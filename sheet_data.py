import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

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


def build_snapshot(tables):
    menus = defaultdict(list)
    for row in tables['가격메뉴']:
        low = amount(row.get('정가·최소가(VND)', ''))
        high = amount(row.get('최대가(VND)', '')) or low
        if not low or high < low:
            continue
        menus[row['업체ID']].append({
            'name': row.get('서비스명') or row.get('비교 항목', ''),
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
            seen.add((tab, source_id))
            entries = menus[source_id]
            comparable = [m for m in entries if m['minutes'] == 90 and '아로마' in m['name']] if tab == '마사지' else []
            value = min((m['low'] for m in comparable), default=None)
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
                'priceValue': value, 'menus': entries, 'image': '', 'tags': [category],
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
        if row.get('통화') != 'VND' or n < 3 or not low or not high or high < low or not row.get('비교단위'):
            continue
        stats[row['품목ID']].append(dict(low=low, high=high, n=n, unit=row['비교단위'],
            start=row.get('기간시작(글 작성일)', ''), end=row.get('기간끝(글 작성일)', '')))
    rates = []
    for row in tables['웹요약']:
        if row.get('currency') not in ('USD', 'KRW') or not row.get('category'):
            continue
        rates.append(dict(category=row['category'], currency=row['currency'],
            nominal=amount(row.get('nominal', '')), posts=amount(row.get('posts', '')) or 0,
            mean_vnd=float(row['mean_vnd']) if row.get('mean_vnd') else None,
            **{'from': row.get('from', ''), 'to': row.get('to', '')}))
    return dict(city='danang', imported_at=datetime.now(KST).isoformat(timespec='seconds'),
        rates=rates, rate_status=next((r.get('collection_status') for r in tables['웹요약']), ''),
        places=places, products=products, stats=stats)


def read_workbook(client):
    tabs = [*CATEGORIES, '가격메뉴', '쇼핑목록', '쇼핑웹요약', '웹요약']
    book = client.open_by_key(WORKBOOK)
    batches = book.values_batch_get([f"'{tab}'!A1:AZ" for tab in tabs])['valueRanges']
    tables = {}
    for tab, batch in zip(tabs, batches, strict=True):
        headers, *rows = batch['values']
        tables[tab] = [dict(zip(headers, row)) for row in rows]
    return build_snapshot(tables)
