"""Shared city navigation and readable, server-rendered travel blog layout."""
from html import escape
from pathlib import Path
import json
NAMES={'danang':'다낭','nhatrang':'나트랑','phuquoc':'푸꾸옥'}
def article_shell(title,description,canonical,body,metadata,jsonld,city):
 name=NAMES[city];home='/'+name
 def link(tab):return home+'?tab='+tab
 items=[('여행 홈','home','⌂'),('쇼핑시세','market','🛍️'),('업체정보','explore','🌿'),('지금 '+name,'social','🌴'),('내 찜','favs','♡')]
 desktop=''.join('<a href="'+link(tab)+'">'+label+'</a>'for label,tab,_ in items[:4])
 mobile=''.join('<a href="'+link(tab)+'"><span>'+icon+'</span>'+('홈'if tab=='home'else label)+'</a>'for label,tab,icon in items)
 cities=''.join('<a href="/'+n+'"'+(' aria-current="page"'if n==name else'')+'>'+n+'</a>'for n in NAMES.values())
 css=(Path(__file__).with_name('article-layout.css')).read_text(encoding='utf-8')
 return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><meta name="description" content="'+escape(description)+'"><link rel="canonical" href="'+escape(canonical)+'"><meta property="og:title" content="'+escape(title)+'"><meta property="og:description" content="'+escape(description)+'"><meta property="og:url" content="'+escape(canonical)+'"><meta property="og:type" content="article">'+metadata+jsonld+'<link rel="icon" href="/assets/mascots/yuyu-vietnam-site.webp"><style>'+css+'</style></head><body><header class="site-top"><div class="site-header"><a class="brand" href="'+home+'"><img src="/assets/mascots/yuyu-vietnam-site.webp" alt="유유" width="48" height="54"><span><strong>지금 여행중</strong><small>'+name+'</small></span></a><nav class="desktop-nav" aria-label="주 메뉴">'+desktop+'</nav><a class="saved-top" href="'+link('favs')+'">♡ 내 찜</a><a class="member-avatar" href="'+link('member')+'" aria-label="내 계정">👤</a></div></header><div class="ribbon">작은 정보 하나가, 여행을 더 즐겁게. <b>'+name+'에서 잘 놀고 잘 쓰는 법 🌿</b></div><main class="blog-main"><nav class="breadcrumbs" aria-label="현재 위치"><a href="'+home+'">'+name+'</a><span>›</span><a href="/information?city='+city+'">여행정보</a></nav><div class="blog-content">'+body+'</div></main><footer class="site-footer"><p><b>지금 여행중 · '+name+'</b> 작은 정보로 더 즐거운 여행을.<br><span>www.지금여행중.com/'+name+'</span></p><nav class="footer-links" aria-label="사이트 안내"><a href="/information?city='+city+'">'+name+' 여행정보</a><a href="'+link('vendor')+'">업체센터 · 광고 안내</a><a href="'+link('feedback')+'">문의 · 기능 · 정보수정요청</a></nav><div class="footer-destinations"><small>다른 여행지</small>'+cities+'</div></footer><nav class="mobile-nav" aria-label="모바일 주 메뉴">'+mobile+'</nav></body></html>'
