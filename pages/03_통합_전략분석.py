"""Menswear Intel v3: add as pages/03_통합_전략분석.py in the existing Streamlit repository."""
import io
import base64
import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin, urlparse, urldefrag

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BRANDS = {
    '캠브리지 멤버스': ('https://www.kolonmall.com/Brands/CAMBRIDGE-MEMBERS', 'kolonmall.com'),
    '갤럭시': ('https://m.ssfshop.com/Galaxy/main?brandShopNo=BDMA04A01&brndShopId=HMBGA', 'ssfshop.com'),
}
COLS = ['brand','season','category','product_name','product_id','price','list_price','material','composition','url','source_category','collected_at','evidence']
CATEGORY_RULES = [
    ('수트', ['수트','정장','SUIT','셋업']), ('재킷', ['재킷','자켓','JACKET','BLAZER']),
    ('아우터', ['아우터','코트','점퍼','패딩','다운','OUTER','COAT','JUMPER']),
    ('셔츠', ['셔츠','SHIRT']), ('니트', ['니트','스웨터','가디건','KNIT','SWEATER']),
    ('팬츠', ['팬츠','바지','슬랙스','TROUSER','PANTS','SLACKS']),
    ('티셔츠', ['티셔츠','T-SHIRT','POLO']), ('액세서리', ['ACC','벨트','타이','SCARF']),
]
MATERIALS = ['캐시미어','울','모헤어','알파카','린넨','리넨','면','코튼','실크','폴리에스터','나일론','레이온','비스코스','스판','라이오셀','텐셀','가죽','스웨이드','다운']
HEADERS = {'User-Agent':'MenswearIntelResearch/3.0 (public pages, low request rate)'}

def normalize_brand(s):
    s=str(s or '').strip().lower()
    if any(x in s for x in ['cambridge','캠브리지']):return '캠브리지 멤버스'
    if 'galaxy' in s or '갤럭시' in s:return '갤럭시'
    if 'daks' in s or '닥스' in s:return '닥스'
    return str(s).strip() or '미확인'

def category_of(s):
    s=str(s or '').upper()
    for cat,keys in CATEGORY_RULES:
        if any(k.upper() in s for k in keys):return cat
    return '미분류'

def season_of(s):
    s=str(s or '').upper()
    m=re.search(r'(?<!\d)(20\d{2})\s*[-_/ ]?\s*(SS|S/S|FW|F/W)(?![A-Z])',s)
    if m:return m.group(1)+('SS' if m.group(2) in ('SS','S/S') else 'FW')
    m=re.search(r'(?<!\d)(\d{2})\s*[-_/ ]?\s*(SS|FW)(?![A-Z])',s)
    if m:return '20'+m.group(1)+m.group(2)
    return '미확인'

def number(s):
    if isinstance(s,(int,float)) and pd.notna(s):return float(s)
    t=re.sub(r'[^\d.]','',str(s or ''))
    try:return float(t) if t else None
    except ValueError:return None

def first(x):
    if isinstance(x,list):return first(x[0]) if x else ''
    if isinstance(x,dict):return str(x.get('name') or x.get('value') or '')
    return str(x or '')

