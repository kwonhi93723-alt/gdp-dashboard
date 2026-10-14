"""Menswear Intel v5.1: public-source discovery, evidence-first product research.
Add to Streamlit pages/. No authentication or bypass of blocked sites.
Dependencies: streamlit pandas requests beautifulsoup4 openpyxl
Optional Streamlit secrets: GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID.
"""
import io
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, quote, parse_qs, unquote
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

UA = 'MenswearIntelResearch/5.1 (+public-source-research; respectful-low-rate)'
HEADERS = {'User-Agent': UA, 'Accept': 'text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8'}
BRANDS = ['닥스 남성', '캠브리지 멤버스', '갤럭시', '타임옴므', '시스템옴므', '솔리드옴므']
SEARCH_NAMES = {'닥스 남성':'닥스 남성', '캠브리지 멤버스':'캠브리지 멤버스 남성', '갤럭시':'갤럭시 남성복', '타임옴므':'타임옴므', '시스템옴므':'시스템옴므', '솔리드옴므':'솔리드옴므'}
TYPES = {
 '초어 재킷':r'초어|chore|워크.?재킷|work.?jacket',
 '봄버 재킷':r'봄버|bomber|ma[- ]?1',
 '해링턴 재킷':r'해링턴|헤링턴|harrington',
 '블루종':r'블루종|blouson',
 '테일러드 재킷':r'블레이저|테일러드|blazer|tailored',
 '필드·사파리':r'필드|사파리|field.?jacket|safari|m[- ]?65',
 '셔츠 재킷':r'셔츠.?재킷|셔츠.?자켓|오버셔츠|overshirt|shirt.?jacket',
 '트러커·데님':r'트러커|trucker|데님.?재킷|denim.?jacket',
 '퀼팅':r'퀼팅|quilted',
 '레더·스웨이드':r'레더|가죽|스웨이드|leather|suede',
 '코트':r'코트|coat|트렌치|trench',
 '팬츠':r'팬츠|바지|슬랙스|trousers|pants',
 '셔츠':r'셔츠|shirt',
 '니트':r'니트|스웨터|knit|sweater',
}
FIBERS = r'(울|양모|캐시미어|면|코튼|린넨|리넨|실크|폴리에스터|나일론|레이온|비스코스|폴리우레탄|스판덱스|알파카|모헤어|wool|cashmere|cotton|linen|silk|polyester|nylon|viscose|elastane)'
COLS = ['brand','season','category','jacket_type','product_name','product_id','price','list_price','material','composition','image_url','url','source_category','collected_at','evidence','source_type','verification_status','season_evidence','search_query','snippet']

def clean(s):
 return re.sub(r'\s+',' ',str(s or '')).strip()

def category(t):
 t=clean(t)
 for k,p in TYPES.items():
  if re.search(p,t,re.I):return ('재킷' if k not in ('코트','팬츠','셔츠','니트') else k), (k if k not in ('코트','팬츠','셔츠','니트') else '')
 return '미분류',''

def season(t):
 t=clean(t)
 m=re.search(r'(?<!\d)(20\d{2}|\d{2})\s*[-_/ ]?\s*(S/?S|F/?W|SPRING|SUMMER|FALL|WINTER)(?![A-Za-z])',t,re.I)
 if not m:return '미확인',''
 year=m.group(1) if len(m.group(1))==4 else '20'+m.group(1)
 return year+('SS' if m.group(2).upper() in ('SS','S/S','SPRING','SUMMER') else 'FW'),m.group(0)

def compositions(t):
 # Explicit fiber-percent statements only; don't mistake discount percentages for fiber content.
 pairs=re.findall(r'(?i)'+FIBERS+r'\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*%',t)
 pairs=[(f,p) for f,p in pairs if 0<float(p)<=100]
 return ', '.join(f'{f} {p}%' for f,p in pairs[:12])

def safe_url(url):
 p=urlparse(url)
 return p.scheme in ('http','https') and bool(p.hostname) and not (p.hostname in ('localhost','127.0.0.1') or p.hostname.endswith('.local'))

@st.cache_data(ttl=3600,show_spinner=False)
def robots_check(url):
 p=urlparse(url); robots=f'{p.scheme}://{p.netloc}/robots.txt'
 try:
  r=requests.get(robots,headers=HEADERS,timeout=10)
  if r.status_code==404:return True,'robots.txt 없음(404)'
  if r.status_code!=200:return False,f'robots.txt 확인 불가 HTTP {r.status_code}'
  rp=RobotFileParser();rp.parse(r.text.splitlines())
  return rp.can_fetch(UA,url),'robots.txt 규칙 확인'
 except requests.RequestException as e:return False,f'robots.txt 요청 실패: {type(e).__name__}'

