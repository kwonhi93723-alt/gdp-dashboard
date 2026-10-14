"""Menswear Intel v4.0 — public-data merchandise planning analysis.
Place this file at pages/04_상품기획_전략분석.py in gdp-dashboard.
Requires streamlit, pandas, requests; uses existing GitHub Secrets.
"""
import base64
import io
import re
from datetime import datetime
from html import escape

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Menswear Intel v4.0 상품기획', page_icon='📈', layout='wide')
st.title('📈 Menswear Intel v4.0 | 상품기획 전략')
st.caption('닥스 기획 검토용 · 공개 상품 표본 분석 · 판매량/수요/전수조사 추정 아님')
st.warning('사내 매출·원가·고객정보는 공개 Streamlit 앱이나 공개 저장소에 업로드하지 마세요.')

COLS = ['brand','season','category','product_name','product_id','price','list_price','material','composition','url','source_category','collected_at','evidence']
CATS = ['수트','재킷','아우터','셔츠','니트','팬츠','티셔츠','액세서리']
KEYWORDS = ['레귤러','슬림','세미오버','오버핏','컴포트','스트레치','경량','워셔블','발수','방수','기능성','셋업','구김','링클프리','테이퍼드','와이드','울','캐시미어','린넨','실크','코튼','면','나일론','폴리에스터','다운']
MATERIAL_KEYS = ['캐시미어','울','모헤어','알파카','린넨','리넨','면','코튼','실크','폴리에스터','나일론','레이온','비스코스','스판','라이오셀','텐셀','가죽','스웨이드','다운']


def load_csv(path):
    token = str(st.secrets.get('GITHUB_TOKEN', ''))
    repo = str(st.secrets.get('GITHUB_DATA_REPO', ''))
    branch = str(st.secrets.get('GITHUB_DATA_BRANCH', 'main'))
    if not token or not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise RuntimeError('GitHub Secrets 연결이 필요합니다.')
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    r = requests.get(url, headers={'Authorization': f'Bearer {token}', 'Accept':'application/vnd.github+json'}, params={'ref':branch}, timeout=20)
    if r.status_code == 404:
        return pd.DataFrame(columns=COLS)
    r.raise_for_status()
    obj = r.json()
    if obj.get('content'):
        raw = base64.b64decode(obj['content'])
    elif obj.get('download_url'):
        raw_response = requests.get(obj['download_url'], headers={'Authorization': f'Bearer {token}'}, timeout=20)
        raw_response.raise_for_status()
        raw = raw_response.content
    else:
        raise RuntimeError('GitHub 파일 내용을 읽을 수 없습니다.')
    return pd.read_csv(io.BytesIO(raw), encoding='utf-8-sig') if raw.strip() else pd.DataFrame(columns=COLS)


def normalize(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS + ['style_key'])
    d = df.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = ''
    d = d[COLS].copy()
    for c in COLS:
        if c not in ('price','list_price'):
            d[c] = d[c].fillna('').astype(str).str.strip()
    for c in ('price','list_price'):
        d[c] = pd.to_numeric(d[c].astype(str).str.replace(r'[^0-9.]','',regex=True), errors='coerce')
        d.loc[d[c] <= 0, c] = float('nan')
    d['brand'] = d['brand'].replace({'Cambridge Members':'캠브리지 멤버스','Galaxy':'갤럭시','DAKS':'닥스'})
    d['season'] = d['season'].replace('', '미확인')
    d['category'] = d['category'].replace('', '미분류')
    d['style_key'] = d['product_id']
    blank = d['style_key'].eq('')
    d.loc[blank,'style_key'] = d.loc[blank,'url']
    blank = d['style_key'].eq('')
    d.loc[blank,'style_key'] = d.loc[blank,'product_name']
    d = d[d['style_key'].ne('')].copy()
    return d.drop_duplicates(['brand','style_key'], keep='last').reset_index(drop=True)


def scoped(df, brands, cats, seasons):
    return df[df['brand'].isin(brands) & df['category'].isin(cats) & df['season'].isin(seasons)].copy()


