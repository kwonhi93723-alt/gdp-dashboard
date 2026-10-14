
import io
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="닥스 남성 디자인 리서치",
    page_icon="🧥",
    layout="wide"
)

st.title("🧥 닥스 남성 디자인 리서치")
st.caption("DAKS MEN | 상품 데이터 · 소재 · 디자인 분석")

CSV_URL = (
    "https://raw.githubusercontent.com/"
    "kwonhi93723-alt/gdp-dashboard/main/"
    "daks_men_verified_research_census_v1.csv"
)

@st.cache_data(ttl=600)
def load_data():
    return pd.read_csv(CSV_URL, dtype=str).fillna("")

try:
    df = load_data()
except Exception as e:
    st.error(f"상품 데이터를 불러오지 못했습니다: {e}")
    st.stop()

if df.empty:
    st.warning("등록된 상품이 없습니다.")
    st.stop()

# 중복 품번 제거
if "품번" in df.columns:
    df = df.drop_duplicates(subset=["품번"], keep="first")

st.success(f"등록된 조사 상품: {len(df)}개")

st.info(
    "현재 데이터는 공개 자료에서 확인한 상품 표본입니다. "
    "브랜드 전체 상품의 전수조사가 완료된 것은 아닙니다. "
    "제조연월과 출시 시즌은 구분해서 확인하세요."
)

# 요약 지표
c1, c2, c3 = st.columns(3)

c1.metric("전체 상품", len(df))

c2.metric(
    "상품 유형",
    df["유형"].nunique() if "유형" in df.columns else 0
)

c3.metric(
    "겉감 정보 보유",
    int(df["겉감"].ne("").sum())
    if "겉감" in df.columns else 0
)

st.divider()
st.subheader("① 상품 검색 및 필터")

search = st.text_input(
    "상품명·품번 검색",
    placeholder="해링턴, 블루종, DMJU..."
)

filtered = df.copy()

for col in ["브랜드", "시즌", "유형"]:
    if col in filtered.columns:
        options = sorted(
            filtered[col].astype(str).unique().tolist()
        )
        selected = st.multiselect(
            f"{col} 선택",
            options,
            default=options,
            key=f"filter_{col}"
        )
        filtered = filtered[
            filtered[col].isin(selected)
        ]

if search:
    matched = pd.Series(False, index=filtered.index)

    for col in ["상품명", "품번", "유형", "디자인분석"]:
        if col in filtered.columns:
            matched |= filtered[col].astype(str).str.contains(
                search, case=False, regex=False, na=False
            )

    filtered = filtered[matched]

st.write(f"검색 결과: **{len(filtered)}개**")

st.divider()
st.subheader("② 상품 상세 데이터")

config = {}

if "출처URL" in filtered.columns:
    config["출처URL"] = st.column_config.LinkColumn(
        "상품 상세 페이지",
        display_text="상품 보기"
    )

for col in filtered.columns:
    if "이미지" in col or "사진URL" in col:
        config[col] = st.column_config.ImageColumn(col)

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    column_config=config
)

st.divider()
st.subheader("③ 품목별 상품 구성")

if "유형" in filtered.columns and not filtered.empty:
    counts = filtered["유형"].value_counts()
    st.bar_chart(counts)
else:
    st.info("표시할 상품이 없습니다.")

st.divider()
st.subheader("④ 상품별 디자인 분석")

if not filtered.empty:
    labels = []

    for _, row in filtered.iterrows():
        labels.append(
            f"{row.get('품번', '')} | {row.get('상품명', '')}"
        )

    selected_index = st.selectbox(
        "분석할 상품 선택",
        range(len(labels)),
        format_func=lambda i: labels[i]
    )

    item = filtered.iloc[selected_index]

    for col in [
        "브랜드", "시즌", "유형", "품번", "상품명",
        "겉감", "안감/기타", "제조국",
        "제조연월", "디자인분석", "검증상태"
    ]:
        if col in item.index:
            st.write(f"**{col}:** {item[col]}")

    if item.get("출처URL", ""):
        st.link_button(
            "공식 상품 페이지 열기",
            item["출처URL"]
        )

st.divider()
st.subheader("⑤ 조사 데이터 다운로드")

st.download_button(
    "CSV 다운로드",
    data=filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name="daks_men_research.csv",
    mime="text/csv"
)

output = io.BytesIO()

with pd.ExcelWriter(output, engine="openpyxl") as writer:
    filtered.to_excel(
        writer,
        index=False,
        sheet_name="DAKS_PRODUCTS"
    )

st.download_button(
    "Excel 다운로드",
    data=output.getvalue(),
    file_name="daks_men_research.xlsx",
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    )
)
