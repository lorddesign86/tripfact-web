"""Operator edits are layered after sheet publication; city and source IDs never change."""
from urllib.parse import urlencode,quote
FIELDS=('adminIntro','adminTags','menuSummary','hours','map','booking','name','region','address')
def apply_business_edits(places,rows,city,origin):
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
  patch=row.get('patch')or {};p['editorBase']={k:p.get(k)for k in (*FIELDS,'image','imageThumb','imageOriginal','imageSource','short','loc')}
  for k in FIELDS:
   if k in patch:p[k]=patch[k]
  if 'name'in patch:p['short']=patch['name']
  if 'region'in patch:p['loc']=patch['region']
  image=patch.get('imageUrl','')
  if patch.get('imagePath'):image=origin.rstrip('/')+'/storage/v1/object/public/tripfact-business-photos/'+quote(patch['imagePath'],safe='/')
  if 'imageUrl'in patch or 'imagePath'in patch:
   p.update(image=image,imageThumb=image,imageOriginal=image,imageSource='')
  p['editVersion']=row.get('version',0)
 return places

def load_business_edits(places,city):
 import os
 if not os.environ.get('NEXT_PUBLIC_SUPABASE_URL')or not os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'):return places
 try:
  from article_service import database,database_url
  rows=database('tripfact_business_edits?'+urlencode({'select':'city_slug,business_id,patch,version','city_slug':'eq.'+city}))
  return apply_business_edits(places,rows,city,database_url())
 except Exception as error:
  print('Business edits unavailable: '+type(error).__name__,flush=True);return places
