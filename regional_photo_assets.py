"""Strict regional photo approvals plus a first-party storage manifest. No cross-city fallback."""
import json,re
from pathlib import Path
from collections import defaultdict,Counter
from urllib.parse import urlparse
from photo_gallery import canonical,integer
CATEGORIES={'마사지':'마사지','네일':'네일','이발소':'이발관','맛집':'맛집','카페':'카페'}
PENDING=re.compile(r'미확인|확인\s*필요|검수\s*필요|검토\s*필요|검토\s*중|검수\s*중|대기|보류|불가|아니오|다른\s*지점|타지점|스톡')
def text(row,key):return str(row.get(key,'')or'').strip()
def https(value):
 u=urlparse(str(value));return str(value)if u.scheme=='https'and u.hostname and not u.username and not u.password else''
def approved(value):return re.sub(r'\s+','',str(value)).lower()in('true','yes','예','가능','게시가능','게시승인완료','승인','공개가능','검수완료','사용승인','게시승인')
def candidates(row):
 values=[text(row,'메인이미지 원본 URL')]+[text(row,'사진'+str(i)+' URL')for i in range(1,6)]+re.findall(r'https?://[^\s<>]+',text(row,'추가사진 후보 URL'))
 return list(dict.fromkeys(v for v in values if urlparse(v).scheme in('http','https')and urlparse(v).hostname))
def assess(ref):
 reasons=[]
 if not approved(text(ref,'사이트 게시 가능')):reasons.append('게시 미승인')
 branch=text(ref,'지점·피사체 확인')
 if PENDING.search(branch)or not re.search(r'(동일|같은|해당)\s*지점|지점.*일치|주소.*일치',branch)or not re.search(r'피사체.*(확인|검수).*완료|지점.*(확인|검수).*완료',branch):reasons.append('지점·피사체 검수 필요')
 rights=text(ref,'사진 사용 허락·라이선스');credit=text(ref,'사진 표시 크레딧')
 legal=bool(re.search(r'CC\s*0|public domain|(허락|허가).*(확인|완료)',rights,re.I))or(bool(re.search(r'CC\s*BY(?:\s|$)',rights,re.I))and not re.search(r'NC|ND',rights,re.I)and bool(credit))
 if PENDING.search(rights)or not legal or not https(text(ref,'허락 근거 URL')):reasons.append('사용 가능 근거 미확인')
 w,h=integer(ref.get('가로 px')),integer(ref.get('세로 px'))
 if min(w,h)<320 or max(w,h)<640:reasons.append('해상도 부족·미확인')
 if re.search(r'실패|오류|404|403|접속\s*불가',text(ref,'접속·검증 상태')):reasons.append('원본 연결 오류')
 return reasons

def approved_candidates(tables,city):
 refs=defaultdict(list)
 for r in tables.get('출처·이미지',[]):refs[(text(r,'업체ID'),canonical(text(r,'이미지 원본 URL')))].append(r)
 selected={};held=[];businesses=[]
 for tab,category in CATEGORIES.items():
  for row in tables.get(tab,[]):
   business=text(row,'업체ID');urls=candidates(row)
   if text(row,'도시')not in('',{'nhatrang':'나트랑','phuquoc':'푸꾸옥'}[city]):continue
   if not business:continue
   businesses.append({'city':city,'category':category,'businessId':business,'candidateCount':len(urls)})
   main=canonical(text(row,'메인이미지 원본 URL'))
   main_ok=approved(text(row,'대표사진 사용 상태'))and not PENDING.search(text(row,'이미지 확인상태'))and bool(re.search(r'확인|승인|완료',text(row,'이미지 확인상태')))
   for order,url in enumerate(urls):
    key=(business,canonical(url));matches=refs.get(key,[]);reasons=['사진별 출처 자료 없음']if not matches else[];ref=None
    for item in matches:
     context=text(item,'도시')+' '+text(item,'자료 구분')
     if ('나트랑'in context and city!='nhatrang')or('푸꾸옥'in context and city!='phuquoc'):reasons=['도시 불일치'];continue
     current=assess(item)
     if not current:ref=item;reasons=[];break
     reasons=current
    if canonical(url)==main and not main_ok:reasons=list(dict.fromkeys(reasons+['대표사진 검수 필요']))
    if reasons:
     held.append({'city':city,'category':category,'businessId':business,'url':url,'reasons':reasons});continue
    kind='menu'if re.search(r'메뉴판|가격표|메뉴\s*이미지',text(ref,'자료 구분')+' '+text(ref,'지점·피사체 확인'))else'general'
    item={'city':city,'businessId':business,'originalUrl':url,'sourceUrl':https(text(ref,'출처 페이지 URL'))or https(text(row,'이미지 출처 URL')),'evidenceUrl':https(text(ref,'허락 근거 URL')),'credit':text(ref,'사진 표시 크레딧'),'width':integer(ref.get('가로 px')),'height':integer(ref.get('세로 px')),'kind':kind,'order':order,'preferredMain':canonical(url)==main,'approved':True,'branchConfirmed':True,'rightsConfirmed':True}
    selected.setdefault(key,item)
 return list(selected.values()),{'businesses':businesses,'held':held,'reasons':dict(Counter(reason for r in held for reason in r['reasons']))}

def read_manifest():
 path=Path(__file__).resolve().parent/'assets/regional-photos/manifest.json'
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (OSError,ValueError):return {'photos':[]}

def attach_assets(places,city,manifest=None,approved_rows=None):
 manifest=manifest or read_manifest();origin=https(manifest.get('storageOrigin',''));bucket=manifest.get('bucket','tripfact-regional-photos')
 prefix=origin.rstrip('/')+'/storage/v1/object/public/'+bucket+'/'if origin else''
 allowed={(p['businessId'],canonical(p['originalUrl']))for p in approved_rows}if approved_rows is not None else None
 by_id=defaultdict(list)
 for photo in manifest.get('photos',[]):
  identity=(photo.get('businessId'),canonical(photo.get('originalUrl','')))
  if photo.get('city')!=city or not all(photo.get(k)is True for k in('approved','branchConfirmed','rightsConfirmed'))or(allowed is not None and identity not in allowed):continue
  if not prefix or not https(photo.get('url','')).startswith(prefix)or not https(photo.get('thumbUrl','')).startswith(prefix):continue
  by_id[photo['businessId']].append(photo)
 for place in places:
  place.update(image='',imageOriginal='',imageThumb='',imageSource='',gallery=[],menuImages=[])
  seen=set();photos=sorted(by_id.get(place.get('sourceId'),[]),key=lambda p:(not p.get('preferredMain'),p.get('order',999)))
  for photo in photos:
   identity=photo.get('sha256')or canonical(photo['url'])
   if identity in seen:continue
   seen.add(identity);entry={k:photo.get(k,'')for k in('url','width','height','sourceUrl','credit')}
   if photo.get('kind')=='menu':place['menuImages'].append(entry)
   elif not place['image']:place.update(image=photo['url'],imageOriginal=photo['url'],imageThumb=photo['thumbUrl'],imageSource=photo.get('sourceUrl',''))
   else:place['gallery'].append(entry)
 return places
