"""Serve Danang pages from the private workbook with a last-build fallback."""
import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from sheet_data import WORKBOOK, read_exchange_locations, read_rates, read_workbook
from article_service import home_metadata

TEMPLATE = Path(__file__).resolve().parents[1] / 'catalog-template.html'
START = '/* SHEET_DATA_START */'
END = '/* SHEET_DATA_END */'


def sheet_client():
    account = json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    credentials = Credentials.from_service_account_info(
        account, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    client = gspread.authorize(credentials)
    client.set_timeout(8)
    return client


def with_data(html, snapshot):
    prefix, payload = html.split(START, 1)
    _, suffix = payload.split(END, 1)
    encoded = json.dumps(snapshot, ensure_ascii=False).replace('<', '\\u003c')
    return prefix + START + encoded + END + suffix


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = TEMPLATE.read_text(encoding='utf-8')
        source = 'snapshot'
        sheet_status = 'not-configured'
        cache = 'no-store'
        try:
            client = sheet_client()
            sheet_status = 'read-failed'
            try:
                snapshot = read_workbook(client, include_places=True)
                source = 'sheets'
            except Exception:
                # Keep live rates available even if an unrelated catalog tab fails.
                snapshot = json.loads(html.split(START, 1)[1].split(END, 1)[0])
                book = client.open_by_key(WORKBOOK)
                rates_sheet = book.worksheet('웹요약')
                rows = rates_sheet.get_all_records(numericise_ignore=['all'])
                snapshot['rates'] = read_rates(rows)
                snapshot['rate_status'] = next((row.get('collection_status') for row in rows), '')
                try:
                    records = book.worksheet('환전수집').get_all_records(numericise_ignore=['all'])
                    snapshot['exchange_locations'] = read_exchange_locations(records)
                except gspread.exceptions.GSpreadException:
                    pass
                source = 'sheets-rates'
            snapshot['source_mode'] = 'connected' if source == 'sheets' else 'snapshot'
            snapshot['places'] = [p for p in snapshot.get('places', []) if p.get('category') in ('마사지', '네일', '이발관')]
            html = with_data(html, snapshot)
            sheet_status = 'connected' if source == 'sheets' else 'rates-only'
            cache = 'public, s-maxage=300, stale-while-revalidate=300'
        except Exception as error:
            # Authentication and upstream network failures should not hide the saved list.
            if os.environ.get('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'):
                sheet_status = 'read-failed'
                print(f'Sheet connection failed: {type(error).__name__}', flush=True)
        payload = home_metadata(html).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', cache)
        self.send_header('X-Tripfact-Data-Source', source)
        self.send_header('X-Tripfact-Sheet-Status', sheet_status)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
