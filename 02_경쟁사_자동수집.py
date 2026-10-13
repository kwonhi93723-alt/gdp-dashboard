"""Menswear Intel competitor collector: add this file under pages/ in a Streamlit repository."""
import io, json, re, time, hashlib
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

BRANDS = {
 '캠브리지 멤버스': ('https://www.kolonmall.com/Brands/CAMBRIDGE-MEMBERS', ('kolonmall.com',)),
 '갤럭시': ('https://m.ssfshop.com/Galaxy/main?brandShopNo=BDMA04A01&brndShopId=HMBGA', ('ssfshop.com',)),
}
CATEGORIES = {'SUIT':'수트','JACKET':'재킷','OUTER':'아우터','TOP':'상의','PANTS':'팬츠','ACC':'액세서리', '셔츠':'셔츠','니트':'니트','코트':'아우터','자켓':'재킷','재킷':'재킷','팬츠':'팬츠','수트':'수트','정장':'수트','아우터':'아우터','티셔츠':'상의'}
MATERIALS=['캐시미어','울','모','실크','린넨','리넨','마','코튼','면','폴리에스터','폴리','나일론','레이온','비스코스','아세테이트','트리아세테이트','알파카','모헤어','가죽','스웨이드','다운','구스','덕다운','텐셀','라이오셀','스판','엘라스테인']
COLS=['brand','season','category','product_name','product_id','price','list_price','material','composition','url','source_category','collected_at','evidence']
UA={'User-Agent':'MenswearIntelResearch/2.0 (public-pages; low-rate; contact site owner for bulk access)'}

def allowed(url, domains):
 u=urlparse(url)
 return u.scheme in ('http','https') and any(u.hostname==d or (u.hostname or '').endswith('.'+d) for d in domains)

def normalize(url):
 u,_=urldefrag(url)
 return u.split('#')[0]

def json_objects(obj):
 if isinstance(obj,dict):
  yield obj
  for v in obj.values(): yield from json_objects(v)
 elif isinstance(obj,list):
  for v in obj: yield from json_objects(v)

def first(x):
 if isinstance(x,list): return first(x[0]) if x else ''
 if isinstance(x,dict): return str(x.get('name') or x.get('value') or '')
 return str(x or '')

def num(x):
 m=re.search(r'\d[\d,]*',str(x or ''))
 return int(m.group().replace(',','')) if m else None

def season_of(s):
 s=str(s)
 m=re.search(r'(?<!\d)(20\d{2})\s*[-_/ ]?\s*(SS|S/S|FW|F/W|SPRING|SUMMER|FALL|WINTER)(?![A-Z])',s,re.I)
 if m:return m.group(1)+('SS' if m.group(2).upper() in ('SS','S/S','SPRING','SUMMER') else 'FW')
 m=re.search(r'(?<!\d)(\d{2})\s*[-_/ ]?\s*(SS|FW)(?![A-Z])',s,re.I)
 if m:return '20'+m.group(1)+m.group(2).upper()
 return '미확인'

def category_of(text):
 t=str(text).upper()
 for k,v in CATEGORIES.items():
  if k.upper() in t:return v
 return '미분류'

def material_of(s):
 return ', '.join(dict.fromkeys(m for m in MATERIALS if m in str(s)))

def product_nodes(soup):
 for tag in soup.select('script[type="application/ld+json"]'):
  try:
   for d in json_objects(json.loads(tag.string or tag.get_text())):
    ty=d.get('@type',[]) if isinstance(d,dict) else []
    if ('Product' in ty if isinstance(ty,list) else ty=='Product'): yield d
  except (ValueError,TypeError):continue

def extract(soup,url,brand,cat):
 rows=[]
 for d in product_nodes(soup):
  name=first(d.get('name'))
  if not name:continue
  offers=d.get('offers') or {}
  if isinstance(offers,list):offers=offers[0] if offers else {}
  if not isinstance(offers,dict):offers={}
  target=urljoin(url,first(d.get('url')) or url)
  desc=first(d.get('description'))
  pid=first(d.get('sku') or d.get('productID') or '')
  rows.append(dict(brand=brand,season=season_of(' '.join([name,desc,pid,target])),category=category_of(cat+' '+name),product_name=name,product_id=pid,price=num(offers.get('price') or offers.get('lowPrice')),list_price=None,material=material_of(name+' '+desc),composition=desc[:400],url=target,source_category=cat,collected_at=datetime.now(timezone.utc).isoformat(),evidence='JSON-LD Product'))
 return rows

def links_from(soup,base,domains):
 out=[]
 for a in soup.find_all('a',href=True):
  u=normalize(urljoin(base,a['href']))
  if allowed(u,domains) and u not in out:out.append(u)
 return out

def relevant(url,brand):
 p=urlparse(url).path.lower()
 if brand=='캠브리지 멤버스':return '/brands/' in p or '/product' in p or '/products' in p
 return any(x in p for x in ('galaxy','product','goods','category','brand'))

