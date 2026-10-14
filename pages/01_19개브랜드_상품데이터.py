from pathlib import Path
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title='19개 브랜드 상품 리서치', layout='wide')
st.title('19개 브랜드 | 상품 리서치')
st.caption('2024–2026년 조사 진행본 · 검증 대기 데이터 포함 · 액세서리 제외')

DATA = Path(__file__).resolve().parents[1] / 'menswear_19brands_import_469.csv'
if not DATA.exists():
    st.error(f'CSV 파일이 없습니다: {DATA.name} (GitHub 저장소 최상위에 업로드 필요)')
    st.stop()

@st.cache_data(show_spinner=False)
def load_csv(path, stamp):
    return pd.read_csv(path, encoding='utf-8-sig', dtype=str, keep_default_na=False)

try:
    df = load_csv(str(DATA), DATA.stat().st_mtime)
except Exception as e:
    st.error(f'CSV를 읽을 수 없습니다: {e}')
    st.stop()

for col in ['브랜드','품번','상품명','대분류','유형','출시시즌','시즌검증','가격원','이미지URL','상품URL','겉감 혼용률','검증상태','데이터등급','제조연월']:
    if col not in df.columns:
        df[col] = ''

# URL은 HTTP(S)로 명시된 경우만 링크/이미지에 사용한다.
def is_http_url(v):
    return isinstance(v, str) and v.strip().lower().startswith(('https://','http://'))

def parse_price(v):
    if not isinstance(v, str):
        return None
    s = v.replace(',', '').replace('₩','').replace('원','').strip()
    # 가격원 필드에 설명이나 복수 가격이 있으면 가격 분석에서 제외한다.
    return int(s) if re.fullmatch(r'\d+', s) else None

df['_가격숫자'] = df['가격원'].map(parse_price)
df['_이미지유효'] = df['이미지URL'].map(is_http_url)
df['_상품링크유효'] = df['상품URL'].map(is_http_url)

m1,m2,m3,m4 = st.columns(4)
m1.metric('수집 상품 행', f'{len(df):,}')
m2.metric('데이터 보유 브랜드', f"{df.loc[df['브랜드'].ne(''), '브랜드'].nunique():,} / 19")
m3.metric('품번 기재 행', f"{df['품번'].str.strip().ne('').sum():,}")
m4.metric('이미지 URL 확인 행', f"{df['_이미지유효'].sum():,}")
st.warning('상품 행 수는 검증 완료 상품 수나 전수조사 완료를 의미하지 않습니다. 출시시즌은 공식 확인된 경우만 신뢰하세요.')

st.subheader('상품 필터')
fc1,fc2,fc3 = st.columns(3)
brands = sorted(x for x in df['브랜드'].unique() if x)
categories = sorted(x for x in df['대분류'].unique() if x)
seasons = sorted(x for x in df['출시시즌'].unique() if x)
with fc1:
    selected_brands = st.multiselect('브랜드', brands, default=brands)
with fc2:
    selected_categories = st.multiselect('의류 카테고리', categories, default=categories)
with fc3:
    selected_seasons = st.multiselect('확인된 출시 시즌', seasons, default=seasons, help='출시시즌이 공란인 상품은 아래 옵션으로 함께 볼 수 있습니다.')
include_unknown = st.checkbox('출시시즌 미확정 상품도 표시', value=True)
search = st.text_input('품번 · 상품명 · 소재 검색', placeholder='예: DMJU, 블루종, 나일론')
only_photo = st.checkbox('이미지 URL 있는 상품만', value=False)

view = df[df['브랜드'].isin(selected_brands) & df['대분류'].isin(selected_categories)].copy()
if seasons:
    keep_season = view['출시시즌'].isin(selected_seasons)
    if include_unknown:
        keep_season |= view['출시시즌'].str.strip().eq('')
    view = view[keep_season]
if search.strip():
    mask = pd.Series(False, index=view.index)
    for c in ['품번','상품명','겉감 혼용률','유형']:
        mask |= view[c].str.contains(search.strip(), case=False, regex=False, na=False)
    view = view[mask]
if only_photo:
    view = view[view['_이미지유효']]

st.subheader(f'검색 결과 · {len(view):,}개 행')
tab1,tab2,tab3 = st.tabs(['상품 리스트', '상품 사진 보기', '브랜드·가격 분석'])
with tab1:
    show_cols = [c for c in ['브랜드','대분류','유형','품번','상품명','출시시즌','시즌검증','겉감 혼용률','제조연월','가격원','상품URL','이미지URL','검증상태','데이터등급'] if c in view.columns]
    st.dataframe(view[show_cols], hide_index=True, use_container_width=True, column_config={'상품URL':st.column_config.LinkColumn('상품 URL'),'이미지URL':st.column_config.LinkColumn('이미지 URL')})
    st.download_button('필터 결과 CSV 다운로드', view.drop(columns=[c for c in view if c.startswith('_')]).to_csv(index=False).encode('utf-8-sig'), 'menswear_filtered.csv', 'text/csv')
with tab2:
    gallery = view[view['_이미지유효']]
    st.caption(f'유효 형식의 이미지 URL이 있는 상품: {len(gallery):,}건. 외부 사이트가 이미지 접근을 제한하면 표시되지 않을 수 있습니다.')
    if gallery.empty:
        st.info('현재 선택한 상품에는 이미지 URL이 없습니다. 공식 상품 페이지의 실제 이미지 주소 확보가 먼저 필요합니다.')
    else:
        limit = st.selectbox('표시 개수', [12,24,48], index=0)
        cards = gallery.head(limit).to_dict('records')
        for pos in range(0,len(cards),3):
            columns=st.columns(3)
            for col,item in zip(columns,cards[pos:pos+3]):
                with col:
                    st.image(item['이미지URL'], use_container_width=True)
                    st.markdown(f"**{item['브랜드']} · {item['품번'] or '품번 미확정'}**")
                    st.caption(item['상품명'] or '상품명 미확정')
                    if item['_상품링크유효']:
                        st.link_button('공식 상품 페이지', item['상품URL'])
with tab3:
    if view.empty:
        st.info('선택한 조건에 해당하는 상품이 없습니다.')
    else:
        st.markdown('**브랜드별 조사 행 수 (검증 완료 수량 아님)**')
        st.bar_chart(view.groupby('브랜드').size().sort_values(ascending=False))
        price_view=view.dropna(subset=['_가격숫자'])
        if price_view.empty:
            st.info('가격 분석이 가능한 숫자형 가격 데이터가 없습니다.')
        else:
            st.markdown('**브랜드별 표시 가격 중간값 (원)**')
            st.caption('숫자로 명확하게 입력된 가격만 집계. 판매가·정상가의 혼재 가능성이 있으므로 경쟁사 가격 분석 확정치로 사용하지 마세요.')
            st.bar_chart(price_view.groupby('브랜드')['_가격숫자'].median().sort_values(ascending=False))
        st.markdown('**카테고리별 상품 행 수**')
        st.bar_chart(view.groupby('대분류').size().sort_values(ascending=False))

with st.expander('현재 데이터의 조사 한계'):
    st.write('2024~2026년 전 시즌·전 스타일이 수집된 자료가 아닙니다. 품번/상품 URL이 없는 행이나 공식 출시 시즌이 미확인된 행이 남아 있습니다.')
    st.write('이미지 URL이 비어 있는 행에 외부 검색 이미지나 추정 링크를 대체 삽입하지 않습니다.')
