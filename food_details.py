"""Selected food business facts; retain source limitations, never invent prices."""
import re
from business_overrides import public_url

FIELDS=('대표메뉴·구글 주요언급','업체특징·선택 포인트','구글 후기 주요언급 수치','특징 수집상태','특징 확인일','구글 특징 근거 URL','에어컨·좌석 구분','에어컨 확인 근거','커피·디저트 강점','뷰·사진 포인트','좌석·가족·작업 적합성','혼잡·방문 전 확인')

def parts(value):return [x.strip()for x in re.split(r'\s+·\s+|\n|;',str(value))if x.strip()]

def mention_pairs(value):
 result=[]
 for item in parts(value):
  match=re.fullmatch(r'(.+?)\s*([0-9][0-9,]*)건',item)
  if match:
   pair=(match[1].strip(),int(match[2].replace(',','')))
   if pair not in result:result.append(pair)
 return result

def display_mentions(value,counts):
 known=set(mention_pairs(counts));result=[]
 for item in parts(value):
  match=re.fullmatch(r'(.+?)\s*([0-9][0-9,]*)건',item)
  if match and known:
   item=f"구글 후기에서 {match[1].strip()} {int(match[2].replace(',','')):,}건 언급"
  if item not in result:result.append(item)
 return ' · '.join(result)

def card_lines(values):
 lines=[]
 for value in values:
  for item in parts(value):
   if re.search(r'확인\s*필요|미확인|추가\s*확인|대조\s*필요|대표\s*여부|https?://',item):continue
   if item not in lines and not any(item in existing or existing in item for existing in lines):lines.append(item)
 return lines[:2]

def ranked_menus(menu,counts):
 # Explicit menu entries plus recognizable dishes in the wider keyword table.
 nonmenu=re.compile(r'staff|service|owner|customer|view|seat|music|atmosphere|revisit|crowd|price|menu|restaurant|coffee shop|taste|friendly|delicious|직원|친절|사장|주인|고객|한국인|전망|좌석|음악|분위기|재방문|가격|서비스|메뉴',re.I)
 dish=re.compile(r'반쎄오|반세오|분짜|반미|모닝글로리|쌀국수|분보|까오러우|화이트로즈|완탕|볶음밥|스프링롤|스프링 롤|춘권|죽|국수|해산물|새우|가리비|굴|랍스터|로브스터|쭈꾸미|문어|조개|피자|파스타|스테이크|초밥|사시미|커피|라떼|카푸치노|아메리카노|에스프레소|케이크|크로와상|크루아상|토스트|샌드위치|빙수|스무디|주스|와플|푸딩|rice|noodle|spring roll|porridge|banh|bánh|pho|phở|bun cha|bún chả|cao lau|cao lầu|mi quang|mì quảng|wonton|pancake|pizza|pasta|steak|sushi|sashimi|shrimp|prawn|lobster|scallop|clam|squid|octopus|curry|madras|tikka|naan|coffee|latte|cappuccino|espresso|cake|croissant|toast|sandwich|smoothie|juice|waffle|pudding',re.I)
 chosen={}
 for label,count in mention_pairs(menu):
  if not nonmenu.search(label):chosen[label]=max(chosen.get(label,0),count)
 for label,count in mention_pairs(counts):
  if label in menu or dish.search(label):
   if not nonmenu.search(label):chosen[label]=max(chosen.get(label,0),count)
 return [{'name':label,'mentions':count}for label,count in sorted(chosen.items(),key=lambda x:-x[1])]

def build_food_info(row):
 detail={key:str(row.get(key,'')).strip()for key in FIELDS if str(row.get(key,'')).strip()}
 menu=detail.get('대표메뉴·구글 주요언급')or str(row.get('코스·메뉴','')).strip()
 choice=detail.get('업체특징·선택 포인트')or str(row.get('시설·서비스','')).strip()
 counts=detail.get('구글 후기 주요언급 수치','')
 display=display_mentions(menu,counts)
 feature=display_mentions(choice,counts)
 cafe_values=[detail.get(k,'')for k in ['커피·디저트 강점','뷰·사진 포인트','에어컨·좌석 구분','좌석·가족·작업 적합성']]
 # Separate menu mentions from verified representative dishes. No verification badge is generated.
 lines=card_lines(card_lines([display])[:1]+card_lines([feature,*cafe_values,str(row.get('음식국가·종류',''))]))
 urls=[]
 for key in ['구글 특징 근거 URL','특징 근거 URL']:
  for value in re.findall(r'https://[^\s<>]+',str(row.get(key,''))):
   url=public_url(value)
   if url and url not in urls:urls.append(url)
 return {'menuSummary':menu,'menuDisplay':display,'services':choice,'choiceDisplay':feature,'foodDetail':detail,'foodCardLines':lines,
         'mentionDisplay':'\n'.join(f'구글 후기에서 {label} {count:,}건 언급'for label,count in mention_pairs(counts)),
         'featureUrls':urls,'menuRanking':ranked_menus(menu,counts)}
