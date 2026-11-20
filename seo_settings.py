"""City-scoped SEO settings, rendered into HTML before crawlers receive it."""
import json,re
from html import escape
from urllib.parse import urlencode
NAMES={'danang':'다낭','nhatrang':'나트랑','phuquoc':'푸꾸옥'}
def defaults(city):
 name=NAMES[city]
 return dict(site_name='지금 여행중',title='지금 여행중 · '+name+' | 환율·쇼핑시세·날씨·현지 여행정보',description=name+' 여행에 필요한 환전 사례 평균, 쇼핑 참고가격, 지역별 날씨와 업체정보를 한곳에서 확인하세요. 사고 싶은 품목은 내 찜에 모아 여행 목록으로 저장하고 공유할 수 있습니다.',intro='지금 여행중은 여행지에서 잘 놀고 알뜰하게 쓰는 데 필요한 정보를 모으는 여행 커뮤니티입니다. '+name+'의 환율·쇼핑시세·날씨를 살펴보고, 업체정보와 현지 이야기를 확인하며 나만의 여행 목록을 만들어 보세요.',keywords=name+' 여행, '+name+' 환율, '+name+' 환전, '+name+' 쇼핑시세, '+name+' 날씨, '+name+' 마사지, '+name+' 맛집, 지금 여행중',og_title=name+' 여행, 필요한 정보만 쏙 | 지금 여행중',og_description='환율부터 쇼핑시세·날씨까지 한눈에. 내 찜에 담아 나만의 '+name+' 여행 목록을 만들어 보세요.',og_image='__DEFAULT__',google_verification='',naver_verification='',indexable=True)
def load(city):
 data=defaults(city)
 from article_service import public_origin
 data['og_image']=public_origin()+'/assets/branding/'+city+'-og.png'
 try:
  from article_service import database
  rows=database('tripfact_seo_settings?'+urlencode({'select':'settings','city_slug':'eq.'+city}))
  if rows:data.update({k:v for k,v in rows[0]['settings'].items()if k in data and not(k=='og_image'and not v)})
 except Exception:pass
 return data

def apply(document,city,article=False):
 d=load(city)
 # Article-specific title, description and cover remain authoritative.
 if not article:
  document=re.sub(r'<title>.*?</title>','<title>'+escape(d['title'])+'</title>',document,count=1,flags=re.S)
  for attr,key in [('name','description'),('property','og:title'),('property','og:description')]:
   document=re.sub(r'<meta\s+'+attr+r'="'+re.escape(key)+r'"[^>]*>','',document,flags=re.I)
 tags=[]
 def meta(attr,key,value):
  if value:tags.append('<meta '+attr+'="'+key+'" content="'+escape(str(value),quote=True)+'">')
 if not article:
  meta('name','description',d['description']);meta('property','og:title',d['og_title']or d['title']);meta('property','og:description',d['og_description']or d['description'])
 meta('property','og:site_name',d['site_name']);meta('property','og:locale','ko_KR')
 meta('name','keywords',d['keywords'])
 meta('name','google-site-verification',d['google_verification']);meta('name','naver-site-verification',d['naver_verification'])
 meta('name','robots','index,follow,max-image-preview:large'if d['indexable']else'noindex,nofollow')
 image=d['og_image']
 existing=re.search(r'<meta property="og:image" content="([^"]+)"',document)
 if existing:image=existing[1]
 elif image:meta('property','og:image',image)
 meta('name','twitter:card','summary_large_image'if image else'summary')
 if image:meta('name','twitter:image',image)
 if not article:
  meta('name','twitter:title',d['og_title']or d['title']);meta('name','twitter:description',d['og_description']or d['description'])
 organization={'@context':'https://schema.org','@type':'Organization','name':d['site_name'],'description':d['intro']}
 tags.append('<script type="application/ld+json">'+json.dumps(organization,ensure_ascii=False).replace('<','\\u003c')+'</script>')
 return document.replace('</head>',''.join(tags)+'</head>',1)
