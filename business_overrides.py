"""Public, whitelisted business fields merged strictly by source business ID."""
import hashlib
import re
from urllib.parse import urlparse

PRICE_FIELDS={
 '마사지':[(f'{kind}{minutes}분 VND',f'{kind} {minutes}분',kind,minutes)for kind,minutes in [('아로마',60),('아로마',90),('아로마',120),('타이',60),('타이',90),('타이',120),('풋',60),('풋',90)]],
 '네일':[('손젤 대표가격 VND','손젤 대표가격','손젤',None),('발젤 대표가격 VND','발젤 대표가격','발젤',None)],
 '이발관':[('이발관 대표코스1 VND','대표코스1','대표코스1',None),('이발관 대표코스2 VND','대표코스2','대표코스2',None)]}

def text(row,key):return str(row.get(key,'')).strip()

def public_url(value):
 value=str(value).strip()
 # Older Kakao public channel links use HTTP; upgrade only this known host.
 if value.startswith('http://pf.kakao.com/'):value='https://'+value[7:]
 u=urlparse(value)
 return value if u.scheme=='https' and u.hostname and not u.username and not u.password else ''

def numeric_price(value):
 raw=str(value).strip().replace(',','')
 return int(raw) if re.fullmatch(r'[0-9]+',raw) and int(raw)>0 else None

def tags_from(row):
 result=[]
 for key in ['추가 특징 해시태그','자동 생성 해시태그']:
  for tag in re.split(r'[#\n]',text(row,key)):
   tag=tag.strip()
   if ('해피아워'in tag and not text(row,'해피아워 혜택'))or('포핸드'in tag and '있음'not in text(row,'포핸드마사지 여부')):continue
   if not tag or re.search(r'없음|없다|미제공|미지원|해당없|미확인|불가',tag):continue
   if tag not in result:result.append(tag)
 return result[:20]

def apply_direct_businesses(places,rows):
 by_id={}
 for p in places:
  source=p.get('sourceId')
  if source and p.get('category')in PRICE_FIELDS:
   previous=by_id.get(source,{})
   by_id[source]=p if len(str(p))>len(str(previous)) else previous
 seen=set();result=[p for p in places if p['category']not in PRICE_FIELDS]
 for row in rows:
  source=text(row,'업체ID')
  if not source:continue
  if source in seen:raise ValueError('Duplicate manual business ID')
  seen.add(source)
  if text(row,'보강 대상')!='핵심업체':continue
  selection=text(row,'업종 선택').replace('이발소','이발관')
  base=by_id.get(source,{})
  for category in PRICE_FIELDS:
   if category not in selection:continue
   tab='이발소'if category=='이발관'else category
   p={**base,'sourceId':source,'id':'sheet-'+hashlib.sha256((tab+':'+source).encode()).hexdigest()[:20],
      'name':text(row,'업체명·지점')or base.get('name',''),'category':category,'type':'spa','manualInput':True,
      'manualPriority':text(row,'보강 대상'),'manualTargetArea':text(row,'목표권역'),'menus':[],
      'priceMemo':text(row,'가격기준·코스명·포함내용'),'transportType':text(row,'이동 지원 유형'),
      'transportConditions':text(row,'이동 조건·추가요금'),'tipPolicy':text(row,'팁 표기'),
      'happyHour':text(row,'해피아워 혜택'),'specialBenefit':text(row,'특별혜택'),
      'fourHands':text(row,'포핸드마사지 여부'),'fourHandsPrice':text(row,'포핸드 가격 VND'),
      'menuUrl':public_url(text(row,'가격표 이미지·메뉴페이지 주소')),'featureTags':tags_from(row)}
   p['short']=p['name'];p['badge']=category;p['tags']=[category]+p['featureTags']
   p['map']=public_url(text(row,'구글지도 링크'))or base.get('map','')
   booking=public_url(text(row,'카카오톡 또는 예약 링크'))
   p['booking']=booking;p['kakao']=booking if 'kakao.com'in(urlparse(booking).hostname or '')else '';p['reservation']=booking if not p['kakao']else ''
   area=p['manualTargetArea']or base.get('loc','');p['loc']=area
   p['region']='한시장'if '한시장'in area else '호이안'if '호이안'in area else '미케비치'if any(k in area for k in ['미케','팜반동','안트엉'])else base.get('region','')
   p['pickup']=' · '.join(x for x in [p['transportType'],p['transportConditions']]if x)or '이동 지원 확인 필요'
   p['directPrices']=[]
   for key,label,service,minutes in PRICE_FIELDS[category]:
    raw=text(row,key);value=numeric_price(raw)
    p['directPrices'].append({'name':label,'raw':raw,'value':value})
    if value:p['menus'].append({'name':label,'service':service,'minutes':minutes,'low':value,'high':value,'conditions':p['priceMemo'],'source':p['menuUrl'],'date':'','directInput':True})
   p['reviewEvidence']=[e for e in base.get('reviewEvidence',[])];p['reviewHighlight']='';p['reviewCaution']=''
   # Internal review/research columns are deliberately never copied into public payloads.
   result.append(p)
 return result
