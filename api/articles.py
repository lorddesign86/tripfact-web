from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape as xml_escape

from article_service import escape, image_url, public_articles, public_origin, render_article, render_page, CITY_NAMES, article_path, article_index


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        view = query.get('view', ['index'])[0]
        slug = query.get('slug', [None])[0]
        city=query.get('city',['danang'])[0]
        if city not in CITY_NAMES:city='danang'
        name=CITY_NAMES[city]
        scoped='city'in query
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
                    batch = public_articles(offset=offset,city=city if scoped else None)
                    rows.extend(batch)
                    if len(batch) < 20:
                        break
                    offset += 20
                if view == 'sitemap':
                    kind = 'application/xml; charset=utf-8'
                    urls='<url><loc>'+xml_escape(origin)+'</loc></url>'+''.join('<url><loc>'+xml_escape(origin+article_index(c))+'</loc></url><url><loc>'+xml_escape(origin+'/'+n)+'</loc></url>'for c,n in CITY_NAMES.items())
                    for row in rows:
                        urls += '<url><loc>' + xml_escape(origin + article_path(row)) + '</loc><lastmod>' + row['updated_at'][:10] + '</lastmod></url>'
                    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>'
                else:
                    kind = 'application/rss+xml; charset=utf-8'
                    items = ''
                    for row in rows[:30]:
                        url = xml_escape(origin + article_path(row))
                        date = format_datetime(datetime.fromisoformat((row['published_at'] or row['created_at']).replace('Z', '+00:00')).astimezone(timezone.utc))
                        items += '<item><title>' + xml_escape(row['title']) + '</title><link>' + url + '</link><guid>' + url + '</guid><description>' + xml_escape(row['description']) + '</description><pubDate>' + date + '</pubDate></item>'
                    body = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>지금 여행중 여행정보</title><link>' + xml_escape(origin + article_index(city)) + '</link><description>자료를 근거로 정리한 여행정보</description>' + items + '</channel></rss>'
            elif slug:
                rows = public_articles(slug,city=city)
                if not rows:
                    status = 404
                    body = render_page('글을 찾을 수 없습니다', '공개된 여행정보를 확인해 주세요.', origin+article_index(city), '<h1>글을 찾을 수 없습니다</h1>',city=city)
                else:
                    body = render_article(rows[0])
            else:
                try:
                    offset = max(0, min(int(query.get('offset', ['0'])[0]), 4980))
                except ValueError:
                    offset = 0
                rows = public_articles(offset=offset,city=city)
                body = '<h1>'+name+' 여행정보</h1><p>'+name+' 여행자를 위한 환전·쇼핑·현지 여행 안내입니다.</p>'
                if not rows:
                    body += '<p>확인한 자료로 새로운 여행정보를 준비하고 있습니다.</p>'
                for row in rows:
                    body += '<a class="article-link" href="' + escape(article_path(row)) + '"><h2>' + escape(row['title']) + '</h2><p>' + escape(row['description']) + '</p><small>자료 기준 ' + escape(row['facts'].get('as_of', '')) + ' · 업데이트 ' + escape(row['updated_at'][:10]) + '</small></a>'
                if len(rows) == 20:
                    body += '<a href="'+article_index(city)+'&offset=' + str(offset + 20) + '">다음 글 보기</a>'
                body = render_page(name+' 여행정보 | 지금 여행중',name+' 환전·쇼핑·현지 여행 안내를 확인하세요.',origin+article_index(city)+('&offset='+str(offset)if offset else ''),body,city=city)
        except Exception:
            status = 503
            body = render_page(name+' 여행정보 | 지금 여행중','여행정보를 준비하고 있습니다.',origin+article_index(city),'<h1>여행정보를 불러오지 못했습니다</h1><p>잠시 후 다시 확인해 주세요.</p>',city=city)
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