def crawl(brand,max_pages=40,delay=1.5,extra=''):
 root,domains=BRANDS[brand]
 q=deque([(root,'전체')]);
 if extra.strip():
  for line in extra.splitlines():
   u=line.strip()
   if allowed(u,domains):q.append((u,'사용자 추가'))
 seen=set();rows=[];logs=[];discovered=0
 session=requests.Session();session.headers.update(UA)
 while q and len(seen)<max_pages:
  url,cat=q.popleft()
  if url in seen:continue
  seen.add(url)
  try:
   resp=session.get(url,timeout=18)
   if resp.status_code in (403,429):
    logs.append(f'{resp.status_code} 접근 제한: {url}');continue
   resp.raise_for_status()
   if 'html' not in resp.headers.get('content-type','').lower():continue
   soup=BeautifulSoup(resp.text,'html.parser')
   title=soup.title.get_text(' ',strip=True) if soup.title else cat
   found=extract(soup,url,brand,cat+' '+title)
   rows.extend(found)
   foundlinks=links_from(soup,url,domains)
   for link in foundlinks:
    if relevant(link,brand) and link not in seen and len(q)<max_pages*12:
     q.append((link,category_of(link+' '+title)));discovered+=1
   logs.append(f'HTTP {resp.status_code} / Product JSON-LD {len(found)} / links {len(foundlinks)}: {url}')
  except requests.RequestException as e:logs.append(f'요청 실패 {url}: {type(e).__name__}')
  time.sleep(delay)
 unique={}
 for r in rows:
  key=r['product_id'] or r['url']
  unique[(brand,key)]=r
 return pd.DataFrame(list(unique.values()),columns=COLS),logs,len(seen),discovered

st.set_page_config(page_title='경쟁사 자동 수집',page_icon='🧥',layout='wide')
st.title('🧥 갤럭시 · 캠브리지 멤버스 자동 수집')
st.caption('Menswear Intel v2 확장 페이지 · 공개 HTML / Product JSON-LD 기반 · 전체 시즌(접근 가능한 상품 한정)')
st.warning('공식몰에서 자동화 접근을 제한하거나 JavaScript로만 상품을 표시하면 결과가 0건일 수 있습니다. 0건은 상품이 없다는 뜻이 아닙니다. 수집 결과는 표본이며 전수조사로 단정하지 마세요.')
brand=st.selectbox('조사 브랜드',list(BRANDS))
max_pages=st.slider('최대 방문 페이지',5,200,40,5)
delay=st.slider('요청 간 대기(초)',1.0,5.0,1.5,0.5)
extra=st.text_area('추가 카테고리 / 상품 목록 URL (선택, 한 줄에 하나)',height=100,placeholder='공식몰에서 카테고리 주소를 복사하여 붙여넣으세요')
if st.button('공개 상품 수집 시작',type='primary'):
 with st.spinner('공개 페이지 확인 중...'):
  df,logs,visited,discovered=crawl(brand,max_pages,delay,extra)
  st.session_state['collector_result']=df
  st.session_state['collector_logs']=logs
  st.session_state['collector_stats']=(visited,discovered,brand)
if 'collector_result' in st.session_state:
 df=st.session_state['collector_result'];visited,discovered,selected=st.session_state['collector_stats']
 a,b,c=st.columns(3);a.metric('방문 페이지',visited);b.metric('발견 링크(중복 포함)',discovered);c.metric('상품 추출',len(df))
 if len(df):
  st.subheader('카테고리 × 시즌')
  st.dataframe(pd.crosstab(df.category,df.season),use_container_width=True)
  st.subheader('상품 데이터')
  st.dataframe(df,use_container_width=True,hide_index=True)
  csv=df.to_csv(index=False).encode('utf-8-sig')
  st.download_button('CSV 다운로드 (기존 DB 가져오기용)',csv,file_name=f'{selected}_products.csv',mime='text/csv')
  buf=io.BytesIO()
  with pd.ExcelWriter(buf,engine='openpyxl') as w:
   df.to_excel(w,index=False,sheet_name='products')
   pd.crosstab(df.category,df.season).to_excel(w,sheet_name='category_season')
  st.download_button('엑셀 다운로드',buf.getvalue(),file_name=f'{selected}_products.xlsx')
 else:st.error('구조화된 Product 데이터 0건. 접근 제한 또는 JavaScript 렌더링 가능성이 있습니다. 추가 URL을 입력하거나 공식몰 데이터를 CSV로 보완하세요.')
 with st.expander('수집 진단 로그'):
  st.code('\n'.join(st.session_state['collector_logs']))
st.info('주의: 이 페이지는 기존 app.py의 DB를 직접 변경하지 않습니다. CSV를 다운로드해 기존 상품 DB 업로드 기능으로 병합하세요. 서버 재시작 시 세션 데이터는 사라질 수 있습니다.')
