"""DAKS MEN 디자인 기획 워크벤치 · 기존 469행 조사 CSV 활용."""
from pathlib import Path
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="DAKS MEN 디자인 기획", page_icon="🧵", layout="wide")
st.title("🧵 DAKS MEN 디자인 기획 워크벤치")
st.caption("기존 469행 조사 데이터를 활용합니다. 표본은 2024–2026 전체 출시 상품을 대표하지 않으며, 미검증 데이터가 포함됩니다.")

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "menswear_19brands_import_469.csv"
if not CSV.exists():
    st.error("GitHub 저장소 최상위에 menswear_19brands_import_469.csv 파일이 없습니다.")
    st.stop()

@st.cache_data(show_spinner=False)
def read_csv(path, mtime):
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    frame.columns = frame.columns.str.strip()
    return frame

df = read_csv(str(CSV), CSV.stat().st_mtime)
required = ["브랜드", "품번", "상품명", "대분류", "가격원", "겉감 혼용률", "상품URL", "출시시즌"]
missing = [x for x in required if x not in df.columns]
if missing:
    st.error("데이터 항목이 없습니다: " + ", ".join(missing))
    st.stop()
for col in df.columns:
    df[col] = df[col].fillna("").astype(str).str.strip()

def price_num(raw):
    text = str(raw).replace(",", "").replace("원", "").replace("₩", "").strip()
    return int(text) if re.fullmatch(r"\d+", text) else float("nan")

df["_price"] = df["가격원"].map(price_num)
df["_rid"] = range(len(df))
brands = sorted([x for x in df["브랜드"].unique() if x and x != "DAKS MEN"])
cat_options = sorted([x for x in df["대분류"].unique() if x])

st.warning("표시된 가격은 정상가/판매가 구분이 완전하지 않을 수 있고, 출시시즌·소재도 공식 검증이 끝나지 않은 행이 있습니다. 이 화면의 분포는 '수집 표본' 기준입니다.")
with st.sidebar:
    st.header("경쟁 조건")
    rivals = st.multiselect("비교 브랜드 (최대 5개)", brands, default=brands[:3], max_selections=5)
    cats = st.multiselect("카테고리", cat_options, default=cat_options)
    only_skus = st.checkbox("품번 기재 상품만", value=False)
    keyword = st.text_input("상품명·품번·디자인 키워드 검색")
    verified_only = st.checkbox("출시시즌 기재 행만 보기", value=False)

chosen = ["DAKS MEN"] + rivals
f = df[df["브랜드"].isin(chosen) & df["대분류"].isin(cats)].copy()
if only_skus:
    f = f[f["품번"].ne("")]
if verified_only:
    f = f[f["출시시즌"].ne("")]
