"""Separate destination entry pages; unlaunched cities never load Danang services."""
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from html import escape

CITIES = {'danang': ('다낭', 'DA NANG'), 'nhatrang': ('나트랑', 'NHA TRANG'), 'phuquoc': ('푸꾸옥', 'PHU QUOC')}


def render(city=None):
    if city is not None and city not in CITIES:
        return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>페이지 없음</title><h1>여행지를 찾을 수 없습니다</h1><a href="/">여행지 선택</a></html>', 404
    name = CITIES[city][0] if city else ''
    title = '지금 여행중' + (' · ' + name if name else ' | 여행지 선택')
    links = ''.join('<a href="/' + label + '"' + (' aria-current="page"' if key == city else '') + '>' + label + '</a>' for key, (label, _) in CITIES.items())
    if city:
        content = '<span class="eyebrow">' + CITIES[city][1] + '</span><h1>지금, ' + name + ' 여행중</h1><p>' + name + '의 여행 정보를 준비하고 있어요.</p><p class="muted">쇼핑시세 · 환율 · 날씨 · 현지 이야기</p><a class="button" href="/">다른 여행지 보기</a>'
    else:
        cards = ''.join('<a class="city-card" href="/' + label + '"><strong>' + label + '</strong><span>' + ('여행 시작하기' if key == 'danang' else '오픈 준비 중') + '</span></a>' for key, (label, _) in CITIES.items())
        content = '<span class="eyebrow">YOUR LITTLE TRAVEL BUDDY</span><h1>지금, 어디로 여행 가세요?</h1><p>여행지를 고르고 필요한 정보를 확인하세요.</p><div class="city-grid">' + cards + '</div>'
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>''' + escape(title) + '''</title><script>if(location.pathname==='/'&&(location.hash.includes('access_token=')||location.search.includes('code='))){location.replace('/다낭'+location.search+location.hash);}</script>''' + ('<meta name="robots" content="noindex,follow">' if city else '') + '''<style>
    *{box-sizing:border-box}body{margin:0;background:#f7f9f3;color:#164b46;font-family:system-ui,"Malgun Gothic",sans-serif}header{background:#fffef9;border-bottom:1px solid #e1e8dc}.header{max-width:1080px;margin:auto;padding:16px 24px;display:flex;align-items:center;gap:12px}.header img{width:46px;height:46px;object-fit:contain}.brand{text-decoration:none;color:inherit;font-size:21px;font-weight:800}.brand small{display:block;font-size:13px;font-weight:500;margin-top:3px}nav{display:flex;justify-content:center;gap:8px;padding:10px}nav a{color:inherit;text-decoration:none;padding:8px 22px;border-radius:24px}nav a[aria-current]{background:#21846d;color:#fff}main{max-width:1040px;margin:45px auto;padding:40px 28px;background:#fffef9;border:1px solid #dfe8d8;border-radius:26px;min-height:390px}.hero-mascot{float:right;width:210px;max-width:35%;margin:0 0 20px 24px}h1{font-size:clamp(26px,4vw,40px);line-height:1.4}.eyebrow{font-size:13px;letter-spacing:2px;color:#21846d;font-weight:700}p{font-size:16px;line-height:1.7}.muted{color:#718273}.city-grid{clear:both;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:32px}.city-card{padding:24px 20px;border-radius:18px;border:1px solid #dce7d3;background:#f0f5e7;text-decoration:none;color:inherit}.city-card strong{display:block;font-size:24px}.city-card span{display:block;margin-top:12px;font-size:14px;color:#637762}.button{display:inline-block;padding:12px 22px;background:#21846d;color:white;border-radius:12px;text-decoration:none;margin-top:16px}footer{max-width:1040px;margin:24px auto;padding:16px 24px;color:#718273;font-size:14px}a:focus-visible{outline:3px solid #e1ac45;outline-offset:3px}@media(max-width:600px){main{margin:20px 14px;padding:28px 20px}.hero-mascot{width:120px}.city-grid{grid-template-columns:1fr}.city-card{padding:20px}nav a{padding:8px 18px}}
    </style></head><body><header><div class="header"><img src="/assets/mascots/yuyu-vietnam-site.webp" alt="유유"><a class="brand" href="/">지금 여행중<small>여행지 선택</small></a></div></header><nav aria-label="여행지 선택">''' + links + '''</nav><main><img class="hero-mascot" src="/assets/mascots/yuyu-vietnam-site.webp" alt="베트남을 여행하는 유유">''' + content + '''</main><footer>지금 여행중 · 나에게 필요한 여행 정보</footer></body></html>''', 200


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        city = parse_qs(urlparse(self.path).query).get('city', [None])[0]
        page, status = render(city)
        payload = page.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'public, s-maxage=300')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
