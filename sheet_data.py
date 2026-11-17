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
        value = row.get('mean_vnd', '').replace(',', '')
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
        shop = re.sub(r'\s+', '', str(row.get('환전소(직접 확인)', ''))).lower()
        if shop.isascii() or re.search(r'[a-z]', shop):
            shop = ''.join(c for c in unicodedata.normalize('NFKD', shop)
                           if not unicodedata.combining(c))
        method = row.get('환전 방식')
        names = [label for label, aliases in (
            ('김옌', ('김옌', 'kimyen')), ('김가', ('김가', 'kimga')),
            ('손하', ('손하', 'sonha'))) if any(alias in shop for alias in aliases)]
        if method == '공항' or '공항' in shop:
            names.append('공항')
        if len(names) != 1:
            continue
        currency = row.get('화폐')
        nominal = {'KRW': 50000, 'USD': 100}.get(currency)
        value = amount(row.get('받은 동(VND)', ''))
        source = safe_url(row.get('출처 링크', ''))
        if nominal and amount(row.get('기준 금액', '')) == nominal and value and source:
            groups[names[0], currency, urlparse(source)._replace(query='', fragment='').geturl()].add(value)

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
            if '사이트 노출 대상' in row and row['사이트 노출 대상'] != '포함':
                continue
            if tab == '이발소' and (
                row.get('한국식 풀케어 확인') != '귀청소·마사지·손발톱 관리 확인'
                or row.get('한국인 운영 확인') != '확인 완료'
            ):
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
    return dict(city='danang', imported_at=datetime.now(KST).isoformat(timespec='seconds'),
        rates=rates, rate_status=next((r.get('collection_status') for r in tables['웹요약']), ''),
        places=places, products=products, stats=stats, mentions=mentions,
        exchange_locations=read_exchange_locations(tables.get('환전수집', [])))


def read_workbook(client):
    tabs = [*CATEGORIES, '가격메뉴', '쇼핑목록', '쇼핑웹요약', '웹요약', '쇼핑수집현황', '환전수집']
    book = client.open_by_key(WORKBOOK)
    batches = book.values_batch_get([f"'{tab}'!A1:AZ" for tab in tabs])['valueRanges']
    tables = {}
    for tab, batch in zip(tabs, batches, strict=True):
        headers, *rows = batch.get('values') or [[]]
        tables[tab] = [dict(zip(headers, row)) for row in rows]
    try:
        reviews = book.worksheet('업체리뷰 근거').get_all_records()
    except WorksheetNotFound:
        reviews = []
    tables['업체리뷰 근거'] = reviews
    return build_snapshot(tables)
