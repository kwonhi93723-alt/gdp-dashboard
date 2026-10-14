"""19개 남성복 브랜드의 조사 데이터 비교분석 (기존 CSV 변경 없음)."""
from pathlib import Path
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="경쟁브랜드 비교분석", page_icon="📊", layout="wide")
st.title("📊 경쟁브랜드 비교분석")
st.caption("2024–2026 조사 데이터 기반 · 조사 행 수는 실제 출시 스타일 수 또는 검증 완료 수량이 아닙니다.")

FILE = Path(__file__).resolve().parent.parent / "menswear_19brands_import_469.csv"
if not FILE.exists():
    st.error(f"데이터 파일을 찾지 못했습니다: {FILE.name}. GitHub 저장소 최상위에 CSV가 있는지 확인하세요.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_data(path, modified):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    df.columns = df.columns.str.strip()
    return df

df = load_data(FILE, FILE.stat().st_mtime)
need = ["브랜드", "상품명", "품번", "대분류", "가격원", "겉감 혼용률", "출시시즌", "상품URL"]
missing = [c for c in need if c not in df.columns]
if missing:
    st.error("CSV에 필요한 컬럼이 없습니다: " + ", ".join(missing))
    st.stop()

for c in df.columns:
    df[c] = df[c].astype(str).str.strip()

def to_price(v):
    v = str(v).replace(",", "").replace("₩", "").replace("원", "").strip()
    if not v or not re.fullmatch(r"\d+(?:\.\d+)?", v):
        return float("nan")
    return float(v)

df["가격_숫자"] = df["가격원"].map(to_price)
df["소재기재"] = df["겉감 혼용률"].ne("")
df["시즌기재"] = df["출시시즌"].ne("")
df["상품URL기재"] = df["상품URL"].ne("")

st.warning("자료에 미검증 행이 포함되어 있으며, 가격은 표기된 값만 비교합니다. 할인·정상가가 혼재할 수 있으므로 브랜드 가격 포지셔닝을 확정하지 마세요.", icon="⚠️")
brands = sorted(x for x in df["브랜드"].unique() if x)
cat = sorted(x for x in df["대분류"].unique() if x)
season = sorted(x for x in df["출시시즌"].unique() if x)
with st.sidebar:
    st.header("분석 조건")
    bsel = st.multiselect("브랜드", brands, default=brands)
    csel = st.multiselect("카테고리", cat, default=cat)
    ssel = st.multiselect("확인된 출시 시즌", season, default=season)
    include_unknown = st.checkbox("시즌 미확정도 포함", value=True)

mask = df["브랜드"].isin(bsel) & df["대분류"].isin(csel)
mask &= df["출시시즌"].isin(ssel) | (include_unknown & df["출시시즌"].eq(""))
f = df.loc[mask].copy()

m1,m2,m3,m4 = st.columns(4)
m1.metric("선택 상품 행", f"{len(f):,}")
m2.metric("선택 브랜드", f"{f['브랜드'].nunique():,}")
m3.metric("가격 기재", f"{f['가격_숫자'].notna().sum():,}")
m4.metric("공식 시즌 기재", f"{f['시즌기재'].sum():,}")

brand_tab, category_tab, price_tab, fabric_tab, quality_tab, detail_tab = st.tabs([
    "브랜드별 구성", "카테고리 비교", "가격 비교", "소재 키워드", "데이터 신뢰도", "상품 목록"
])
with brand_tab:
    counts = f.groupby("브랜드").size().sort_values(ascending=False).rename("조사 행 수")
    st.bar_chart(counts)
    st.dataframe(counts.reset_index(), use_container_width=True, hide_index=True)
with category_tab:
    matrix = pd.crosstab(f["브랜드"], f["대분류"])
    st.dataframe(matrix, use_container_width=True)
    if not matrix.empty:
        st.bar_chart(matrix.T)
with price_tab:
    priced = f.loc[f["가격_숫자"].notna() & (f["가격_숫자"] > 0)]
    if priced.empty:
        st.info("현재 선택 조건에서 비교할 수 있는 숫자형 가격이 없습니다.")
    else:
        summary = priced.groupby("브랜드")["가격_숫자"].agg(표본수="count", 중간값="median", 최소값="min", 최대값="max").sort_values("중간값", ascending=False)
        st.dataframe(summary.style.format({"중간값":"{:,.0f}원","최소값":"{:,.0f}원","최대값":"{:,.0f}원"}), use_container_width=True)
        st.bar_chart(summary["중간값"])
        st.caption("가격 표본이 소수인 브랜드 및 서로 다른 상품군의 직접 비교는 주의가 필요합니다.")
with fabric_tab:
    keywords = ["면", "코튼", "울", "모", "폴리에스터", "나일론", "린넨", "마", "캐시미어", "레이온", "폴리우레탄", "실크"]
    tmp = f.loc[f["소재기재"], ["브랜드", "겉감 혼용률"]]
    hits = []
    for k in keywords:
        hits.append({"소재 키워드": k, "언급 상품 행": int(tmp["겉감 혼용률"].str.contains(k, regex=False).sum())})
    out = pd.DataFrame(hits).sort_values("언급 상품 행", ascending=False)
    st.bar_chart(out.set_index("소재 키워드"))
    st.caption("문자열 키워드 집계이며 소재별 순수 사용 비율이나 정확한 섬유 조성 통계가 아닙니다. 한 상품이 여러 키워드에 집계될 수 있습니다.")
with quality_tab:
    q = f.groupby("브랜드").agg(전체행=("상품명","size"), 품번기재=("품번",lambda x:(x!="").sum()), 상품URL기재=("상품URL기재","sum"), 가격기재=("가격_숫자","count"), 소재기재=("소재기재","sum"), 시즌기재=("시즌기재","sum"))
    st.dataframe(q, use_container_width=True)
    st.caption("기재 여부만 계산했습니다. 각 값의 공식 출처 검증 여부와는 다릅니다.")
with detail_tab:
    search = st.text_input("품번 / 상품명 검색")
    view = f
    if search.strip():
        view = view[view["품번"].str.contains(search, case=False, regex=False) | view["상품명"].str.contains(search, case=False, regex=False)]
    cols = [c for c in ["브랜드", "품번", "상품명", "대분류", "출시시즌", "가격원", "겉감 혼용률", "상품URL", "검증상태"] if c in view.columns]
    st.dataframe(view[cols], use_container_width=True, hide_index=True, column_config={"상품URL":st.column_config.LinkColumn("상품 링크")})
    st.download_button("현재 검색 결과 CSV 다운로드", view.drop(columns=["가격_숫자", "소재기재", "시즌기재", "상품URL기재"]).to_csv(index=False).encode("utf-8-sig"), file_name="menswear_filtered.csv", mime="text/csv")
