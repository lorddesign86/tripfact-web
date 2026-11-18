from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape as xml_escape

from article_service import escape, image_url, public_articles, public_origin, render_article, render_page


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        view = query.get('view', ['index'])[0]
        slug = query.get('slug', [None])[0]
        origin = public_origin()
        kind = 'text/html; charset=utf-8'
        status = 200
        try:
            if view == 'robots':
                kind = 'text/plain; charset=utf-8'
                body = 'User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: ' + origin + '/sitemap.xml\n'
            elif view in ('sitemap', 'rss'):
                rows = []
                offset = 0
                while offset < 5000:
                    batch = public_articles(offset=offset)
                    rows.extend(batch)
                    if len(batch) < 20:
                        break
                    offset += 20
                if view == 'sitemap':
                    kind = 'application/xml; charset=utf-8'
                    urls = '<url><loc>' + xml_escape(origin) + '</loc></url><url><loc>' + xml_escape(origin + '/information') + '</loc></url>'
                    for row in rows:
                        urls += '<url><loc>' + xml_escape(origin + '/information/' + row['slug']) + '</loc><lastmod>' + row['updated_at'][:10] + '</lastmod></url>'
                    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>'
                else:
                    kind = 'application/rss+xml; charset=utf-8'
                    items = ''
                    for row in rows[:30]:
                        url = xml_escape(origin + '/information/' + row['slug'])
                        date = format_datetime(datetime.fromisoformat((row['published_at'] or row['created_at']).replace('Z', '+00:00')).astimezone(timezone.utc))
                        items += '<item><title>' + xml_escape(row['title']) + '</title><link>' + url + '</link><guid>' + url + '</guid><description>' + xml_escape(row['description']) + '</description><pubDate>' + date + '</pubDate></item>'
                    body = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>다낭 트립팩트 여행정보</title><link>' + xml_escape(origin + '/information') + '</link><description>자료를 근거로 정리한 다낭 여행정보</description>' + items + '</channel></rss>'
            elif slug:
                rows = public_articles(slug)
                if not rows:
                    status = 404
                    body = render_page('글을 찾을 수 없습니다', '공개된 여행정보를 확인해 주세요.', origin + '/information', '<h1>글을 찾을 수 없습니다</h1>')
                else:
                    body = render_article(rows[0])
            else:
                try:
                    offset = max(0, min(int(query.get('offset', ['0'])[0]), 4980))
                except ValueError:
                    offset = 0
                rows = public_articles(offset=offset)
                body = '<h1>다낭 여행정보</h1><p>최근 수집 자료를 바탕으로 환전과 쇼핑에 필요한 내용을 정리합니다.</p>'
                if not rows:
                    body += '<p>확인한 자료로 새로운 여행정보를 준비하고 있습니다.</p>'
                for row in rows:
                    body += '<a class="article-link" href="/information/' + escape(row['slug']) + '"><h2>' + escape(row['title']) + '</h2><p>' + escape(row['description']) + '</p><small>자료 기준 ' + escape(row['facts'].get('as_of', '')) + ' · 업데이트 ' + escape(row['updated_at'][:10]) + '</small></a>'
                if len(rows) == 20:
                    body += '<a href="/information?offset=' + str(offset + 20) + '">다음 글 보기</a>'
                body = render_page('다낭 여행정보 · 환전과 쇼핑 가이드 | 트립팩트', '최신 수집 자료로 정리한 다낭 환전·쇼핑 가이드와 자주 묻는 질문을 확인하세요.', origin + '/information' + ('?offset=' + str(offset) if offset else ''), body)
        except Exception:
            status = 503
            body = render_page('다낭 여행정보 | 트립팩트', '여행정보를 준비하고 있습니다.', origin + '/information', '<h1>여행정보를 불러오지 못했습니다</h1><p>잠시 후 다시 확인해 주세요.</p>')
            kind = 'text/html; charset=utf-8'
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'public, s-maxage=60, stale-while-revalidate=60' if status == 200 else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        if status != 200:
            self.send_header('X-Robots-Tag', 'noindex')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
