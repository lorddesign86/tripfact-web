"""Operator edits are layered after sheet publication; city and source IDs never change."""
from urllib.parse import urlencode,quote
FIELDS=('adminIntro','adminTags','menuSummary','hours','map','booking','name','region','address','adminHidden','hiddenCategories','menuPhotos','serviceMenus')
def apply_business_edits(places,rows,city,origin,menu_defaults=None):
 index={r['business_id']:r for r in rows if r.get('city_slug')==city}
 pairs={(p.get('sourceId'),p.get('category'))for p in places}
 for row in index.values():
  seed=(row.get('patch')or{}).get('createdBusiness')
  if not isinstance(seed,dict):continue
  for category in dict.fromkeys(seed.get('categories',[])):
   if category not in ('마사지','네일','이발관','맛집','카페')or(row['business_id'],category)in pairs:continue
   suffix={'마사지':'massage','네일':'nail','이발관':'barber','맛집':'dining','카페':'cafe'}[category]
   places.append({'id':row['business_id']+'-'+suffix,'sourceId':row['business_id'],'name':seed['name'],'short':seed['name'],'category':category,'type':'dining'if category in ('맛집','카페')else'spa','city':city,'loc':seed['region'],'region':seed['region'],'address':seed.get('address',''),'image':'','imageThumb':'','imageOriginal':'','imageSource':'','map':'','booking':'','kakao':'','reservation':'','website':'','menus':[],'price':'','priceValue':None,'priceBasis':'','services':'','menuSummary':'','hours':'','pickup':'','tags':[],'featureTags':[],'reviewEvidence':[],'rating':None,'reviews':None,'badge':category,'isOperatorBusiness':True})
   pairs.add((row['business_id'],category))
 for p in places:
  row=index.get(p.get('sourceId'))
  if not row:continue
  patch=row.get('patch')or {};p['editorBase']={k:p.get(k)for k in (*FIELDS,'menus','price','priceValue','priceBasis','image','imageThumb','imageOriginal','imageSource','short','loc','menuImages')}
  for k in FIELDS:
   if k in patch:p[k]=patch[k]
  if 'name'in patch:p['short']=patch['name']
  if 'region'in patch:p['loc']=patch['region']
  image=patch.get('imageUrl','')
  if patch.get('imagePath'):image=origin.rstrip('/')+'/storage/v1/object/public/tripfact-business-photos/'+quote(patch['imagePath'],safe='/')
  if 'imageUrl'in patch or 'imagePath'in patch:
   p.update(image=image,imageThumb=image,imageOriginal=image,imageSource='')
  if 'menuPhotos'in patch:
   p['menuImages']=[{'url':origin.rstrip('/')+'/storage/v1/object/public/tripfact-business-photos/'+quote(x['path'],safe='/')if x.get('path')else x.get('url',''),'alt':'메뉴판·가격표'}for x in patch['menuPhotos']]
  apply_service_menus(p)
  p['editVersion']=row.get('version',0)
 for p in places:
  if menu_defaults and p.get('category')in menu_defaults:p['menuDisplayDefaults']=menu_defaults[p['category']]
  apply_service_menus(p)
 return places

def load_business_edits(places,city):
 import os
 if not os.environ.get('NEXT_PUBLIC_SUPABASE_URL')or not os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'):return places
 try:
  from article_service import database,database_url
  rows=database('tripfact_business_edits?'+urlencode({'select':'city_slug,business_id,patch,version','city_slug':'eq.'+city}))
  try:defaults={r['category']:r['menus']for r in database('tripfact_menu_defaults?select=category,menus')}
  except Exception:defaults={}
  return apply_business_edits(places,rows,city,database_url(),defaults)
 except Exception as error:
  print('Business edits unavailable: '+type(error).__name__,flush=True);return places


def apply_service_menus(p):
 import re
 valid=lambda x:type(x)is int and 0<x<=1000000000
 key=lambda x:re.sub(r'\s+','',str(x)).lower()
 edited=isinstance(p.get('serviceMenus'),list)and any(m.get('category')==p.get('category')for m in p['serviceMenus'])
 available=[m for m in p['serviceMenus']if m.get('category')==p.get('category')]if edited else[dict(name=m['name'],price=m.get('low'))for m in p.get('menus',[])if m.get('low')==m.get('high')and valid(m.get('low'))]
 menus=[m for m in available if valid(m.get('price'))]
 if edited:p['menus']=[dict(name=m['name'],low=m['price'],high=m['price'],conditions='',source='',date='')for m in menus]
 custom=any(type(m.get('featured'))is bool or type(m.get('primary'))is bool for m in available)
 template=p.get('menuDisplayDefaults')
 if not edited and not template and not custom and p.get('category')!='마사지':return
 template=template if template is not None else[dict(name='아로마 60분',featured=True,primary=True),dict(name='아로마 90분',featured=True,primary=False)]if p.get('category')=='마사지'else[]
 featured=[m for m in menus if m.get('featured')]if custom else[next((m for m in menus if key(m['name'])==key(t['name'])),None)for t in template if t.get('featured')]
 featured=[m for m in featured if m]
 main=next((m for m in menus if m.get('primary')),None)if custom else next((m for t in template if t.get('primary')for m in menus if key(m['name'])==key(t['name'])),None)
 main=main or next(iter(featured),None)or(next((m for n in (60,90)for m in menus if key(m['name'])=='아로마'+str(n)+'분'),None)if p.get('category')=='마사지'else None)or next(iter(menus),None)
 p.update(priceValue=main['price']if main else None,price=f"{main['price']:,}동"if main else'',priceBasis=main['name']if main else'')
