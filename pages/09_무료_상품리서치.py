
import streamlit as st
import pandas as pd
import requests
import json
import re
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup
from datetime import datetime

st.set_page_config(
    page_title="무료 상품 리서치",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 Menswear Intel | 무료 상품 리서치 v5.3")
st.caption(
    "API 키·카드 등록 없이 상품을 조사하고 "
    "디자인 리서치 데이터를 관리합니다."
)

BRANDS = [
    "닥스 남성",
    "갤럭시 남성",
    "캠브리지 멤버스",
    "마에스트로",
    "헤지스 남성",
]

CATEGORIES = [
    "재킷",
    "블루종",
    "해링턴",
    "초어 재킷",
    "봄버",
    "사파리",
    "필드 재킷",
    "코트",
    "점퍼",
    "셔츠",
    "니트",
    "팬츠",
]

YEARS = list(range(2026, 2021, -1))

if "research_items" not in st.session_state:
    st.session_state.research_items = []

def classify(title):
    text = title.lower()

    patterns = [
        ("초어 재킷", r"초어|chore"),
        ("해링턴", r"해링턴|harrington"),
        ("봄버", r"봄버|bomber|ma-1"),
        ("블루종", r"블루종|blouson"),
        ("사파리", r"사파리|safari"),
        ("필드 재킷", r"필드|field jacket"),
        ("코트", r"코트|coat"),
        ("점퍼", r"점퍼|jumper"),
        ("셔츠", r"셔츠|shirt"),
        ("니트", r"니트|knit|sweater"),
        ("팬츠", r"팬츠|바지|trouser|pants"),
        ("재킷", r"재킷|자켓|jacket"),
    ]

    for category, pattern in patterns:
        if re.search(pattern, text):
            return category

    return "미분류"

def read_metadata(url):
    parsed = urlparse(url)

    if parsed.scheme != "https":
        return None, "HTTPS 주소만 지원합니다."

    # 직접 수집이 제한된 쇼핑몰은 요청하지 않습니다.
    blocked_domains = [
        "lfmall.co.kr",
        "ssg.com",
    ]

    host = (parsed.hostname or "").lower()

    if any(
        host == domain or host.endswith("." + domain)
        for domain in blocked_domains
    ):
        return None, (
            "이 쇼핑몰은 자동 접근 제한 가능성이 있어 "
            "직접 요청하지 않습니다. "
            "상품 정보를 직접 입력해 주세요."
        )

    # 그 밖의 사이트도 자동으로 접근하지 않고
    # 사용자가 확인한 정보를 입력하도록 합니다.
    return None, (
        "사이트별 접근 허용 여부가 확인되지 않아 "
        "자동 추출을 생략합니다."
    )

st.subheader("1. 브랜드 상품 검색")

col1, col2, col3 = st.columns(3)

with col1:
    brand = st.selectbox("브랜드", BRANDS)

with col2:
    year = st.selectbox("연도", YEARS)

with col3:
    category = st.selectbox("상품 유형", CATEGORIES)

query = f"{brand} {year} {category} 상품"

google_url = (
    "https://www.google.com/search?q="
    + quote(query)
)

naver_url = (
    "https://search.naver.com/search.naver?query="
    + quote(query)
)

st.write("검색어:", query)

col_a, col_b = st.columns(2)

with col_a:
    st.link_button(
        "Google에서 검색",
        google_url,
        use_container_width=True,
    )

with col_b:
    st.link_button(
        "네이버에서 검색",
        naver_url,
        use_container_width=True,
    )

st.divider()

st.subheader("2. 상품 정보 등록")

with st.form("add_product", clear_on_submit=True):
    product_url = st.text_input(
        "상품 URL",
        placeholder="https://..."
    )

    product_name = st.text_input("상품명")

    material = st.text_input(
        "소재 및 혼용률",
        placeholder="예: 면 65%, 나일론 35%"
    )

    price = st.text_input(
        "판매가",
        placeholder="예: 399000"
    )

    image_url = st.text_input(
        "이미지 URL (선택)"
    )

    notes = st.text_area(
        "디자인 특징 및 분석 메모",
        placeholder=(
            "예: 짧은 기장, 래글런 소매, "
            "플랩 포켓, 워시드 소재"
        )
    )

    submitted = st.form_submit_button(
        "상품 추가",
        type="primary",
    )

    if submitted:
        if not product_url or not product_name:
            st.error("상품 URL과 상품명을 입력해 주세요.")
        elif urlparse(product_url).scheme not in [
            "http", "https"
        ]:
            st.error("올바른 상품 URL을 입력해 주세요.")
        else:
            st.session_state.research_items.append({
                "브랜드": brand,
                "연도": year,
                "상품 유형": classify(product_name)
                    if classify(product_name) != "미분류"
                    else category,
                "상품명": product_name,
                "소재": material,
                "가격": price,
                "이미지 URL": image_url,
                "상품 URL": product_url,
                "디자인 분석": notes,
                "등록일": datetime.now().strftime(
                    "%Y-%m-%d"
                ),
            })

            st.success("상품을 추가했습니다.")

st.divider()

st.subheader("3. 수집한 상품 비교")

items = st.session_state.research_items

if items:
    df = pd.DataFrame(items)

    st.metric("등록된 상품", len(df))

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    csv_data = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "CSV 다운로드",
        csv_data,
        file_name="menswear_research.csv",
        mime="text/csv",
    )

    st.info(
        "현재 데이터는 실행 세션에 저장됩니다. "
        "앱 재시작 시 사라질 수 있으므로 "
        "CSV를 다운로드해 보관해 주세요."
    )

else:
    st.info(
        "아직 등록된 상품이 없습니다. "
        "위에서 검색 후 상품을 추가해 주세요."
    )
