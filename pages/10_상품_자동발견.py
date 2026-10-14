
import streamlit as st
import pandas as pd
from urllib.parse import quote
from datetime import datetime

st.set_page_config(
    page_title="상품 자동 발견",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 Menswear Intel | 상품 발견 v5.4")
st.caption("무료 · API 키 없음 · 공개 검색 링크 활용")

BRANDS = [
    "닥스 남성", "갤럭시 남성",
    "캠브리지 멤버스", "마에스트로", "헤지스 남성"
]
TYPES = [
    "재킷", "블루종", "해링턴", "초어 재킷",
    "봄버", "사파리", "필드 재킷",
    "코트", "점퍼", "셔츠", "니트", "팬츠"
]

brands = st.multiselect(
    "브랜드", BRANDS, default=["닥스 남성"]
)
years = st.multiselect(
    "연도", list(range(2026, 2021, -1)),
    default=[2026, 2025, 2024]
)
types = st.multiselect(
    "상품 유형", TYPES,
    default=["재킷", "블루종", "해링턴", "초어 재킷"]
)

if st.button("검색 링크 자동 생성", type="primary"):
    rows = []
    for brand in brands:
        for year in years:
            for typ in types:
                query = f"{brand} {year} {typ} 상품"
                rows.append({
                    "브랜드": brand,
                    "연도": year,
                    "유형": typ,
                    "검색어": query,
                    "Google": "https://www.google.com/search?q=" + quote(query),
                    "네이버": "https://search.naver.com/search.naver?query=" + quote(query),
                })

    st.session_state["search_rows"] = rows

rows = st.session_state.get("search_rows", [])

if rows:
    df = pd.DataFrame(rows)
    st.metric("생성된 검색 조합", len(df))

    st.dataframe(
        df,
        column_config={
            "Google": st.column_config.LinkColumn(
                "Google 검색", display_text="검색 열기"
            ),
            "네이버": st.column_config.LinkColumn(
                "네이버 검색", display_text="검색 열기"
            ),
        },
        hide_index=True,
        use_container_width=True,
    )

    st.download_button(
        "검색 목록 CSV 저장",
        df.to_csv(index=False).encode("utf-8-sig"),
        "menswear_search_links.csv",
        "text/csv",
    )

st.info(
    "이 페이지는 검색 링크를 일괄 생성합니다. "
    "검색 결과의 상품 URL·이미지를 자동 수집하지는 않습니다."
)