def objects(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from objects(v)
    elif isinstance(x,list):
        for v in x:yield from objects(v)

def extract(soup,url,brand,source_category):
    out=[]
    for tag in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(tag.string or tag.get_text())
        except (ValueError,TypeError):continue
        for item in objects(data):
            kind=item.get('@type',[]) if isinstance(item,dict) else []
            if not (('Product' in kind) if isinstance(kind,list) else kind=='Product'):continue
            name=first(item.get('name'))
            if not name:continue
            offers=item.get('offers') or {}
            if isinstance(offers,list):offers=offers[0] if offers else {}
            if not isinstance(offers,dict):offers={}
            desc=first(item.get('description'))
            pid=first(item.get('sku') or item.get('productID'))
            product_url=urljoin(url,first(item.get('url')) or url)
            materials=', '.join(m for m in MATERIALS if m in (name+' '+desc))
            out.append(dict(brand=brand,season=season_of(' '.join([name,desc,pid,product_url])),category=category_of(source_category+' '+name),product_name=name,product_id=pid,price=number(offers.get('price') or offers.get('lowPrice')),list_price=None,material=materials,composition=desc[:500],url=product_url,source_category=source_category,collected_at=datetime.now(timezone.utc).isoformat(),evidence='Product JSON-LD'))
    return out

def in_domain(url,domain):
    p=urlparse(url)
    return p.scheme in ('http','https') and (p.hostname==domain or (p.hostname or '').endswith('.'+domain))

def link_kind(url,brand):
    path=urlparse(url).path.lower()
    if brand=='캠브리지 멤버스' and '/brands/cambridge-members/' not in path:return None
    if brand=='갤럭시' and not any(x in path for x in ['galaxy','product','goods','category']):return None
    if any(x in path for x in ['/product/','/goods/','/goodsdetail','/productdetail']):return 'product'
    if any(x in path for x in ['/list/','/category/','/categories/','/special/','/collection/']):return 'listing'
    return None

def crawl(brand,max_pages=60,delay=1.5,extra=''):
    root,domain=BRANDS[brand]
    listing=deque([(root,'브랜드 메인')]);products=deque();seen=set();queued={root};rows=[];logs=[];links_found=0
    for raw in extra.splitlines():
        u=urldefrag(raw.strip())[0]
        if in_domain(u,domain) and u not in queued:
            listing.append((u,'사용자 지정'));queued.add(u)
    session=requests.Session();session.headers.update(HEADERS)
    while (listing or products) and len(seen)<max_pages:
        # 목록을 우선 방문해 상품 상세 페이지가 방문 한도를 독점하지 않도록 함
        url,source=(listing.popleft() if listing else products.popleft())
        if url in seen:continue
        seen.add(url)
        try:
            response=session.get(url,timeout=15,allow_redirects=True)
            if not in_domain(response.url,domain):
                logs.append(f'외부 도메인 리다이렉트 제외: {url}');continue
            if response.status_code in (403,429):
                logs.append(f'접근 제한 HTTP {response.status_code}: {url}');break
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type','').lower():continue
            soup=BeautifulSoup(response.text,'html.parser')
            found=extract(soup,response.url,brand,source)
            rows.extend(found)
            discovered=0
            for a in soup.select('a[href]'):
                target=urldefrag(urljoin(response.url,a['href']))[0]
                if not in_domain(target,domain) or target in queued:continue
                kind=link_kind(target,brand)
                if kind is None:continue
                queued.add(target);discovered+=1;links_found+=1
                if len(queued)>max_pages*100:break
                (listing if kind=='listing' else products).append((target,category_of(a.get_text(' ',strip=True)+' '+target)))
            logs.append(f'HTTP {response.status_code} / 상품 {len(found)} / 신규링크 {discovered}: {url}')
        except requests.RequestException as exc:
            logs.append(f'요청 실패 {type(exc).__name__}: {url}')
        time.sleep(delay)
    frame=pd.DataFrame(rows,columns=COLS)
    if not frame.empty:
        frame['_key']=frame['product_id'].fillna('').astype(str).str.strip()
        frame.loc[frame['_key']=='','_key']=frame.loc[frame['_key']=='','url']
        frame=frame.drop_duplicates(['brand','_key']).drop(columns='_key').reset_index(drop=True)
    return frame,logs,{'visited':len(seen),'discovered':links_found,'listing_queue_remaining':len(listing),'product_queue_remaining':len(products)}

def standardize(raw,source_name=''):
    df=raw.copy()
    alias={'브랜드':'brand','시즌':'season','카테고리':'category','상품명':'product_name','품번':'product_id','판매가':'price','정상가':'list_price','소재':'material','혼용률':'composition','상품URL':'url','상품 url':'url'}
    df=df.rename(columns={c:alias.get(str(c).strip(),str(c).strip()) for c in df.columns})
    if 'brand' not in df.columns:
        guessed=normalize_brand(source_name)
        df['brand']=guessed if guessed!='미확인' else '미확인'
    for col in COLS:
        if col not in df.columns:df[col]=None
    df=df[COLS].copy()
    df['brand']=df['brand'].map(normalize_brand)
    for col in ['product_name','product_id','url','material','composition','source_category','season','category']:
        df[col]=df[col].fillna('').astype(str).str.strip().replace({'nan':''})
    df['season']=df.apply(lambda r:r['season'] if re.fullmatch(r'20\d{2}(SS|FW)',r['season'].upper()) else season_of(' '.join([r['season'],r['product_name'],r['product_id'],r['url']])),axis=1)
    df['category']=df.apply(lambda r:r['category'] if r['category'] not in ('','미분류') else category_of(r['product_name']+' '+r['source_category']),axis=1)
    for col in ['price','list_price']:
        df[col]=pd.to_numeric(df[col].map(number),errors='coerce')
        df.loc[df[col]<=0,col]=float('nan')
    df['style_key']=df.apply(lambda r: r['product_id'].strip() or r['url'].strip() or r['product_name'].strip(),axis=1)
    df=df[df['style_key'].str.len()>0].drop_duplicates(['brand','style_key']).reset_index(drop=True)
    df['data_quality']=df.apply(lambda r:sum([bool(r['product_name']),r['category']!='미분류',r['season']!='미확인',pd.notna(r['price']),bool(r['material'])])/5,axis=1)
    return df

def group_stats(df):
    if df.empty:return pd.DataFrame()
    return df.groupby(['brand','season','category'],dropna=False).agg(styles=('style_key','nunique'),median_price=('price','median'),min_price=('price','min'),max_price=('price','max'),material_coverage=('material',lambda x:round(x.fillna('').astype(str).str.len().gt(0).mean()*100,1)),quality=('data_quality','mean')).reset_index()

def insights(df,season):
    sample=df if season=='전체' else df[df.season==season]
    results=[]
    if sample.empty:return ['선택한 시즌에 분석할 상품이 없습니다.']
    if sample['brand'].nunique()<2:results.append('현재 비교 브랜드가 1개뿐이므로 브랜드 간 우열이나 상품 공백은 판단할 수 없습니다.')
    if (sample['season']=='미확인').mean()>0.2:results.append('시즌 미확인 상품 비중이 높습니다. 시즌별 비교 결과를 확정하기 전에 원문 검증이 필요합니다.')
    if (sample['category']=='미분류').mean()>0.15:results.append('미분류 상품이 많습니다. 카테고리 표준화 후 상품 구성비를 다시 비교해야 합니다.')
    if sample['price'].notna().mean()<0.6:results.append('가격 정보가 충분하지 않습니다. 가격 포지셔닝 결론은 보류해야 합니다.')
    daks=sample[sample.brand=='닥스']; competitors=sample[sample.brand.isin(BRANDS)]
    if daks.empty:results.append('닥스 비교 데이터가 없어 닥스의 상품 공백을 판단할 수 없습니다. 닥스 상품 CSV를 추가해 주세요.')
    if not daks.empty and not competitors.empty:
        a=set(daks.category)-{'미분류'};b=set(competitors.category)-{'미분류'}
        gaps=sorted(b-a)
        if gaps:results.append('경쟁사 표본에는 있지만 닥스 표본에는 없는 카테고리: '+', '.join(gaps)+'. 실제 미전개 여부는 전체 상품 목록으로 확인해야 합니다.')
        else:results.append('현재 표본 기준으로 경쟁사에만 존재하는 카테고리는 확인되지 않았습니다.')
    results.append('상품 수와 구성비는 공개몰에서 확보한 표본 기준입니다. 판매량·매출·소비자 수요를 직접 나타내지 않습니다.')
    return results

def report_html(df,season,notes):
    view=df if season=='전체' else df[df.season==season]
    summary=group_stats(view)
    table=summary.to_html(index=False,border=0,na_rep='—') if not summary.empty else '<p>분석 데이터 없음</p>'
    bullets=''.join('<li>'+escape(x)+'</li>' for x in notes)
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Menswear Intel v3</title>'
            '<style>body{font-family:Arial,sans-serif;max-width:1080px;margin:40px auto;color:#20242b}h1{color:#12354b}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}th{background:#e9f0f4}.muted{color:#777}</style></head><body>'
            '<h1>Menswear Intel v3 | 시즌별 상품기획 리포트</h1><p class="muted">시즌: '+escape(season)+' · 생성: '+datetime.now().strftime('%Y-%m-%d %H:%M')+'</p>'
            '<h2>분석 범위</h2><p>확보 상품 '+str(len(view))+'개 · 브랜드 '+str(view.brand.nunique())+'개 · 수집 표본이며 전수조사/매출 데이터가 아닙니다.</p>'
            '<h2>경쟁사 비교</h2>'+table+'<h2>기획 검토 포인트</h2><ul>'+bullets+'</ul>'
            '<h2>기획 제안의 검증 절차</h2><p>1. 시즌·품번 검증 → 2. 브랜드별 수집 범위 일치 → 3. 가격·소재 원문 검증 → 4. 닥스 판매/재고 및 MD 의견 대조 → 5. 개발 우선순위 결정</p>'
            '<p class="muted">자동 분석은 의사결정 보조 자료입니다. 수집 누락과 시즌 미확인 데이터를 주의하세요.</p></body></html>')