def coverage(df):
    if df.empty:
        return pd.DataFrame(columns=['브랜드','수집 SKU','카테고리 수','시즌 확인율','가격 확보율','혼용률 확보율'])
    return df.groupby('brand').agg(
        **{'수집 SKU':('style_key','nunique'), '카테고리 수':('category','nunique'),
           '시즌 확인율':('season',lambda s: round(s.ne('미확인').mean()*100,1)),
           '가격 확보율':('price',lambda s: round(s.notna().mean()*100,1)),
           '혼용률 확보율':('composition',lambda s: round(s.str.contains(r'\d+\s*%',regex=True).mean()*100,1))}
    ).reset_index().rename(columns={'brand':'브랜드'})


def price_stats(df):
    valid = df.dropna(subset=['price'])
    if valid.empty:
        return pd.DataFrame(columns=['brand','category','상품 수','중앙가격','하위25%','상위75%','최저가','최고가'])
    out = valid.groupby(['brand','category']).price.agg(
        **{'상품 수':'count','중앙가격':'median','하위25%':lambda s:s.quantile(.25),
           '상위75%':lambda s:s.quantile(.75),'최저가':'min','최고가':'max'}).reset_index()
    for c in ['중앙가격','하위25%','상위75%','최저가','최고가']:
        out[c] = out[c].round(0).astype('int64')
    return out


def keyword_stats(df, keywords):
    rows=[]
    for brand, part in df.groupby('brand'):
        for word in keywords:
            count = part['product_name'].str.contains(re.escape(word),case=False,regex=True,na=False).sum()
            if count:
                rows.append({'브랜드':brand,'키워드':word,'언급 SKU':int(count),'표본 내 비율(%)':round(100*count/len(part),1)})
    return pd.DataFrame(rows,columns=['브랜드','키워드','언급 SKU','표본 내 비율(%)'])


def history_changes(history, df):
    if history.empty or 'collected_at' not in history.columns:
        return pd.DataFrame(), pd.DataFrame()
    h = history.copy()
    for col in COLS:
        if col not in h.columns: h[col]=''
    h['date'] = pd.to_datetime(h['collected_at'],errors='coerce',utc=True).dt.date
    h = h.dropna(subset=['date'])
    if h.empty: return pd.DataFrame(),pd.DataFrame()
    h['product_id'] = h['product_id'].fillna('').astype(str)
    h['url'] = h['url'].fillna('').astype(str)
    h['product_name'] = h['product_name'].fillna('').astype(str)
    h['identity'] = h['product_id'].where(h['product_id'].ne(''),h['url'])
    h['identity'] = h['identity'].where(h['identity'].ne(''),h['product_name'])
    h = h[h['identity'].ne('')].sort_values('date')
    firsts = h.drop_duplicates(['brand','identity'],keep='first')
    discoveries = firsts.groupby(['date','brand']).size().rename('최초 발견 SKU').reset_index()
    h['price_num'] = pd.to_numeric(h['price'],errors='coerce')
    unique = h.drop_duplicates(['brand','identity','date'],keep='last')
    first = unique.dropna(subset=['price_num']).drop_duplicates(['brand','identity'],keep='first')
    last = unique.dropna(subset=['price_num']).drop_duplicates(['brand','identity'],keep='last')
    both = first[['brand','identity','date','price_num']].merge(last[['brand','identity','date','price_num']],on=['brand','identity'],suffixes=('_first','_last'))
    changes = both[(both['date_first'] < both['date_last']) & (both['price_num_first'] != both['price_num_last'])].copy()
    if not changes.empty:
        changes['변동률(%)'] = ((changes['price_num_last']/changes['price_num_first']-1)*100).round(1)
        changes = changes.rename(columns={'brand':'브랜드','identity':'상품 식별자','date_first':'첫 관측일','date_last':'최근 관측일','price_num_first':'첫 관측가','price_num_last':'최근 관측가'})
    return discoveries,changes