def product_nodes(soup):
 for s in soup.select('script[type="application/ld+json"]'):
  try: obj=json.loads(s.string or s.get_text())
  except (ValueError,TypeError):continue
  stack=[obj]
  while stack:
   x=stack.pop()
   if isinstance(x,list):stack.extend(x)
   if isinstance(x,dict):
    typ=x.get('@type',[]);typ=[typ] if isinstance(typ,str) else typ
    if 'Product' in typ:yield x
    stack.extend(v for v in x.values() if isinstance(v,(dict,list)))

def text_value(x):
 if isinstance(x,list):return text_value(x[0]) if x else ''
 if isinstance(x,dict):return text_value(x.get('name') or x.get('url') or x.get('value'))
 return clean(x)

def number(v):
 m=re.search(r'\d[\d,]*',str(v or ''))
 return int(m.group().replace(',','')) if m else None

def search_bing_rss(query,limit,logs):
 url='https://www.bing.com/search?format=rss&q='+quote(query)
 ok,why=robots_check(url)
 if not ok:logs.append('Bing RSS 접근 생략: '+why);return []
 try:
  r=requests.get(url,headers=HEADERS,timeout=15)
  r.raise_for_status();root=ET.fromstring(r.content)
  result=[]
  for x in root.findall('.//item')[:limit]:
   title=clean(x.findtext('title'));link=clean(x.findtext('link'))
   snippet=clean(BeautifulSoup(x.findtext('description') or '','html.parser').get_text(' ',strip=True))
   if safe_url(link):result.append((title,link,snippet,'Bing RSS'))
  return result
 except (requests.RequestException,ET.ParseError) as e:
  logs.append('Bing RSS 검색 실패: '+type(e).__name__);return []

def search_google_cse(query,limit,logs):
 try:key=st.secrets.get('GOOGLE_CSE_API_KEY','');cx=st.secrets.get('GOOGLE_CSE_ID','')
 except Exception:key=cx=''
 if not key or not cx:return []
 try:
  r=requests.get('https://www.googleapis.com/customsearch/v1',params={'key':key,'cx':cx,'q':query,'num':min(10,limit)},timeout=15)
  r.raise_for_status()
  return [(clean(x.get('title')),x.get('link',''),clean(x.get('snippet')),'Google CSE') for x in r.json().get('items',[]) if safe_url(x.get('link',''))]
 except requests.RequestException as e:logs.append('Google 검색 API 실패: '+type(e).__name__);return []

def discover(brand,years,per_query,delay,logs):
 found=[]; queries=[]
 for year in years:
  for term in ['재킷 블루종','헤링턴 초어 사파리','코트 점퍼','니트 셔츠 팬츠']:
   queries.append(f'{SEARCH_NAMES[brand]} {year} {term} 상품')
 for q in queries:
  hits=search_google_cse(q,per_query,logs)
  if not hits:hits=search_bing_rss(q,per_query,logs)
  logs.append(f'검색 후보 {len(hits)}건: {q}')
  found.extend([(q,*hit) for hit in hits]);time.sleep(delay)
 return found

def build_rows(brand,hits,fetch_limit,delay,logs):
 now=datetime.now(timezone.utc).isoformat();rows=[];seen=set();fetched=0
 for query,title,url,snippet,source in hits:
  if url in seen:continue
  seen.add(url)
  if not safe_url(url):continue
  name=title;desc=snippet;img='';pid='';price=None;detail_source='검색 결과';verified='검색 후보 (상품 미검증)';page_text=''
  if fetched<fetch_limit:
   ok,why=robots_check(url)
   if ok:
    try:
     r=requests.get(url,headers=HEADERS,timeout=14)
     if r.status_code==200 and 'html' in r.headers.get('content-type','').lower():
      fetched+=1;soup=BeautifulSoup(r.text,'html.parser')
      p=next(product_nodes(soup),None)
      if p:
       name=text_value(p.get('name')) or name
       desc=text_value(p.get('description')) or desc
       pid=text_value(p.get('sku') or p.get('productID'))
       offers=p.get('offers') or {};offers=offers[0] if isinstance(offers,list) and offers else offers
       if isinstance(offers,dict):price=number(offers.get('price') or offers.get('lowPrice'))
       img=text_value(p.get('image'))
       verified='상품 구조화 데이터 확인';detail_source='Product JSON-LD'
      else:
       og=soup.find('meta',attrs={'property':'og:image'})
       if og:img=og.get('content','')
       ogt=soup.find('meta',attrs={'property':'og:title'})
       if ogt:name=clean(ogt.get('content')) or name
       detail_source='HTML 메타데이터';verified='페이지 확인 (상품 여부 미검증)'
      page_text=soup.get_text(' ',strip=True)[:12000]
     else:logs.append(f'페이지 건너뜀 HTTP {r.status_code}: {url[:100]}')
    except requests.RequestException as e:logs.append(f'상세 페이지 실패 {type(e).__name__}: {url[:100]}')
    time.sleep(delay)
   else:logs.append(f'상세 접근 생략 ({why}): {url[:100]}')
  cat,jtype=category(name+' '+desc)
  sea,ev=season(name+' '+url+' '+desc)
  comp=compositions(desc+' '+page_text)
  mats=', '.join(dict.fromkeys(f for f,_ in re.findall(r'(?i)'+FIBERS+r'\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*%',comp))) if comp else ''
  # No unsupported claim that a search result is a verified DAKS product.
  rows.append(dict(brand=brand,season=sea,category=cat,jacket_type=jtype,product_name=name,product_id=pid,price=price,list_price=None,material=mats,composition=comp,image_url=img if safe_url(img) else '',url=url,source_category='웹 검색',collected_at=now,evidence=detail_source,source_type=source,verification_status=verified,season_evidence=ev,search_query=query,snippet=snippet))
 return pd.DataFrame(rows,columns=COLS),fetched

