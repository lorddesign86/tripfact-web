import hmac
import json
import os
from http.server import BaseHTTPRequestHandler

from article_service import database_url, generate_article, request_json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get('CRON_SECRET', '').strip()
        if not secret or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + secret):
            self.reply(401, {'error': 'unauthorized'})
            return
        self.run(False)

    def do_POST(self):
        token = self.headers.get('Authorization', '')
        if not token.startswith('Bearer ') or len(token) > 10000:
            self.reply(401, {'error': 'unauthorized'})
            return
        try:
            admin = request_json(database_url() + '/rest/v1/rpc/tripfact_is_admin', {}, {
                'apikey': os.environ['NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'].strip(), 'Authorization': token})
            if admin is not True:
                self.reply(403, {'error': 'admin_required'})
                return
        except Exception:
            self.reply(403, {'error': 'admin_required'})
            return
        self.run(True)

    def run(self, manual):
        try:
            result = generate_article(manual)
            self.reply(503 if result['state'] == 'not_configured' else 200, result)
        except Exception as error:
            print('Article generation failed: ' + type(error).__name__, flush=True)
            self.reply(502, {'error': 'generation_failed'})

    def reply(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
