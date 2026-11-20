"""Approve photos by business ID and explicit publication evidence; candidates stay private."""
import re
from collections import Counter,defaultdict
from urllib.parse import urlparse,urlunparse
from business_overrides import public_url

BLOCKED=re.compile(r'미확인|확인\s*필요|검수\s*대기|검토\s*대기|검토\s*중|수기|보류|불가|아니오|아님|없음|다른\s*지점|타지점|스톡')

def clean(row,key):return str(row.get(key,'')).strip()
def integer(value):
 try:return int(str(value).replace(',','').strip())
 except (ValueError,TypeError):return 0

def canonical(url):
 u=urlparse(str(url));path=u.path
 if (u.hostname or '').endswith('googleusercontent.com'):
  path=re.sub(r'=(?:w\d+(?:-h\d+)?[^/]*|s\d+[^/]*)$','',path)
 return urlunparse((u.scheme,u.netloc,path,'',u.query,''))

def candidate_index(tables):
 index=defaultdict(set)
 for key in ('마사지','네일','이발소','맛집','카페'):
  for row in tables.get(key,[]):
   source=clean(row,'업체ID')
   if not source:continue
   for url in re.findall(r'https?://[^\s<>]+',clean(row,'추가사진 후보 URL')):
    index[source].add(canonical(url))
 return index

def assess_photo(row,declared):
 source=clean(row,'업체ID');url=public_url(clean(row,'이미지 원본 URL'));reasons=[]
 if not source or not url:reasons.append('invalid_business_or_url')
 if canonical(clean(row,'이미지 원본 URL'))not in declared.get(source,set()):reasons.append('not_in_business_candidates')
 publish=re.sub(r'\s+','',clean(row,'사이트 게시 가능')).lower()
 if publish not in ('true','yes','예','가능','게시가능','게시승인완료','승인','공개가능'):reasons.append('not_approved')
 branch=clean(row,'지점·피사체 확인')
 if BLOCKED.search(branch)or not re.search(r'(동일\s*지점|같은\s*지점|해당\s*지점).*(확인|검수).*(완료|승인)',branch):reasons.append('branch_subject_pending')
 rights=clean(row,'사진 사용 허락·라이선스');evidence=public_url(clean(row,'허락 근거 URL'))
 cc0=bool(re.search(r'CC\s*0|public domain',rights,re.I))
 by=bool(re.search(r'CC\s*BY(?:\s|$)',rights,re.I))and not re.search(r'NC|ND',rights,re.I)
 written=bool(re.search(r'(허락|허가).*(확인|완료)',rights))
 credit=clean(row,'사진 표시 크레딧')
 if BLOCKED.search(rights)or not evidence or not(cc0 or written or(by and credit)):reasons.append('permission_evidence_pending')
 width=integer(row.get('가로 px'));height=integer(row.get('세로 px'))
 if width<=0 or height<=0:reasons.append('dimensions_missing')
 category=clean(row,'자료 구분')+' '+branch
 kind='menu'if re.search(r'메뉴판|가격표|메뉴\s*이미지',category)else 'general'if re.search(r'일반\s*사진|시설|외관|실내|시술|음식|음료|갤러리',category)else ''
 if not kind:reasons.append('photo_type_pending')
 notes=clean(row,'추가 확인')
 if notes not in ('','없음','해당없음','완료')and BLOCKED.search(notes):reasons.append('review_notes_pending')
 if re.search(r'실패|오류|404|403|접속\s*불가',clean(row,'접속·검증 상태')):reasons.append('image_response_failed')
 if reasons:return None,reasons
 return {'id':clean(row,'출처ID'),'url':url,'width':width,'height':height,
         'sourceUrl':public_url(clean(row,'출처 페이지 URL')),'credit':credit,
         'kind':kind,'order':integer(row.get('추가사진 순서'))or 999999,
         '_hash':clean(row,'이미지 해시')},[]

def build_photo_index(tables):
 declared=candidate_index(tables);index=defaultdict(list);held=[];seen=defaultdict(set)
 rows=[]
 for row in tables.get('출처·이미지',[]):
  if '추가' in clean(row,'자료 구분')and clean(row,'이미지 원본 URL'):rows.append(row)
 for row in sorted(rows,key=lambda r:integer(r.get('추가사진 순서'))or 999999):
  photo,reasons=assess_photo(row,declared);source=clean(row,'업체ID')
  if reasons:held.append({'businessId':source,'photoId':clean(row,'출처ID'),'reasons':reasons});continue
  identities={canonical(photo['url'])}
  if photo['_hash']:identities.add('hash:'+photo['_hash'])
  if identities&seen[source]:
   if photo['kind']=='menu':
    for existing in index[source]:
     keys={canonical(existing['url'])}
     if existing['_hash']:keys.add('hash:'+existing['_hash'])
     if identities&keys:existing.update(photo)
   continue
  seen[source].update(identities);index[source].append(photo)
 counts=Counter(row['업체ID']for row in rows)
 declared_counts={}
 states=Counter()
 for tab in ('마사지','네일','이발소','맛집','카페'):
  for r in tables.get(tab,[]):
   source=clean(r,'업체ID')
   if source and integer(r.get('추가사진 후보 수')):
    declared_counts[source]=max(declared_counts.get(source,0),integer(r.get('추가사진 후보 수')))
    if clean(r,'추가사진 수집 상태'):states[clean(r,'추가사진 수집 상태')]+=1
 audit={'declaredCandidateBusinesses':len(declared_counts),'candidateUrlBusinesses':len(declared),'candidateUrlCount':sum(len(v)for v in declared.values()),'collectionStates':dict(states),'candidatePhotos':len(rows),'candidateBusinesses':len(counts),'businessesWithThreeOrMore':sum(n>=3 for n in counts.values()),
        'approvedPhotos':sum(len(p)for p in index.values()),'approvedBusinesses':len(index),
        'heldPhotos':len(held),'holdReasons':dict(Counter(reason for row in held for reason in row['reasons'])),'held':held}
 return index,audit

def attach_photo_galleries(places,tables):
 index,_=build_photo_index(tables)
 for place in places:
  primary=canonical(place.get('imageOriginal')or place.get('image',''))
  place['gallery']=[];place['menuImages']=[]
  for photo in index.get(str(place.get('sourceId','')),[]):
   if photo['kind']=='general'and canonical(photo['url'])==primary:continue
   entry={k:v for k,v in photo.items()if k not in ('_hash','kind','order')}
   place['menuImages'if photo['kind']=='menu'else'gallery'].append(entry)
 return places