def make_notes(df, pstats, changes):
    notes=[]
    if df.empty: return ['분석할 상품이 없습니다.']
    brands=df['brand'].nunique()
    if brands<2: notes.append('브랜드 1개만 확보되어 경쟁사 간 차이 판단은 보류합니다.')
    if (df['season']=='미확인').mean()>.2: notes.append('시즌 미확인 비중이 20%를 넘습니다. 시즌별 상품 전략 판단 전 시즌 검증이 필요합니다.')
    if df['composition'].str.contains(r'\d+\s*%',regex=True).mean()<.5: notes.append('혼용률 확인율이 낮습니다. 소재 키워드는 참고하되 실제 섬유 비율 비교는 보류합니다.')
    for category, sub in pstats.groupby('category'):
        if sub['brand'].nunique()<2: continue
        if (sub['상품 수']<3).any():
            notes.append(f'{category}: 브랜드별 가격 표본 중 3개 미만이 있어 가격 차이 해석을 보류합니다.')
            continue
        low=sub.loc[sub['중앙가격'].idxmin()]
        high=sub.loc[sub['중앙가격'].idxmax()]
        if low['브랜드' if '브랜드' in sub.columns else 'brand'] != high['brand']:
            notes.append(f"{category}: 수집 표본 중앙가격은 {low['brand']} {int(low['중앙가격']):,}원, {high['brand']} {int(high['중앙가격']):,}원입니다. 가격대 차이의 원인이 소재·사양·라인 차이인지 상품 원문으로 검증하세요.")
    if '닥스' not in set(df['brand']): notes.append('닥스 데이터가 없어 닥스 대비 가격·상품 전략을 직접 비교할 수 없습니다.')
    if not changes.empty: notes.append(f'날짜별 관측 가격 변경 상품 {len(changes)}건이 확인됩니다. 할인·쿠폰 적용 여부를 원문에서 검증하세요.')
    notes.append('상품 미발견은 미전개를 뜻하지 않습니다. 브랜드별 수집 범위와 중복을 확인한 뒤 기획회의에 활용하세요.')
    return notes


try:
    latest_raw=load_csv('data/menswear_public_products.csv')
    history_raw=load_csv('data/menswear_public_history.csv')
    st.success(f'GitHub 공개 상품 데이터 연결 · 최신 {len(latest_raw)}행 / 이력 {len(history_raw)}행')
except Exception as exc:
    st.error(f'GitHub 데이터 연결 실패: {type(exc).__name__}: {str(exc)[:160]}')
    latest_raw=pd.DataFrame(columns=COLS)
    history_raw=pd.DataFrame(columns=COLS)

with st.expander('선택: 공개 상품 CSV 추가 업로드 (세션 내 분석만)',expanded=False):
    uploads=st.file_uploader('CSV 선택',type='csv',accept_multiple_files=True)
    extra=[]
    for f in uploads or []:
        try:
            try: extra.append(pd.read_csv(io.BytesIO(f.getvalue()),encoding='utf-8-sig'))
            except UnicodeDecodeError: extra.append(pd.read_csv(io.BytesIO(f.getvalue()),encoding='cp949'))
        except Exception as exc: st.warning(f'{f.name}: {type(exc).__name__}')
    if extra:
        latest_raw=pd.concat([latest_raw,*extra],ignore_index=True)

df=normalize(latest_raw)
if df.empty:
    st.info('공개 상품 데이터가 없습니다. v3.6 수집 페이지에서 먼저 수집하거나 공개 상품 CSV를 업로드해 주세요.')
    st.stop()

st.subheader('① 분석 범위 · 데이터 신뢰도')
a,b,c=st.columns(3)
brands=a.multiselect('브랜드',sorted(df['brand'].unique()),default=sorted(df['brand'].unique()))
categories=b.multiselect('카테고리',sorted(df['category'].unique()),default=sorted(df['category'].unique()))
seasons=c.multiselect('시즌',sorted(df['season'].unique()),default=sorted(df['season'].unique()))
view=scoped(df,brands,categories,seasons)
if view.empty:
    st.info('선택 조건에 해당하는 상품이 없습니다.')
    st.stop()
st.dataframe(coverage(view),hide_index=True,use_container_width=True)
st.caption('확보율과 구성비는 수집된 SKU 기준입니다. 브랜드 전체 상품 수 또는 판매 비중이 아닙니다.')