# Optional persistence in a GitHub repository. Configure secrets in Streamlit Cloud.
def github_config():
    try:
        token=st.secrets.get('GITHUB_TOKEN','')
        repo=st.secrets.get('GITHUB_DATA_REPO','')
        branch=st.secrets.get('GITHUB_DATA_BRANCH','main')
        return str(token),str(repo),str(branch)
    except Exception:
        return '','','main'

def github_request(method, payload=None, sha=None):
    token,repo,branch=github_config()
    if not (token and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo)):
        raise RuntimeError('GitHub 저장소 연결이 설정되지 않았습니다.')
    url=f'https://api.github.com/repos/{repo}/contents/data/menswear_public_products.csv'
    headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    if method=='GET':
        r=requests.get(url,headers=headers,params={'ref':branch},timeout=20)
        if r.status_code==404:return None
        r.raise_for_status()
        return r.json()
    body={'message':'Update Menswear Intel public product snapshots','content':base64.b64encode(payload).decode(),'branch':branch}
    if sha:body['sha']=sha
    r=requests.put(url,headers=headers,json=body,timeout=30)
    r.raise_for_status()
    return r.json()

def load_remote():
    obj=github_request('GET')
    if obj is None:return pd.DataFrame(columns=COLS)
    content=base64.b64decode(obj['content'])
    return standardize(pd.read_csv(io.BytesIO(content),encoding='utf-8-sig'))[COLS]