st.set_page_config(page_title='닥스 공개자료 자동 발견',page_icon='🔎',layout='wide')
st.title('🔎 Menswear Intel v5.1 | 공개자료 자동 발견')
st.caption('상품 URL 수동 입력 없이 공개 검색 결과에서 후보를 발견하고, 접근이 허용된 페이지의 상품 정보를 확인합니다.')
st.warning('검색 결과는 상품 검증이 아닙니다. robots.txt 확인 실패·접근 제한 시 상세 페이지는 요청하지 않습니다. 과년도 전체 상품 및 당시 가격을 재현하지 않습니다.')
brand=st.selectbox('조사 브랜드',BRANDS)
years=st.multiselect('검색 연도',list(range(2026,2020,-1)),default=[2026,2025,2024])
per_query=st.slider('검색어당 최대 후보',3,10,5)
fetch_limit=st.slider('상세 페이지 확인 상한',0,50,15,5)
delay=st.slider('요청 사이 대기(초)',1.0,5.0,2.0,0.5)
if st.button('공개 웹에서 상품 후보 자동 찾기',type='primary',disabled=not bool(years)):
 logs=[]
 with st.spinner('공개 검색 결과와 접근 허용된 상품 페이지를 확인하는 중...'):
  hits=discover(brand,years,per_query,delay,logs)
  df,verified_pages=build_rows(brand,hits,fetch_limit,delay,logs)
 st.session_state['v51_data']=df;st.session_state['v51_logs']=logs;st.session_state['v51_pages']=verified_pages
if 'v51_data' in st.session_state:
 df=st.session_state['v51_data'];logs=st.session_state['v51_logs']
 a,b,c=st.columns(3)
 a.metric('검색 후보',len(df));b.metric('상세 페이지 확인',st.session_state['v51_pages']);c.metric('대표 이미지 URL',int(df.image_url.fillna('').ne('').sum()))
 if len(df):
  st.subheader('디자인 유형별 검색 후보')
  st.dataframe(df.groupby(['category','jacket_type'],dropna=False).size().reset_index(name='후보 수'),hide_index=True,use_container_width=True)
  st.subheader('검색 결과 및 검증 상태')
  st.dataframe(df[['brand','season','category','jacket_type','product_name','verification_status','url']],hide_index=True,use_container_width=True)
  st.subheader('확인된 이미지 갤러리')
  pictures=df[df.image_url.fillna('').ne('')]
  if pictures.empty:st.info('접근 가능한 상세 페이지에서 대표 이미지를 확인하지 못했습니다.')
  for i in range(0,min(30,len(pictures)),3):
   for col,(_,r) in zip(st.columns(3),pictures.iloc[i:i+3].iterrows()):
    with col:
     st.image(r.image_url,use_container_width=True)
     st.caption(r.product_name)
     st.markdown(f'[출처 페이지]({r.url})')
  st.download_button('CSV 다운로드',df.to_csv(index=False).encode('utf-8-sig'),file_name='menswear_v5_1_discovery.csv',mime='text/csv')
  buf=io.BytesIO()
  with pd.ExcelWriter(buf,engine='openpyxl') as w:df.to_excel(w,index=False,sheet_name='discovered')
  st.download_button('Excel 다운로드',buf.getvalue(),file_name='menswear_v5_1_discovery.xlsx')
 else:st.error('공개 검색 후보 0건. 검색 제공자 접근 제한 가능성이 있습니다. 검색 API 연결 여부와 진단 로그를 확인하세요.')
 with st.expander('검색·수집 진단 로그'):st.code('\n'.join(logs))
st.info('이 페이지는 기존 DB를 자동 변경하지 않습니다. Google Programmable Search API를 사용하려면 Streamlit Secrets에 GOOGLE_CSE_API_KEY와 GOOGLE_CSE_ID를 등록하세요. 미설정 시 Bing RSS를 시도하며, 검색 제공자가 차단하면 후보가 0건일 수 있습니다.')
