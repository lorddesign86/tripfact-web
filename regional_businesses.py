"""City-scoped directory rows. No fallback to another city's businesses."""
import hashlib,re
from urllib.parse import urlparse,unquote
REGIONS={
 'nhatrang':['시내·쩐푸 해변','북부·혼총·팜반동','남부·안비엔·빈펄 선착장','깜란·바이다이','서부·주거지역'],
 'phuquoc':['즈엉동·야시장','롱비치·바이쯔엉','옹랑·꾸어깐','북부·그랜드월드·간저우','남부·안터이·선셋타운']}
CATEGORIES={'마사지':'마사지','네일':'네일','이발소':'이발관','맛집':'맛집','카페':'카페'}
def clean(value):return str(value or '').strip()
def url(value):
 value=clean(value);u=urlparse(value)
 return value if u.scheme=='https' and u.hostname else ''
def public_text(value):
 return ' · '.join(part.strip(' .·') for part in re.split(r'(?<=[.!?])\s*|\n',clean(value)) if part.strip(' .·') and not re.search(r'미확인|확인\s*필요|추가\s*확인|검토|수집\s*상태|미완료',part))
def number(value):
 try:return float(clean(value).replace(',',''))
 except ValueError:return None
def build_regional_places(tables,city):
 places=[];seen=set();excluded=[];issues=[]
 for tab,category in CATEGORIES.items():
  for r in tables.get(tab,[]):
   source=clean(r.get('업체ID'));name=clean(r.get('업체명'));reason=''
   if not source or not name:reason='업체ID 또는 업체명 없음'
   elif clean(r.get('도시')) not in ('',{'nhatrang':'나트랑','phuquoc':'푸꾸옥'}[city]):reason='도시 불일치'
   elif clean(r.get('사이트 노출 대상')) in ('숨김','제외','비공개'):reason='운영자 숨김'
   elif (tab,source) in seen:reason='같은 업종 내 업체ID 중복'
   if reason:excluded.append({'city':city,'category':category,'businessId':source,'reason':reason});continue
   seen.add((tab,source));map_url=url(r.get('구글지도 URL'))
   if map_url and re.search(r'da[ +_-]*nang|다낭|hoi[ +_-]*an|호이안',unquote(map_url),re.I):
    issues.append({'city':city,'category':category,'businessId':source,'reason':'다른 도시를 가리키는 지도 링크 숨김','url':map_url});map_url=''
   if not map_url and not clean(r.get('주소')):
    excluded.append({'city':city,'category':category,'businessId':source,'reason':'지도와 주소 모두 없음'});continue
   website=url(r.get('공식 홈페이지'));kakao=url(r.get('카카오톡 예약 URL'));reservation=url(r.get('예약 URL'))
   menus=[];raw=clean(r.get('가격'));status=clean(r.get('가격 확인 상태'));date=clean(r.get('상세정보 확인일'))[:10];source_url=url(r.get('상세정보 출처 URL'))or website
   if clean(r.get('통화'))=='VND' and '확인' in status and not re.search(r'필요|미확인|검토',status):
    for part in raw.split('/'):
     m=re.fullmatch(r'\s*(.*?)\s*(\d+)분\s*([\d,]+)\s*(?:VND|동)?\s*',part)
     if m:
      price=int(m[3].replace(',',''));minutes=int(m[2]);menus.append({'name':(m[1]+m[2]+'분').strip(),'service':'','minutes':minutes,'low':price,'high':price,'conditions':public_text(r.get('시간·인원 기준')),'date':date,'source':source_url})
    if not menus and re.fullmatch(r'[\d,]+',raw):
     price=int(raw.replace(',',''));menus=[{'name':public_text(r.get('코스·메뉴'))or '표시 가격','minutes':None,'low':price,'high':price,'conditions':public_text(r.get('시간·인원 기준')),'date':date,'source':source_url}]
   rating=number(r.get('구글평점'));reviews=number(r.get('구글리뷰수'))
   photo_state=clean(r.get('대표사진 사용 상태'))+' '+clean(r.get('이미지 확인상태'))
   approved=bool(re.search(r'게시\s*승인|사용\s*승인|검수\s*완료',photo_state))and not re.search(r'필요|미확인|후보|대기|보류',photo_state)
   image=url(r.get('메인이미지 원본 URL')) if approved else ''
   region=clean(r.get('지역'));menu=public_text(r.get('대표메뉴·구글 주요언급')or r.get('코스·메뉴'));services=public_text(r.get('업체특징·선택 포인트')or r.get('시설·서비스'))
   places.append({'id':'sheet-'+hashlib.sha256((city+':'+tab+':'+source).encode()).hexdigest()[:20],'sourceId':source,'city':city,'name':name,'short':name,'category':category,'type':'dining'if tab in ('맛집','카페')else'spa','loc':region,'region':region,'address':clean(r.get('주소')),'map':map_url,'booking':kakao or reservation or website,'kakao':kakao,'reservation':reservation,'website':website,'rating':rating if rating and 0<rating<=5 else None,'reviews':int(reviews)if reviews and reviews>0 else None,'ratingBasis':'공개 디렉터리 기준'if rating or reviews else '','ratingSource':url(r.get('평점·리뷰 수 출처 URL')),'hours':clean(r.get('영업시간')),'phone':clean(r.get('전화')),'pickup':public_text(r.get('픽업·드롭')),'services':services,'menuSummary':menu,'cuisine':public_text(r.get('음식국가·종류')),'foodCardLines':list(dict.fromkeys(v for v in (menu,services)if v)),'tags':[category],'featureTags':[],'menus':menus,'priceValue':None,'price':'','priceBasis':'','image':image,'imageSource':url(r.get('이미지 출처 URL'))if image else'','reviewEvidence':[],'badge':category,'date':date})
 return places,{'excluded':excluded,'linkIssues':issues}
