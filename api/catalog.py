"""Shared city layout with strictly regional sheet data and saved fallbacks."""
import json
import base64
import re
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
import gspread
from google.oauth2.service_account import Credentials
from sheet_data import read_workbook, CITY_NAMES, place_is_ready, publish_place
from article_service import home_metadata

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'catalog-template.html'
START='/* SHEET_DATA_START */'
END='/* SHEET_DATA_END */'

def sheet_client():
    account=json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    credentials=Credentials.from_service_account_info(account,scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    client=gspread.authorize(credentials);client.set_timeout(8)
    return client

def with_data(html,snapshot):
    prefix,payload=html.split(START,1)
    _,suffix=payload.split(END,1)
    return prefix+START+json.dumps(snapshot,ensure_ascii=False).replace('<','\\u003c')+END+suffix

def resolve_city(path):
    query=parse_qs(urlparse(path).query)
    value=unquote(query.get('destination',query.get('city',['']))[0]).strip('/')
    if not value:
        value=unquote(urlparse(path).path).strip('/')
    if value in ('','api/catalog','api/destinations'):return 'danang'
    return next((code for code,name in CITY_NAMES.items() if value in (code,name)),None)

def render_catalog(city,live=True):
    html=TEMPLATE.read_text(encoding='utf-8')
    schedules=ROOT/'festival-schedules.json'
    a,b='/* FESTIVAL_SCHEDULES_START */','/* FESTIVAL_SCHEDULES_END */'
    if schedules.exists() and a in html and b in html:
        data=json.loads(schedules.read_text(encoding='utf-8'))
        prefix,rest=html.split(a,1);_,suffix=rest.split(b,1)
        html=prefix+a+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+b+suffix
    saved=ROOT/'city-data'/(city+'.json')
    snapshot=json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else json.loads(html.split(START,1)[1].split(END,1)[0])
    if snapshot.get('city')!=city:raise ValueError('Regional fallback mismatch')
    source='snapshot';status='not-configured'
    if live and os.environ.get('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'):
        try:snapshot=read_workbook(sheet_client(),include_places=True,city=city);source='sheets';status='connected'
        except Exception as error:
            status='read-failed';print('Regional sheet read failed: '+city+' '+type(error).__name__,flush=True)
    snapshot['source_mode']='connected' if source=='sheets' else 'snapshot'
    snapshot['places']=[publish_place(p) for p in snapshot.get('places',[]) if p.get('category') in ('마사지','네일','이발관','맛집','카페') and place_is_ready(p)]
    from business_edits import load_business_edits
    snapshot['places']=load_business_edits(snapshot['places'],city)
    html=with_data(html,snapshot)
    qr=ROOT/'assets/branding'/(city+'-qr.png')
    if qr.exists():
        value='data:image/png;base64,'+base64.b64encode(qr.read_bytes()).decode('ascii')
        html=re.sub(r'const qrSource = "data:image/png;base64,[^"]*";' ,lambda _: 'const qrSource = '+json.dumps(value)+';',html,count=1)
    config={'code':city,'name':CITY_NAMES[city],'path':'/'+CITY_NAMES[city]}
    html=html.replace('</head>','<script>window.tripfactCity='+json.dumps(config,ensure_ascii=False).replace('<','\\u003c')+';</script></head>',1)
    if city!='danang':
        for key in ('tripfact-favs','tripfact-shopping-favs','tripfact-shopping-quantities'):
            html=html.replace("'"+key+"'","'"+key+'-'+city+"'")
    html=home_metadata(html,city=city)
    if city!='danang':html=html.replace('다낭 여행자를',CITY_NAMES[city]+' 여행자를').replace('지금 여행중 · 다낭','지금 여행중 · '+CITY_NAMES[city]).replace('/다낭"','/'+CITY_NAMES[city]+'"')
    return html,source,status

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        city=resolve_city(self.path)
        if city is None:
            self.send_response(404);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers();self.wfile.write('페이지를 찾을 수 없습니다'.encode());return
        html,source,status=render_catalog(city)
        payload=html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','public, s-maxage=300, stale-while-revalidate=300')
        self.send_header('X-Tripfact-City',city)
        self.send_header('X-Tripfact-Data-Source',source)
        self.send_header('X-Tripfact-Sheet-Status',status)
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)
