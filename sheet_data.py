import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from urllib.parse import urlparse
from gspread.exceptions import WorksheetNotFound

KST = timezone(timedelta(hours=9))

WORKBOOK = '1EypcoS2PInvEWcYXYJCiFBT0BWnJ_s9X2ekHf6Z1SMU'
CATEGORIES = {'마사지': '마사지', '네일': '네일', '이발소': '이발관', '맛집': '맛집', '카페': '카페'}


def safe_url(value):
    return value if urlparse(value).scheme == 'https' and urlparse(value).hostname else ''


def amount(value):
    value = str(value).replace(',', '').strip()
    return int(value) if re.fullmatch(r'\d+', value) else None


def price_range(value):
    match = re.fullmatch(r'\s*([\d,]+)(?:\s*[~–-]\s*([\d,]+))?\s*', str(value))
    if not match:
        return None
    low, high = amount(match[1]), amount(match[2] or match[1])
    return (low, high) if low and high and high >= low else None


def read_rates(rows):
    rates = []
    for row in rows:
        if row.get('currency') not in ('USD', 'KRW') or not row.get('category'):
            continue
        value = str(row.get('mean_vnd', '')).replace(',', '')
        rates.append(dict(category=row['category'], currency=row['currency'],
            nominal=amount(row.get('nominal', '')), posts=amount(row.get('posts', '')) or 0,
            mean_vnd=float(value) if value else None,
            **{'from': row.get('from', ''), 'to': row.get('to', '')}))
    return rates


def read_exchange_locations(rows, today=None):
    """Compare matching denominations, counting each unambiguous source post once."""
    end = today or datetime.now(KST).date()
    start = (end - timedelta(days=6)).isoformat()
    end = end.isoformat()
    groups = defaultdict(set)
    for row in rows:
        posted = str(row.get('글 작성일', '')).strip()
        if not start <= posted <= end or row.get('분류') not in ('실거래 후보', '환율 언급'):
            continue
        exchange_date = str(row.get('환전일(직접 확인)', '')).strip()
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', exchange_date) and not start <= exchange_date <= end:
            continue
        shop = re.sub(r'\s+', '', str(row.get('환전소(직접 확인)', ''))).lower()
        if shop.isascii() or re.search(r'[a-z]', shop):
            shop = ''.join(c for c in unicodedata.normalize('NFKD', shop)
                           if not unicodedata.combining(c))
        method = row.get('환전 방식')
        names = [label for label, aliases in (
            ('김옌', ('김옌', '킴옌', 'kimyen')), ('김가', ('김가', '킴가', '킴기아', 'kimgia', 'kimga')),
            ('손하', ('손하', '소안하', '쏘안하', 'sonha', 'soanha'))) if any(alias in shop for alias in aliases)]
        if not names and method in ('김옌', '김가', '손하'):
            names.append(method)
        if method == '공항' or '공항' in shop:
            names.append('공항')
        if len(names) != 1:
            continue
        currency = row.get('화폐')
        nominal = {'KRW': 50000, 'USD': 100}.get(currency)
        value = amount(row.get('받은 동(VND)', ''))
        source = safe_url(row.get('출처 링크', ''))
        if nominal and amount(row.get('기준 금액', '')) == nominal and value and source:
            comment = re.match(r'댓글 기록 ([a-f0-9]{16})', str(row.get('확인 사유', '')))
            source_key = (urlparse(source)._replace(query='', fragment='').geturl(), comment[1] if comment else '')
            groups[names[0], currency, source_key].add(value)

    samples = defaultdict(list)
    for (name, currency, _), values in groups.items():
        if len(values) == 1:
            samples[name, currency].append(next(iter(values)))
    return [
        {'location': name, 'currency': currency, 'posts': len(values),
         'mean_vnd': round(mean(values), 2) if values else None, 'from': start, 'to': end}
        for name in ('김옌', '김가', '손하', '공항')
        for currency in ('KRW', 'USD')
        for values in [samples[name, currency]]
    ]