st.subheader('② 카테고리 구성 · 가격 포지셔닝')
counts=pd.crosstab(view['category'],view['brand'])
st.bar_chart(counts)
st.dataframe(counts, use_container_width=True)
if counts.shape[1]>1:
    st.caption('표본 내 카테고리 비중(%) · 수집 범위가 비슷한 경우에만 비교하세요')
    st.dataframe((counts.div(counts.sum(axis=0),axis=1)*100).round(1),use_container_width=True)
ps=price_stats(view)
st.dataframe(ps,hide_index=True,use_container_width=True)
if not ps.empty:
    st.caption('카테고리별 중앙 판매가(원)')
    st.bar_chart(ps.pivot(index='category',columns='brand',values='중앙가격'))
    price_bins=[0,100000,200000,300000,500000,800000,1200000,2000000,float('inf')]
    price_labels=['10만원 미만','10~20만원','20~30만원','30~50만원','50~80만원','80~120만원','120~200만원','200만원 이상']
    priced=view.dropna(subset=['price']).copy()
    if not priced.empty:
        priced['가격 구간']=pd.cut(priced['price'],bins=price_bins,labels=price_labels,right=False)
        st.caption('브랜드별 가격 구간 분포 (SKU 수)')
        st.dataframe(pd.crosstab(priced['가격 구간'],priced['brand']),use_container_width=True)

st.subheader('③ 소재 · 실루엣 · 기능 키워드')
keyword_choice=st.multiselect('분석 키워드',KEYWORDS,default=KEYWORDS)
ks=keyword_stats(view,keyword_choice)
if ks.empty:
    st.info('현재 상품명에서 선택 키워드를 찾지 못했습니다.')
else:
    st.dataframe(ks.sort_values(['브랜드','언급 SKU'],ascending=[True,False]),hide_index=True,use_container_width=True)
st.caption('상품명 키워드 언급만 집계합니다. 실제 원단 혼용률·핏·기능성 인증을 뜻하지 않습니다.')

st.subheader('④ 신규 발견 · 관측 가격 변화')
discoveries,changes=history_changes(history_raw,view)
if discoveries.empty:
    st.info('날짜별 이력이 없거나 관측 날짜를 확인할 수 없습니다.')
else:
    st.dataframe(discoveries.tail(40),hide_index=True,use_container_width=True)
    st.caption('최초 발견일은 출시일이 아니라 이 시스템에서 처음 수집된 날짜입니다.')
if changes.empty:
    st.info('서로 다른 관측일 사이 가격 변화가 확인된 상품이 없습니다.')
else:
    st.dataframe(changes,hide_index=True,use_container_width=True)

st.subheader('⑤ 자동 기획 검토 포인트')
notes=make_notes(view,ps,changes)
for note in notes: st.info(note)
st.subheader('⑥ 근거 상품 확인 · 기획회의용 다운로드')
st.dataframe(view[['brand','season','category','product_name','product_id','price','material','composition','url','evidence']],hide_index=True,use_container_width=True)
st.download_button('분석 상품 CSV 다운로드',view[COLS].to_csv(index=False).encode('utf-8-sig'),file_name='menswear_v4_products.csv',mime='text/csv')
st.download_button('가격 포지셔닝 CSV 다운로드',ps.to_csv(index=False).encode('utf-8-sig'),file_name='menswear_v4_price_positioning.csv',mime='text/csv')
report='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>Menswear Intel v4.0</title><style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;color:#222}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}h1{color:#15384a}</style><h1>Menswear Intel v4.0 상품기획 검토</h1>'''
report+=f'<p>생성 {escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} · 확보 표본 {len(view)} SKU · {view["brand"].nunique()}개 브랜드</p>'
report+='<h2>분석 범위·품질</h2>'+coverage(view).to_html(index=False,escape=True)
report+='<h2>가격 포지셔닝</h2>'+ps.to_html(index=False,escape=True)
report+='<h2>기획 검토 포인트</h2><ul>'+''.join('<li>'+escape(note)+'</li>' for note in notes)+'</ul>'
report+='<p>주의: 공개몰 수집 표본이며 브랜드 전수·판매량·실제 수요를 나타내지 않습니다.</p></html>'
st.download_button('상품기획 회의용 HTML 리포트',report.encode('utf-8'),file_name='menswear_v4_strategy.html',mime='text/html')
