import io, json, re, sqlite3, time, os, hmac
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

ROOT=Path(__file__).parent
DB=ROOT/'products.sqlite3'
CATS=['재킷','코트','점퍼/다운','셔츠','니트','팬츠','수트','베스트','액세서리','기타']
COLS=['brand','season','category','name','price','currency','material','color','url','image_url','source_url','collected_at','quality']
st.set_page_config(page_title='Menswear Intel',page_icon='🧥',layout='wide',initial_sidebar_state='collapsed')
st.markdown("""<style>
.block-container{padding-top:1.3rem;padding-bottom:2rem;max-width:1180px}
[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:12px}
@media(max-width:700px){.block-container{padding:0.9rem 0.8rem 2rem}h1{font-size:1.55rem!important}h2,h3{font-size:1.2rem!important}[data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:.6rem}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:calc(50% - .6rem)!important;flex:1 1 calc(50% - .6rem)!important}[data-testid="stTabs"] button{font-size:.79rem;white-space:nowrap;padding:.65rem .6rem}}
</style>""",unsafe_allow_html=True)

def setting(name,default=''):
    try: return str(st.secrets.get(name,os.environ.get(name,default)))
    except Exception: return str(os.environ.get(name,default))

PASSWORD=setting('APP_PASSWORD')
if PASSWORD:
    with st.sidebar:
        st.subheader('접속 인증')
        entered=st.text_input('비밀번호',type='password',key='app_password')
    if not hmac.compare_digest(entered,PASSWORD):
        st.title('🧥 Menswear Intel')
        st.info('좌측 메뉴에서 접속 비밀번호를 입력해주세요.')
        st.stop()
else:
    st.warning('접속 비밀번호가 설정되지 않았습니다. 공개 배포 전 APP_PASSWORD를 설정하세요.')

DATABASE_URL=setting('DATABASE_URL')
if setting('REQUIRE_CLOUD_DB')=='true' and not DATABASE_URL:
    st.error('DATABASE_URL이 없습니다. 클라우드 영구 저장 DB를 설정해주세요.')
    st.stop()


def connect():
    if DATABASE_URL:
        import psycopg
        return psycopg.connect(DATABASE_URL,connect_timeout=12)
    return sqlite3.connect(DB)

def init_db(c):
    if DATABASE_URL:
        c.execute('''CREATE TABLE IF NOT EXISTS products (brand TEXT NOT NULL,season TEXT NOT NULL,category TEXT,name TEXT,price DOUBLE PRECISION,currency TEXT,material TEXT,color TEXT,url TEXT NOT NULL,image_url TEXT,source_url TEXT,collected_at TEXT,quality TEXT,PRIMARY KEY(brand,season,url))''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS products (brand TEXT NOT NULL,season TEXT NOT NULL,category TEXT,name TEXT,price REAL,currency TEXT,material TEXT,color TEXT,url TEXT NOT NULL,image_url TEXT,source_url TEXT,collected_at TEXT,quality TEXT,PRIMARY KEY(brand,season,url))''')

def save(rows):
    with connect() as c:
        init_db(c)
        ph='%s' if DATABASE_URL else '?'
        sql='INSERT INTO products VALUES ('+','.join([ph]*len(COLS))+') ON CONFLICT(brand,season,url) DO UPDATE SET '+','.join(f'{k}=excluded.{k}' for k in COLS if k not in ('brand','season','url'))
        for r in rows:
            c.execute(sql,[r.get(k) for k in COLS])
        c.commit()

def load():
    with connect() as c:
        init_db(c)
        if DATABASE_URL:
            with c.cursor() as cur:
                cur.execute('SELECT * FROM products ORDER BY collected_at DESC')
                data=cur.fetchall()
                columns=[x.name for x in cur.description]
                return pd.DataFrame(data,columns=columns)
        return pd.read_sql_query('SELECT * FROM products ORDER BY collected_at DESC',c)

def category(s):
    s=str(s).lower()
    for name,words in [('코트',['코트','coat','trench']),('점퍼/다운',['점퍼','패딩','다운','파카','puffer','parka']),('재킷',['재킷','자켓','jacket','blazer']),('셔츠',['셔츠','shirt']),('니트',['니트','스웨터','가디건','knit','sweater','cardigan']),('팬츠',['팬츠','바지','슬랙스','pants','trouser']),('수트',['수트','정장','suit']),('베스트',['베스트','vest']),('액세서리',['벨트','타이','가방','belt','tie','bag'])]:
        if any(w in s for w in words):return name
    return '기타'

def numeric(v):
    try: return float(re.sub(r'[^\d.]','',str(v)))
    except (ValueError,TypeError): return None

def product_nodes(obj):
    if isinstance(obj,list):
        for x in obj:yield from product_nodes(x)
    if isinstance(obj,dict):
        typ=obj.get('@type',[])
        if isinstance(typ,str):typ=[typ]
        if any(str(t).lower().endswith('product') for t in typ):yield obj
        for v in obj.values():
            if isinstance(v,(dict,list)):yield from product_nodes(v)