def build_snapshot(tables):
    evidence = defaultdict(list)
    review_ids = set()
    for row in tables.get('업체리뷰 근거', []):
        if row.get('사이트 게시 상태') not in ('게시 승인 · 직접 제보', '게시 승인 · 재사용 허용') or not row.get('재사용 근거'):
            continue
        review_id = row.get('근거ID')
        source = safe_url(row.get('출처 URL', ''))
        if not review_id or review_id in review_ids or not source or not row.get('후기 요약'):
            continue
        review_ids.add(review_id)
        evidence[(row.get('업종'), row.get('업체ID'))].append({
            'topic': row.get('언급 항목', ''), 'direction': row.get('평가 방향', ''),
            'summary': row['후기 요약'], 'source': source, 'sourceType': row.get('출처 유형', ''),
            'date': row.get('후기 작성 시점', ''),
        })
    menus = defaultdict(list)
    for row in tables['가격메뉴']:
        low = amount(row.get('정가·최소가(VND)', ''))
        high = amount(row.get('최대가(VND)', '')) or low
        if not low or high < low or '수기로 확인 필요' in row.get('적용 조건', ''):
            continue
        menus[(row.get('업종'), row['업체ID'])].append({
            'name': row.get('서비스명') or row.get('비교 항목', ''),
            'service': row.get('비교 항목', ''),
            'minutes': amount(row.get('시간(분)', '')), 'low': low, 'high': high,
            'conditions': row.get('적용 조건', ''), 'date': row.get('확인일', ''),
            'source': safe_url(row.get('가격 출처 URL', '')),
        })

    places = []
    seen = set()
    for tab, category in CATEGORIES.items():
        for row in tables[tab]:
            source_id, name = row.get('업체ID'), row.get('업체명')
            if not source_id or not name or (tab, source_id) in seen:
                continue
            if row.get('사이트 노출 대상') in ('제외','비공개','숨김'):
                continue
            selected=row.get('선택 업종·자동분류','').strip()
            if selected and category not in selected and tab not in selected:
                continue
            seen.add((tab, source_id))
            entries = menus[(tab, source_id)]
            reviews = sorted(evidence[(tab, source_id)], key=lambda item: str(item['date']), reverse=True)
            comparable = [m for m in entries if m['minutes'] == 90 and m['service'] == '아로마'] if tab == '마사지' else []
            value = min((m['low'] for m in comparable), default=None)
            image = safe_url(row.get('메인이미지 원본 URL', ''))
            if '수기로 확인 필요' in row.get('이미지 확인상태', '') or 'streetviewpixels' in image:
                image = ''
            try:
                rating = float(row.get('구글평점') or 0)
            except ValueError:
                rating = 0
            area = row.get('지역', '')
            region = next((r for r in ('한시장', '미케비치', '호이안') if r in area), '')
            places.append({
                'id': 'sheet-' + hashlib.sha256((tab + ':' + source_id).encode()).hexdigest()[:20],
                'name': name, 'short': name, 'category': category,
                'type': 'spa' if tab in ('마사지', '네일', '이발소') else 'dining',
                'loc': area, 'region': region, 'address': row.get('주소', ''),
                'map': safe_url(row.get('구글지도 URL', '')),
                'booking': safe_url(row.get('카카오톡 예약 URL', '')) or safe_url(row.get('예약 URL', '')),
                'pickup': row.get('픽업·드롭') or '픽업 정보 미확인',
                'price': f'{value:,}동부터' if value else '가격 확인 필요',
                'priceValue': value, 'menus': entries, 'image': image, 'tags': [category],
                'imageSource': safe_url(row.get('이미지 출처 URL', '')) if image else '',
                'rating': rating if 0 < rating <= 5 else None,
                'reviews': amount(row.get('구글리뷰수', '')),
                'hours': row.get('영업시간', ''), 'phone': row.get('전화', ''),
                'website': safe_url(row.get('공식 홈페이지', '')),
                'services': row.get('시설·서비스', ''),
                'kakao': safe_url(row.get('카카오톡 예약 URL', '')),
                'reservation': safe_url(row.get('예약 URL', '')),
                'reviewEvidence': reviews,
                'reviewHighlight': next((item['summary'] for item in reviews if item['direction'] == '긍정'), ''),
                'reviewCaution': next((item['summary'] for item in reviews if item['direction'] == '주의'), ''),
                'badge': category, 'date': row.get('구글 확인일', '')[:10],
            })

    products = []
    for row in tables['쇼핑목록']:
        if not row.get('품목ID') or not row.get('품목'):
            continue
        bounds = price_range(row.get('참고가격(통계 제외)', ''))
        reference = None
        if bounds and row.get('참고 통화(통계 제외)') == 'VND':
            reference = dict(low=bounds[0], high=bounds[1],
                description=row.get('참고 제품·단위(통계 제외)', ''),
                date=row.get('참고 날짜(통계 제외)', ''),
                source=safe_url(row.get('참고 출처(통계 제외)', '')))
        products.append(dict(id=row['품목ID'], name=row['품목'], category=row.get('분류', ''),
            aliases=[x.strip() for x in row.get('검색어(쉼표 구분)', '').split(',') if x.strip()],
            specification=row.get('가격 비교 조건', ''), reference=reference))

    stats = defaultdict(list)
    for row in tables['쇼핑웹요약']:
        n = amount(row.get('표본수', '')) or 0
        low, high = amount(row.get('최저', '')), amount(row.get('최고', ''))
        if row.get('통화') != 'VND' or n < 1 or not low or not high or high < low or not row.get('비교단위'):
            continue
        stats[row['품목ID']].append(dict(low=low, high=high, n=n, unit=row['비교단위'],
            start=row.get('기간시작(글 작성일)', ''), end=row.get('기간끝(글 작성일)', '')))
    rates = read_rates(tables['웹요약'])
    mentions = {}
    for row in tables['쇼핑수집현황']:
        product_id = row.get('품목ID')
        count = amount(row.get('가격이 나온 글 수', ''))
        start = row.get('시작일(글 작성일)', '')
        end = row.get('종료일(글 작성일)', '')
        if not product_id or not count or not start or not end:
            continue
        entry = dict(count=count, start=start, end=end, latest=row.get('최근 글 작성일', ''))
        existing = mentions.get(product_id)
        if not existing or (end, start, count) > (existing['end'], existing['start'], existing['count']):
            mentions[product_id] = entry
    locations = read_exchange_locations(tables.get('환전수집', []))
    live_rates = {(row['category'], row['currency']): row for row in rates
                  if row['category'] in ('김옌', '김가', '손하', '공항') and row['posts'] and row['mean_vnd']}
    for location in locations:
        combined = live_rates.get((location['location'], location['currency']))
        if combined:
            for field in ('posts', 'mean_vnd', 'from', 'to'):
                location[field] = combined[field]
        if not location['mean_vnd']:
            candidates = [row for row in tables.get('환전최근확인', [])
                if row.get('환전장소') == location['location']
                and row.get('기준금액') == ('100달러' if location['currency'] == 'USD' else '5만원')
                and amount(row.get('최근 확인 VND', '')) and safe_url(row.get('출처 링크', ''))
                and re.fullmatch(r'20\d{2}-\d{2}-\d{2}', row.get('확인일', ''))
                and row['확인일'] <= datetime.now(KST).date().isoformat()]
            if candidates:
                latest = max(candidates, key=lambda row: row['확인일'])
                location.update(mean_vnd=amount(latest['최근 확인 VND']), posts=1, basis='latest_known',
                    source_date=latest['확인일'], source_url=latest['출처 링크'],
                    **{'from': latest['확인일'], 'to': latest['확인일']})
    return dict(city='danang', imported_at=datetime.now(KST).isoformat(timespec='seconds'),
        rates=rates, rate_status=next((r.get('collection_status') for r in tables['웹요약']), ''),
        places=places, products=products, stats=stats, mentions=mentions,
        exchange_locations=locations)


