"""DAKS MEN research viewer. Data is maintained in repository root CSV.

No automated scraping is performed. Do not treat scraped/search results as a census.
"""
from pathlib import Path
import io
import re

import pandas as pd
import streamlit as st

st.set_page_config(page_title="닥스 남성 디자인 리서치", page_icon="🧥", layout="wide")
st.title("닥스 남성 디자인 리서치")
st.caption("DAKS MEN · 품번 단위 조사 · 소재 · 시즌 증거 · 이미지")

DATA_FILE = "daks_men_verified_research.csv"
REPO_RAW = (
    "https://raw.githubusercontent.com/kwonhi93723-alt/"
    "gdp-dashboard/main/" + DATA_FILE
)
REQUIRED = ("품번", "브랜드", "상품명", "유형", "출처URL")
OPTIONAL = (
    "시즌", "시즌확정여부", "겉감", "안감/기타", "제조연월",
    "제조국", "가격", "이미지URL", "검증상태", "디자인분석",
)


def valid_http_url(value):
    return str(value).startswith(("https://", "http://"))


@st.cache_data(ttl=300, show_spinner="조사 데이터 불러오는 중...")
def load_data():
    # Running on Streamlit Cloud: root app.py and pages/ are in the same repository.
    root = Path(__file__).resolve().parent.parent
    local = root / DATA_FILE
    source = str(local) if local.is_file() else REPO_RAW
    frame = pd.read_csv(source, dtype=str, encoding="utf-8-sig").fillna("")
    frame.columns = frame.columns.str.strip()
    missing = [col for col in REQUIRED if col not in frame.columns]
    if missing:
        raise ValueError("CSV 필수 열 누락: " + ", ".join(missing))
    for col in OPTIONAL:
        if col not in frame.columns:
            frame[col] = ""
    frame["품번"] = frame["품번"].str.strip().str.upper()
    frame = frame.loc[frame["품번"].ne("")].copy()
    frame = frame.drop_duplicates(subset=["품번"], keep="last").reset_index(drop=True)
    return frame, source


try:
    df, data_source = load_data()
except Exception as error:
    st.error(f"데이터 읽기 실패: {error}")
    st.info("GitHub 최상위에 daks_men_verified_research.csv를 업로드했는지 확인해 주세요.")
    st.stop()

if df.empty:
    st.warning("CSV에 유효한 품번이 없습니다.")
    st.stop()

n_pics = int(df["이미지URL"].map(valid_http_url).sum())
n_fabric = int(df["겉감"].str.strip().ne("").sum())
n_season_confirmed = int(df["시즌확정여부"].str.strip().eq("확정").sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("수집된 고유 품번", len(df))
m2.metric("겉감 정보", n_fabric)
m3.metric("사진 URL", n_pics)
m4.metric("공식 시즌 확정", n_season_confirmed)
st.info(
    "수집된 품번 수는 브랜드 전체 상품 수가 아닙니다. 전체 목록(분모)이 확보되지 않아 "
    "전수조사 완료율은 산출할 수 없습니다. 제조연월만으로 시즌을 확정하지 않습니다."
)

st.subheader("① 검색 · 필터")
needle = st.text_input("상품명 / 품번 / 소재 / 디자인 특징 검색", placeholder="예: 해링턴, 울, DMJU")
filtered = df.copy()
for col in ("브랜드", "유형", "시즌", "검증상태"):
    available = sorted(v for v in df[col].astype(str).unique() if v.strip())
    if available:
        selected = st.multiselect(col, available, default=available, key=f"daks_v3_{col}")
        filtered = filtered.loc[filtered[col].isin(selected)]

if needle.strip():
    escaped = re.escape(needle.strip())
    cols = ("품번", "상품명", "유형", "겉감", "디자인분석")
    hits = pd.Series(False, index=filtered.index)
    for col in cols:
        hits |= filtered[col].str.contains(escaped, case=False, regex=True, na=False)
    filtered = filtered.loc[hits]

st.caption(f"표시: {len(filtered)}개 / 전체 {len(df)}개")
st.subheader("② 상품 목록")
view_cols = [
    "이미지URL", "품번", "상품명", "브랜드", "유형", "시즌", "시즌확정여부",
    "겉감", "안감/기타", "제조연월", "제조국", "가격", "출처URL",
    "검증상태", "디자인분석",
]
image_enabled = n_pics > 0
configs = {"출처URL": st.column_config.LinkColumn("상품 상세 링크")}
if image_enabled:
    configs["이미지URL"] = st.column_config.ImageColumn("대표 이미지")
else:
    view_cols.remove("이미지URL")

st.dataframe(
    filtered[view_cols], use_container_width=True, hide_index=True,
    column_config=configs,
)

st.subheader("③ 상품 상세 검토")
if filtered.empty:
    st.warning("선택한 조건에 맞는 상품이 없습니다. 필터를 변경해 주세요.")
else:
    choices = filtered.index.tolist()
    chosen = st.selectbox(
        "검토할 품번", choices,
        format_func=lambda idx: f"{filtered.loc[idx, '품번']} | {filtered.loc[idx, '상품명']}",
    )
    row = filtered.loc[chosen]
    left, right = st.columns([1, 2])
    with left:
        if valid_http_url(row["이미지URL"]):
            try:
                st.image(row["이미지URL"], caption=row["품번"])
            except Exception:
                st.warning("이미지를 가져오지 못했습니다. 출처 링크에서 확인해 주세요.")
        else:
            st.caption("등록된 대표 이미지 없음")
    with right:
        st.markdown(f"**{row['상품명']}**")
        for col in ("품번", "브랜드", "유형", "시즌", "시즌확정여부", "겉감",
                    "안감/기타", "제조연월", "제조국", "가격", "검증상태", "디자인분석"):
            if str(row[col]).strip():
                st.write(f"**{col}**: {row[col]}")
        if valid_http_url(row["출처URL"]):
            st.link_button("공식 상품 상세 페이지", row["출처URL"])

st.subheader("④ 자료 누락 현황")
coverage = pd.DataFrame([
    ("겉감", n_fabric),
    ("제조연월", int(df["제조연월"].str.strip().ne("").sum())),
    ("대표 이미지 URL", n_pics),
    ("시즌 근거 확인", n_season_confirmed),
], columns=["항목", "기재 품번"])
coverage["미확보 품번"] = len(df) - coverage["기재 품번"]
st.dataframe(coverage, use_container_width=True, hide_index=True)
if not filtered.empty:
    st.bar_chart(filtered["유형"].value_counts())
st.caption("제품명/소재/제조연월은 각 출처의 기록이며, 누락값은 추정하지 않습니다.")

st.subheader("⑤ 다운로드")
st.download_button(
    "현재 필터 결과 CSV", filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name="daks_men_filtered.csv", mime="text/csv",
)
try:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        filtered.to_excel(writer, sheet_name="PRODUCTS", index=False)
        coverage.to_excel(writer, sheet_name="COVERAGE", index=False)
    st.download_button(
        "현재 필터 결과 Excel", output.getvalue(),
        file_name="daks_men_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
except (ImportError, ModuleNotFoundError):
    st.caption("Excel 내보내기는 openpyxl 설치 시 활성화됩니다. CSV 내보내기는 항상 가능합니다.")

st.caption("CSV 원본: " + ("GitHub 저장소 파일" if data_source != REPO_RAW else "GitHub Raw URL"))