def save_remote(frame):
    # Never persist uploaded internal data; only public crawls and public samples.
    obj=github_request('GET')
    old=pd.DataFrame(columns=COLS) if obj is None else standardize(pd.read_csv(io.BytesIO(base64.b64decode(obj['content'])),encoding='utf-8-sig'))[COLS]
    merged=standardize(pd.concat([old,frame],ignore_index=True))[COLS]
    payload=merged.to_csv(index=False).encode('utf-8-sig')
    github_request('PUT',payload,sha=obj['sha'] if obj else None)
    return len(merged)

def add_public(frame):
    old=st.session_state.get('v3_crawl',pd.DataFrame(columns=COLS))
    st.session_state['v3_crawl']=standardize(pd.concat([old,frame],ignore_index=True))[COLS]
    token,repo,_=github_config()
    if token and repo:
        try:
            n=save_remote(frame)
            st.success(f'GitHub 저장소에 공개 상품 누적 저장 완료: {n}건')
        except Exception as e:
            st.error(f'GitHub 저장 실패: {type(e).__name__} — CSV 백업을 다운로드해 주세요.')

st.set_page_config(page_title='Menswear Intel v3 통합 전략',page_icon='📊',layout='wide')
st.title('📊 Menswear Intel v3 | 통합 전략 분석')
st.caption('수집 → 정제 → 경쟁사 비교 → 인사이트 → 시즌별 상품기획 리포트')
st.warning('공개 Streamlit 앱에는 사내 매출·원가·고객정보를 업로드하지 마세요. GitHub 저장은 공개몰 수집 데이터에만 적용됩니다.')
if 'v3_remote_checked' not in st.session_state:
    st.session_state['v3_remote_checked']=True
    token,repo,_=github_config()
    if token and repo:
        try:st.session_state['v3_crawl']=load_remote()
        except Exception as e:st.warning(f'저장 데이터 불러오기 실패: {type(e).__name__}')