if keyword.strip():
    searchable = f["상품명"].str.cat(f["품번"], sep=" ")
    if "디자인 키워드" in f.columns:
        searchable = searchable.str.cat(f["디자인 키워드"], sep=" ")
    f = f[searchable.str.contains(keyword.strip(), case=False, regex=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("선택된 조사 행", f"{len(f):,}")
m2.metric("비교 브랜드", f"{f['브랜드'].nunique():,}")
m3.metric("가격 기재 행", f"{f['_price'].notna().sum():,}")
m4.metric("공식 시즌 기재 행", f"{f['출시시즌'].ne('').sum():,}")

t1,t2,t3,t4 = st.tabs(["카테고리 구성", "가격·소재", "경쟁 스타일 후보", "기획안 만들기"])
with t1:
    st.subheader("브랜드 × 카테고리 (조사 행 수)")
    if f.empty:
        st.info("현재 조건에 해당하는 상품이 없습니다.")
    else:
        matrix = pd.crosstab(f["브랜드"], f["대분류"])
        st.dataframe(matrix, use_container_width=True)
        st.bar_chart(matrix.T)
        st.caption("브랜드별 조사량이 다르므로 이 표를 실제 출시 비중으로 해석하지 마세요.")

with t2:
    st.subheader("카테고리별 가격 비교")
    c = st.selectbox("가격 비교할 카테고리", cat_options) if cat_options else None
    priced = f[f["대분류"].eq(c) & f["_price"].notna() & f["_price"].gt(0)] if c else f.iloc[:0]
    if priced.empty:
        st.info("이 카테고리는 숫자로 확인된 가격이 없습니다.")
    else:
        stat = priced.groupby("브랜드")["_price"].agg(표본수="count", 중간가격="median", 최저가격="min", 최고가격="max").reset_index()
        st.dataframe(stat, hide_index=True, use_container_width=True)
        st.bar_chart(stat.set_index("브랜드")["중간가격"])
        st.caption("가격 표본 수와 정상가·판매가 혼재 여부를 함께 확인하세요.")
    st.subheader("소재 관련 키워드 기재 현황")
    fiber_terms = ["면", "코튼", "울", "모", "린넨", "마", "나일론", "폴리에스터", "캐시미어", "레이온", "실크", "폴리우레탄"]
    fiber_data = []
    for term in fiber_terms:
        fiber_data.append({"키워드":term, "언급된 조사 행": int(f["겉감 혼용률"].str.contains(term, regex=False).sum())})
    st.dataframe(pd.DataFrame(fiber_data), use_container_width=True, hide_index=True)
    st.caption("섬유별 혼용 비율이 아닌 문자열 언급 횟수이며, 한 상품에 여러 소재가 집계될 수 있습니다.")

with t3:
    st.subheader("참고할 경쟁 상품 고르기")
    st.caption("선택은 현재 세션에서만 유지됩니다. 제안 후보는 CSV로 저장해 주세요. 이미지 수집은 하지 않습니다.")
    competitors = f[f["브랜드"].ne("DAKS MEN")].copy()
    if competitors.empty:
        st.info("비교 브랜드를 선택하면 상품 후보가 표시됩니다.")
    else:
        cols = [c for c in ["브랜드", "품번", "상품명", "대분류", "가격원", "겉감 혼용률", "출시시즌", "상품URL", "검증상태"] if c in competitors.columns]
        view = competitors[["_rid"] + cols].copy().reset_index(drop=True)
        view.insert(0, "선택", False)
        edited = st.data_editor(view, hide_index=True, use_container_width=True, key="candidate_editor", disabled=["_rid"] + cols,
                                column_config={"상품URL":st.column_config.LinkColumn("공식 상품 링크"), "_rid":None})
        ids = edited.loc[edited["선택"], "_rid"].tolist()
        selection = competitors[competitors["_rid"].isin(ids)].drop(columns=["_rid", "_price"])
        st.metric("선택한 경쟁 상품", len(selection))
        st.download_button("선택한 상품 CSV 저장", selection.to_csv(index=False).encode("utf-8-sig"),
                           file_name="daks_competitor_shortlist.csv", mime="text/csv", disabled=selection.empty)

with t4:
    st.subheader("DAKS MEN 디자인 기획안")
    st.caption("아래 입력은 데이터베이스에 자동 저장되지 않습니다. 작성 후 CSV로 내려받으세요.")
    with st.form("idea_form"):
        proposed_category = st.selectbox("제안 카테고리", cat_options if cat_options else ["기타"])
        concept = st.text_input("제안 스타일/콘셉트", placeholder="예: 클래식 해링턴 실루엣을 경량 소재로 재해석")
        differentiation = st.text_area("경쟁 제품 대비 차별화 포인트", placeholder="실루엣, 패턴, 디테일, 착용 편의성 등")
        fabric = st.text_input("제안 소재", placeholder="예: 면·나일론 혼방")
        target_price = st.number_input("목표 가격(원, 미정이면 0)", min_value=0, max_value=10000000, value=0, step=10000)
        references = st.text_area("참고 품번 / URL", placeholder="후보 상품 CSV를 참고해 입력")
        comments = st.text_area("검증 과제 / 다음 액션", placeholder="원가, 샘플, 시장 반응 등")
        make = st.form_submit_button("기획안 다운로드 준비")
    if make:
        if not concept.strip():
            st.error("제안 스타일/콘셉트를 입력해 주세요.")
        else:
            idea = pd.DataFrame([{
                "기준브랜드":"DAKS MEN", "카테고리":proposed_category, "제안스타일":concept,
                "차별화포인트":differentiation, "제안소재":fabric,
                "목표가격원":target_price or "", "참고품번_URL":references, "검증과제":comments,
                "데이터출처":"menswear_19brands_import_469.csv", "진행상태":"아이디어 단계"
            }])
            st.download_button("기획안 CSV 다운로드", idea.to_csv(index=False).encode("utf-8-sig"),
                               file_name="daks_design_proposal.csv", mime="text/csv")

st.divider()
st.caption(f"현재 사용 데이터: {CSV.name} · 전체 {len(df):,}개 조사 행 · GitHub 기존 데이터 및 다른 페이지는 수정하지 않음")