def collect(url,brand,season):
    p=urlparse(url)
    if p.scheme not in ('http','https') or not p.netloc:raise ValueError('유효한 http(s) URL이 필요합니다.')
    resp=requests.get(url,headers={'User-Agent':'Mozilla/5.0 (compatible; MenswearResearch/1.0)'},timeout=18)
    resp.raise_for_status()
    soup=BeautifulSoup(resp.text,'html.parser')
    rows=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.string or script.get_text())
        except (ValueError,TypeError):continue
        for node in product_nodes(data):
            offer=node.get('offers') or {}
            if isinstance(offer,list):offer=offer[0] if offer else {}
            if not isinstance(offer,dict):offer={}
            image=node.get('image') or ''
            if isinstance(image,list):image=image[0] if image else ''
            if isinstance(image,dict):image=image.get('url','')
            material=node.get('material') or ''
            if isinstance(material,(dict,list)):material=json.dumps(material,ensure_ascii=False)
            name=str(node.get('name') or '')
            link=urljoin(url,str(node.get('url') or url))
            rows.append(dict(brand=brand,season=season,category=category(name+' '+str(node.get('category',''))),name=name,price=numeric(offer.get('price') or offer.get('lowPrice')),currency=offer.get('priceCurrency') or 'KRW',material=str(material),color=str(node.get('color') or ''),url=link,image_url=urljoin(url,str(image)),source_url=url,collected_at=datetime.now().isoformat(timespec='seconds'),quality='structured'))
    if not rows:
        # Metadata is not evidence that a listing page represents one product.
        og_type=soup.find('meta',property='og:type')
        if og_type and 'product' in str(og_type.get('content','')).lower():
            title=soup.find('meta',property='og:title')
            image=soup.find('meta',property='og:image')
            price=soup.find('meta',property='product:price:amount')
            name=title.get('content','') if title else (soup.title.get_text(strip=True) if soup.title else '')
            rows.append(dict(brand=brand,season=season,category=category(name),name=name,price=numeric(price.get('content')) if price else None,currency='KRW',material='',color='',url=url,image_url=urljoin(url,image.get('content','')) if image else '',source_url=url,collected_at=datetime.now().isoformat(timespec='seconds'),quality='metadata'))
    return list({x['url']:x for x in rows}.values())

st.title('🧥 Menswear Intel')
st.caption('남성복 시즌별 경쟁사 조사 · 모바일 반응형 웹 대시보드 v1.1')
st.info('공식몰 공개 HTML의 Product JSON-LD를 수집합니다. 브랜드 전체 전수 수집은 지원하지 않으며, 수집된 URL 기준으로 집계합니다.')
t1,t2,t3,t4=st.tabs(['📊 분석 대시보드','🌐 상품 수집','🗂 상품 DB · 엑셀','🔐 향후 내부 데이터'])
with t1:
    df=load()
    if df.empty:st.warning('저장된 상품이 없습니다. 상품 수집 탭에서 URL을 입력하거나 샘플 CSV를 업로드하세요.')
    else:
        a,b,c=st.columns(3)
        seasons=sorted(df.season.dropna().unique(),reverse=True)
        brands=sorted(df.brand.dropna().unique())
        with a:sf=st.selectbox('시즌',['전체']+seasons)
        with b:bf=st.multiselect('브랜드',brands,default=brands)
        with c:cf=st.multiselect('카테고리',CATS,default=CATS)
        view=df[(df.brand.isin(bf)) & (df.category.isin(cf))]
        if sf!='전체':view=view[view.season==sf]
        a,b,c,d=st.columns(4)
        a.metric('수집 상품 수',len(view));b.metric('브랜드',view.brand.nunique());c.metric('카테고리',view.category.nunique())
        d.metric('가격 중앙값',f"₩{view.price.median():,.0f}" if view.price.notna().any() else '정보 없음')
        st.subheader('브랜드 × 카테고리 상품 수')
        if not view.empty:st.bar_chart(view.groupby(['category','brand']).size().unstack(fill_value=0))
        st.subheader('가격 분석')
        prices=view.dropna(subset=['price'])
        if not prices.empty:st.dataframe(prices.groupby(['brand','category']).price.agg(['count','median','mean','min','max']).reset_index(),use_container_width=True,hide_index=True)
        st.subheader('소재 비교')
        material=view[view.material.fillna('').str.strip()!='']
        if material.empty:st.caption('공식몰에서 추출된 소재 정보가 없습니다. CSV로 보완할 수 있습니다.')
        else:st.dataframe(material[['brand','season','category','name','material','price','url']],use_container_width=True,hide_index=True)
        st.caption('상품 수는 수집된 고유 URL 수이며 공식몰 전체 스타일 수를 뜻하지 않을 수 있습니다. 통화가 다른 가격은 직접 비교하지 마세요.')