with st.expander('① 경쟁사 공식몰 추가 수집 (카테고리 우선 탐색)',expanded=False):
    st.caption('기존 v2 수집 페이지는 유지됩니다. 이 기능은 목록 페이지를 우선 탐색하지만 전체 상품 수집을 보장하지 않습니다.')
    brand=st.selectbox('브랜드',list(BRANDS),key='v3_brand')
    pages=st.slider('최대 방문 페이지',10,200,60,10,key='v3_pages')
    delay=st.slider('요청 간 대기(초)',1.0,5.0,1.5,0.5,key='v3_delay')
    extra=st.text_area('추가 카테고리 URL (선택)',key='v3_extra')
    if st.button('카테고리 우선 수집 실행',type='primary'):
        with st.spinner('공식몰 공개 페이지를 확인하고 있습니다...'):
            data,logs,stats=crawl(brand,pages,delay,extra)
        # Keep earlier brands in the current browser session instead of overwriting.
        add_public(data)
        st.session_state['v3_logs']=logs
        st.session_state['v3_stats']=stats
    if 'v3_stats' in st.session_state:
        stats=st.session_state['v3_stats']
        a,b,c=st.columns(3)
        a.metric('방문 페이지',stats['visited']);b.metric('신규 링크',stats['discovered']);c.metric('추출 상품',len(st.session_state['v3_crawl']))
        st.caption(f"남은 목록 {stats['listing_queue_remaining']} / 남은 상품 상세 {stats['product_queue_remaining']} · 남은 페이지가 있으면 표본 수집이 끝난 것입니다.")
        with st.expander('수집 로그'):st.code('\n'.join(st.session_state['v3_logs']))

st.subheader('② 데이터 통합 및 품질 확인')
st.caption('브랜드별 수집 결과는 세션에 누적됩니다. GitHub Secrets를 설정하면 공개 상품만 별도 저장소에 자동 보관하고 재접속 시 복원합니다. 설정하지 않으면 CSV 백업이 필요합니다.')
with st.expander('💾 데이터 영구 보관 상태 / 복원'):
    token,repo,_=github_config()
    st.write('GitHub 저장 연결: '+('설정됨 ('+repo+')' if token and repo else '미설정 — 세션 종료 시 데이터가 사라질 수 있습니다.'))
    if token and repo and st.button('저장된 공개 상품 다시 불러오기'):
        try:add=load_remote();st.session_state['v3_crawl']=standardize(pd.concat([st.session_state.get('v3_crawl',pd.DataFrame(columns=COLS)),add],ignore_index=True))[COLS];st.success(f'복원 완료: {len(add)}건')
        except Exception as e:st.error(f'복원 실패: {type(e).__name__}')