CITY_NAMES = {'danang':'다낭', 'nhatrang':'나트랑', 'phuquoc':'푸꾸옥'}
EXCHANGE_NAMES = {'danang':['김옌','김가','손하','공항'], 'nhatrang':['김청','김빈','나트랑공항'], 'phuquoc':['금은방','킹콩마트 옆','푸꾸옥공항','GOOD&GOOD','킹콩마트 앞']}

def verified_menus(place):
    today=datetime.now(KST).date().isoformat()
    oldest=(datetime.now(KST).date()-timedelta(days=180)).isoformat()
    return [menu for menu in place.get('menus',[]) if isinstance(menu.get('low'),(int,float)) and menu['low']>0 and menu.get('high',0)>=menu['low'] and safe_url(menu.get('source','')) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}',menu.get('date','')) and oldest<=menu['date']<=today]

def representative_menu(place):
    prices=[m for m in verified_menus(place) if not re.search(r'제거|추가요금|옵션|파일링|큐티클',m.get('name',''))]
    if not prices:
        return None
    if place.get('category')=='네일':
        preferred=[m for m in prices if '젤' in m.get('name','') and ('매니큐어' in m.get('name','') or '손' in m.get('name',''))]
    else:
        preferred=[m for m in prices if place.get('category')=='마사지' and m.get('minutes')==90 and m.get('service')=='아로마']
    return min(preferred or prices,key=lambda m:m['low'])

def place_is_ready(place):
    return bool(str(place.get('name','')).strip() and (safe_url(place.get('map','')) or str(place.get('address','')).strip()))

def publish_place(place):
    result={**place,'menus':verified_menus(place)}
    menu=representative_menu(place)
    if not menu:
        result.update(priceValue=None,price='가격 문의',priceBasis='')
        return result
    result['priceValue']=menu['low']
    result['price']=(f"{menu['low']:,}~{menu['high']:,}동"if menu['low']!=menu['high']else f"{menu['low']:,}동")
    result['priceBasis']=menu.get('name','')+(' · '+str(menu['minutes'])+'분'if menu.get('minutes')else '')
    return result