with t2:
    st.subheader('공식몰 URL에서 상품 정보 수집')
    with st.form('collector'):
        a,b=st.columns(2)
        with a:brand=st.text_input('브랜드',placeholder='예: DAKS')
        with b:season=st.text_input('시즌',placeholder='예: 27SS')
        urls=st.text_area('공식몰 상품 상세 또는 목록 URL · 줄바꿈으로 구분',height=145)
        go=st.form_submit_button('수집 및 DB 저장',type='primary')
    if go:
        targets=list(dict.fromkeys(x.strip() for x in urls.splitlines() if x.strip()))
        if not brand.strip() or not season.strip() or not targets:st.error('브랜드, 시즌, URL을 입력하세요.')
        elif len(targets)>30:st.error('한 번에 최대 30개 URL까지 지원합니다.')
        else:
            results=[];errors=[];bar=st.progress(0)
            for i,url in enumerate(targets):
                try:results+=collect(url,brand.strip(),season.strip())
                except Exception as e:errors.append({'url':url,'error':str(e)[:250]})
                bar.progress((i+1)/len(targets))
                if i<len(targets)-1:time.sleep(1.5)
            if results:
                save(results);st.success(f'{len(results)}개 상품 레코드를 저장하거나 갱신했습니다.');st.dataframe(pd.DataFrame(results),use_container_width=True)
            else:st.warning('상품 구조화 데이터를 찾지 못했습니다. JavaScript 렌더링, 차단 또는 목록 페이지일 수 있습니다.')
            if errors:st.dataframe(pd.DataFrame(errors),use_container_width=True)
    st.divider()
    st.subheader('CSV 보완 업로드')
    template=pd.DataFrame(columns=COLS)
    st.download_button('CSV 템플릿 받기',template.to_csv(index=False).encode('utf-8-sig'),'product_template.csv','text/csv')
    up=st.file_uploader('CSV 파일 선택',type=['csv'])
    if up:
        try:
            try:uploaded=pd.read_csv(up,encoding='utf-8-sig')
            except UnicodeDecodeError:
                up.seek(0);uploaded=pd.read_csv(up,encoding='cp949')
            if not {'brand','season','url'}.issubset(uploaded.columns):st.error('brand, season, url 열은 필수입니다.')
            else:
                for col in COLS:
                    if col not in uploaded.columns:uploaded[col]=None
                uploaded=uploaded.where(pd.notna(uploaded),None)
                st.dataframe(uploaded.head(20),use_container_width=True)
                if st.button('CSV 상품 저장'):
                    rows=[]
                    for r in uploaded.to_dict('records'):
                        if not all(str(r.get(k) or '').strip() for k in ('brand','season','url')):continue
                        r['category']=r.get('category') or category(r.get('name'))
                        r['collected_at']=r.get('collected_at') or datetime.now().isoformat(timespec='seconds')
                        r['quality']=r.get('quality') or 'manual'
                        r['price']=numeric(r.get('price'))
                        rows.append(r)
                    save(rows);st.success(f'{len(rows)}개 저장 완료')
        except Exception as e:st.error(f'파일 오류: {e}')
with t3:
    df=load()
    if df.empty:st.caption('저장된 상품이 없습니다.')
    else:
        search=st.text_input('상품 검색')
        if search:df=df[df.astype(str).apply(lambda col:col.str.contains(search,case=False,regex=False,na=False)).any(axis=1)]
        st.dataframe(df,use_container_width=True,hide_index=True,column_config={'url':st.column_config.LinkColumn('상품 URL'),'image_url':st.column_config.LinkColumn('이미지 URL')})
        st.download_button('CSV 다운로드',df.to_csv(index=False).encode('utf-8-sig'),'menswear_products.csv','text/csv')
        output=io.BytesIO()
        with pd.ExcelWriter(output,engine='openpyxl') as writer:
            df.to_excel(writer,index=False,sheet_name='Products')
            df.groupby(['season','brand','category']).size().reset_index(name='count').to_excel(writer,index=False,sheet_name='Category_Counts')
            priced=df.dropna(subset=['price'])
            if not priced.empty:priced.groupby(['season','brand','category','currency']).price.agg(['count','median','mean','min','max']).reset_index().to_excel(writer,index=False,sheet_name='Price_Summary')
        st.download_button('엑셀 리포트 다운로드',output.getvalue(),'menswear_report.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
with t4:
    st.subheader('판매·고객 리퀘스트 연동 준비')
    st.warning('회사에서 허가한 비식별·비기밀 자료만 사용하세요. 현재 버전에서는 업로드 파일을 DB에 저장하지 않고 화면에 미리보기만 표시합니다.')
    for label in ['판매 데이터','고객 리퀘스트']:
        upload=st.file_uploader(label,type=['csv','xlsx'],key=label)
        if upload:
            try:
                data=pd.read_excel(upload) if upload.name.endswith('.xlsx') else pd.read_csv(upload)
                st.write(f'{label}: {len(data):,}행 / 열: '+', '.join(map(str,data.columns)))
                st.dataframe(data.head(10),use_container_width=True,hide_index=True)
            except Exception as e:st.error(f'읽기 실패: {e}')
    st.caption('향후: 스타일 코드 매핑, 판매율/정상판매 비중, 사이즈별 수요, 리퀘스트 키워드 집계, 상품 제안 우선순위 점수.')
