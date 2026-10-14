from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="19개 브랜드 상품 조사", layout="wide")
st.title("19개 브랜드 상품 조사")
st.caption("2024–2026 조사 진행본 · 미검증 항목 포함 · 액세서리 제외 대상")

DATA_FILE = Path(__file__).resolve().parents[1] / "menswear_19brands_import_469.csv"
if not DATA_FILE.is_file():
    st.error(f"데이터 파일을 찾지 못했습니다: {DATA_FILE.name}")
    st.info("GitHub 저장소 최상위에 menswear_19brands_import_469.csv 를 올려주세요.")
    st.stop()

try:
    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", dtype=str).fillna("")
except Exception as exc:
    st.error(f"CSV 읽기 오류: {exc}")
    st.stop()

required = ["브랜드", "품번", "상품명", "대분류"]
missing = [c for c in required if c not in df.columns]
if missing:
    st.error("필요한 컬럼이 없습니다: " + ", ".join(missing))
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("수집된 상품 행", f"{len(df):,}")
c2.metric("데이터 보유 브랜드", f"{df['브랜드'].replace('', pd.NA).nunique():,}")
c3.metric("품번 기재 행", f"{df['품번'].ne('').sum():,}")
c4.metric("상품 URL 기재 행", f"{df['상품URL'].ne('').sum():,}" if "상품URL" in df else "-")
st.warning("수집 행 수는 검증 완료 품번 수 또는 전수조사 완료 수량이 아닙니다.")

brand_options = sorted(v for v in df['브랜드'].unique() if v)
category_options = sorted(v for v in df['대분류'].unique() if v)
selected_brands = st.multiselect("브랜드", brand_options, default=brand_options)
selected_categories = st.multiselect("대분류", category_options, default=category_options)
query = st.text_input("품번·상품명 검색")

view = df[df['브랜드'].isin(selected_brands) & df['대분류'].isin(selected_categories)]
if query:
    q = query.strip()
    view = view[view['품번'].str.contains(q, case=False, regex=False) | view['상품명'].str.contains(q, case=False, regex=False)]

st.subheader(f"상품 목록 · {len(view):,}개 행")
cols = [c for c in ["브랜드", "대분류", "품번", "상품명", "출시시즌", "시즌검증", "겉감 혼용률", "가격원", "이미지URL", "상품URL", "검증상태", "데이터등급"] if c in view.columns]
st.dataframe(view[cols], hide_index=True, use_container_width=True)
st.download_button("현재 필터 결과 CSV 다운로드", view.to_csv(index=False).encode('utf-8-sig'), file_name="menswear_filtered.csv", mime="text/csv")

st.subheader("브랜드별 수집 행 수")
st.bar_chart(df.groupby('브랜드').size().sort_values(ascending=False))