st.info('닥스는 LF몰 공개 검색결과에서 확인된 2026-10-13 스냅샷 6건을 제공합니다. 특정 검색어의 편향된 표본이므로 전체 브랜드 구성비나 시즌별 상품 공백 판단에 사용하면 안 됩니다.')
# Verified public LFmall search snapshot, 2026-10-13. These are search hits, not the entire DAKS assortment.
DAKS_PUBLIC = [
 ('닥스','미확인','티셔츠','[EXCLUSIVE] 다크 블루 기모 마이크로 투톤 카라넥 티셔츠','','185490','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 블루 고밀도 데님 세미 오버 핏 셔츠','','169290','','면','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 라이트블루 린넨100% 닥스훈트 반팔 셔츠','','112770','','린넨','린넨100%','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','팬츠','[EXCLUSIVE] 라이트블루 스트레치 치노 팬츠','','125370','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','티셔츠','[EXCLUSIVE] 블루 링클프리 마이크로 반팔 티셔츠','','125370','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 블루 시어서커 스트라이프 반팔 셔츠','','112770','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
]
daks_public_df=pd.DataFrame(DAKS_PUBLIC,columns=COLS)
st.download_button('닥스 공개 검색 스냅샷 CSV 다운로드 (6건)',daks_public_df.to_csv(index=False).encode('utf-8-sig'),file_name='daks_public_sample_2026_10.csv',mime='text/csv')
if st.button('닥스 공개 검색 스냅샷 6건 비교에 추가'):
    old=st.session_state.get('v3_crawl',pd.DataFrame(columns=COLS))
    st.session_state['v3_crawl']=pd.concat([old,daks_public_df],ignore_index=True).drop_duplicates(subset=['brand','product_name','url'],keep='last').reset_index(drop=True)
    st.success('닥스 공개 샘플을 현재 세션에 추가했습니다.')
if 'v3_crawl' in st.session_state and not st.session_state['v3_crawl'].empty:
    st.download_button('현재 누적 수집 결과 백업 CSV',st.session_state['v3_crawl'][COLS].to_csv(index=False).encode('utf-8-sig'),file_name='menswear_intel_all_brands_backup.csv',mime='text/csv')
files=st.file_uploader('상품 CSV 업로드 (여러 개 선택 가능)',type=['csv'],accept_multiple_files=True,key='v3_upload')
frames=[]
if 'v3_crawl' in st.session_state and not st.session_state['v3_crawl'].empty:frames.append(st.session_state['v3_crawl'])
for file in files or []:
    try:
        content=file.getvalue()
        try:raw=pd.read_csv(io.BytesIO(content),encoding='utf-8-sig')
        except UnicodeDecodeError:raw=pd.read_csv(io.BytesIO(content),encoding='cp949')
        frames.append(raw)
    except Exception as exc:st.error(f'{file.name} 읽기 실패: {type(exc).__name__}')
if frames:
    combined=pd.concat(frames,ignore_index=True)
    df=standardize(combined)
    brands=sorted(df.brand.unique().tolist())
    seasons=['전체']+sorted(df.season.unique().tolist(),reverse=True)
    season=st.selectbox('분석 시즌',seasons,key='v3_season')
    view=df if season=='전체' else df[df.season==season]
    a,b,c,d=st.columns(4)
    a.metric('표본 스타일/SKU',len(view));b.metric('브랜드',view.brand.nunique());c.metric('시즌 확인율',f"{(view.season!='미확인').mean():.0%}" if len(view) else '—');d.metric('가격 확보율',f"{view.price.notna().mean():.0%}" if len(view) else '—')
    st.caption('품번이 없으면 URL 또는 상품명으로 중복 제거합니다. 동일 디자인의 컬러별 SKU는 합쳐지지 않을 수 있습니다.')
    st.dataframe(view[['brand','season','category','product_name','product_id','price','material','data_quality','url']],use_container_width=True,hide_index=True)
    if '닥스' in view.brand.values and view.brand.nunique()>1:
        st.warning('닥스는 특정 검색어에서 얻은 6건의 편향 표본입니다. 경쟁사와 구성비·상품 공백을 동등한 모집단으로 비교할 수 없습니다. 아래 비교는 탐색용입니다.')
    st.subheader('③ 브랜드별 상품 구성')
    count=pd.crosstab(view['category'],view['brand'])
    if not count.empty:
        st.bar_chart(count)
        st.dataframe(count,use_container_width=True)
        pct=count.div(count.sum(axis=0).replace(0,float('nan')),axis=1).mul(100).round(1)
        st.caption('브랜드별 카테고리 구성비 (%) — 수집된 표본 기준')
        st.dataframe(pct,use_container_width=True)
    st.subheader('④ 가격 및 소재 분석')
    stats=group_stats(view)
    st.dataframe(stats,use_container_width=True,hide_index=True)
    mat=view[view.material.str.len()>0].copy()
    if not mat.empty:
        mat['material_token']=mat.material.str.split(', ')
        mat=mat.explode('material_token')
        st.caption('소재 언급 빈도 (소재 혼용률이 아니라 텍스트 등장 기준)')
        st.dataframe(pd.crosstab(mat.material_token,mat.brand),use_container_width=True)
    st.subheader('⑤ 자동 인사이트 · 개발 검토 포인트')
    notes=insights(df,season)
    for note in notes:st.info(note)
    st.subheader('⑥ 시즌별 상품기획 리포트')
    st.caption('가설과 검증 필요 사항을 구분한 HTML 보고서입니다. 브라우저에서 열어 PDF로 인쇄할 수 있습니다.')
    html=report_html(df,season,notes)
    st.download_button('상품기획 HTML 리포트 다운로드',html.encode('utf-8'),file_name='menswear_intel_v3_report.html',mime='text/html')
    st.download_button('정제 데이터 CSV 다운로드',df[COLS].to_csv(index=False).encode('utf-8-sig'),file_name='menswear_intel_v3_cleaned.csv',mime='text/csv')
    st.download_button('비교 요약 CSV 다운로드',stats.to_csv(index=False).encode('utf-8-sig'),file_name='menswear_intel_v3_summary.csv',mime='text/csv')
else:
    st.info('먼저 공식몰 수집을 실행하거나, 기존 v2에서 내려받은 CSV를 업로드해 주세요. 닥스 CSV를 추가하면 경쟁사와 비교할 수 있습니다.')