def read_workbook(client, include_places=True, city='danang'):
    if city not in CITY_NAMES:
        raise ValueError('Unknown city')
    name=CITY_NAMES[city]
    book=client.open_by_key(WORKBOOK)
    available={sheet.title for sheet in book.worksheets()}
    def choose(*names):
        return next((title for title in names if title in available),None)
    mapping={
      '쇼핑목록':choose('공통 쇼핑목록','쇼핑목록'),
      '쇼핑웹요약':choose(name+' 쇼핑웹요약',*(('쇼핑웹요약',) if city=='danang' else ())),
      '쇼핑수집현황':choose(name+' 쇼핑수집현황',*(('쇼핑수집현황',) if city=='danang' else ())),
      '웹요약':choose('웹요약' if city=='danang' else name+'_웹요약'),
      '환전수집':choose('환전수집' if city=='danang' else name+'_환전수집'),
      '환전최근확인':choose('환전최근확인' if city=='danang' else name+'_최근확인'),
      '지역참고가격':choose(name+' 쇼핑참고가격')}
    if include_places:
        for tab in [*CATEGORIES,'가격메뉴','업체리뷰 근거']:
            mapping[tab]=choose(name+' '+tab,name+'_'+tab,*((tab,) if city=='danang' else ()))
    required=['쇼핑목록','쇼핑웹요약','웹요약']
    if any(not mapping.get(key) for key in required):
        raise ValueError('Missing regional sheet')
    present=[(key,title) for key,title in mapping.items() if title]
    batches=book.values_batch_get(["'"+title.replace("'","''")+"'!A1:CH" for _,title in present])['valueRanges']
    tables={key:[] for key in [*CATEGORIES,'가격메뉴','업체리뷰 근거',*mapping]}
    for (key,_),batch in zip(present,batches,strict=True):
        headers,*rows=batch.get('values') or [[]]
        tables[key]=[dict(zip(headers,row)) for row in rows]
    # The common catalogue describes products, never another city's prices.
    if city!='danang':
        tables['쇼핑목록']=[{k:v for k,v in row.items() if not k.startswith('참고')} for row in tables['쇼핑목록']]
    references={row.get('품목ID'):row for row in tables['지역참고가격'] if row.get('통화')=='VND' and safe_url(row.get('출처',''))}
    for row in tables['쇼핑웹요약']:
        if row.get('표시통화')=='VND' and safe_url(row.get('표시가격 출처','')) and row.get('품목ID') not in references:
            references[row['품목ID']]={'참고가격':row.get('표시가격',''),'통화':'VND','기준일':row.get('표시가격 기준일',''),'제품·단위':row.get('표시가격 단위·제품',''),'출처':row['표시가격 출처']}
    for row in tables['쇼핑목록']:
        ref=references.get(row.get('품목ID'))
        if ref:
            row.update({'참고가격(통계 제외)':ref.get('참고가격',''),'참고 통화(통계 제외)':'VND','참고 날짜(통계 제외)':ref.get('기준일',''),'참고 제품·단위(통계 제외)':ref.get('제품·단위',''),'참고 출처(통계 제외)':ref['출처']})
    result=build_snapshot(tables)
    result['places']=[publish_place(place) for place in result['places'] if place_is_ready(place)]
    result['city']=city
    result['exchange_names']=EXCHANGE_NAMES[city]
    if city!='danang':
        result['exchange_locations']=[]
        for label in EXCHANGE_NAMES[city]:
            for currency in ('KRW','USD'):
                summary=next((r for r in result['rates'] if r['category']==label and r['currency']==currency and r['posts'] and r['mean_vnd']),None)
                if summary:
                    result['exchange_locations'].append({**summary,'location':label})
                    continue
                candidates=[r for r in tables['환전최근확인'] if r.get('환전장소')==label and r.get('기준금액')==('100달러' if currency=='USD' else '5만원') and amount(r.get('최근 확인 VND','')) and safe_url(r.get('출처 링크','')) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}',r.get('확인일','')) and r['확인일']<=datetime.now(KST).date().isoformat()]
                if candidates:
                    r=max(candidates,key=lambda row:row['확인일'])
                    result['exchange_locations'].append({'location':label,'currency':currency,'posts':1,'mean_vnd':amount(r['최근 확인 VND']),'basis':'latest_known','source_date':r['확인일'],'source_url':r['출처 링크'],'from':r['확인일'],'to':r['확인일']})
    return result
