"""Serve Danang pages from the private workbook with a last-build fallback."""
import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from sheet_data import read_workbook

TEMPLATE = Path(__file__).resolve().parents[1] / 'index.html'
START = '/* SHEET_DATA_START */'
END = '/* SHEET_DATA_END */'


def fresh_data():
    account = json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    credentials = Credentials.from_service_account_info(
        account, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    client = gspread.authorize(credentials)
    client.set_timeout(8)
    return read_workbook(client)


def with_data(html, snapshot):
    prefix, payload = html.split(START, 1)
    _, suffix = payload.split(END, 1)
    encoded = json.dumps(snapshot, ensure_ascii=False).replace('<', '\\u003c')
    return prefix + START + encoded + END + suffix


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = TEMPLATE.read_text(encoding='utf-8')
        source = 'snapshot'
        cache = 'no-store'
        try:
            snapshot = fresh_data()
            snapshot['source_mode'] = 'connected'
            html = with_data(html, snapshot)
            source = 'sheets'
            cache = 'public, s-maxage=300, stale-while-revalidate=300'
        except (KeyError, ValueError, gspread.exceptions.GSpreadException, OSError):
            pass
        except Exception:
            # Authentication and upstream network failures should not hide the saved list.
            pass
        payload = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', cache)
        self.send_header('X-Tripfact-Data-Source', source)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
