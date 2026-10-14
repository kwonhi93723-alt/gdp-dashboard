"""Menswear Intel v5.0 — public menswear product research.
Place in Streamlit pages/. Research sample, not complete historic assortment.
Dependencies: streamlit pandas requests beautifulsoup4 openpyxl
"""
import io
import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BRANDS = {
    "닥스 남성": ("https://www.lfmall.co.kr/", ("lfmall.co.kr",)),
    "캠브리지 멤버스": ("https://www.kolonmall.com/Brands/CAMBRIDGE-MEMBERS", ("kolonmall.com",)),
    "갤럭시": ("https://m.ssfshop.com/Galaxy/main?brandShopNo=BDMA04A01&brndShopId=HMBGA", ("ssfshop.com",)),
}
HEADERS = {"User-Agent": "MenswearIntelResearch/5.0 (public pages; respectful low-rate research)"}
BASE_COLS = ["brand", "season", "category", "product_name", "product_id", "price", "list_price", "material", "composition", "url", "source_category", "collected_at", "evidence"]
EXTRA_COLS = ["image_url", "jacket_type", "silhouette", "detail_tags", "season_evidence", "season_confidence", "composition_evidence", "source_type", "classification_evidence"]
ALL_COLS = BASE_COLS + EXTRA_COLS
FIBERS = {
    "울": r"울|양모|모(?!헤어)|wool", "캐시미어": r"캐시미어|cashmere", "면": r"면|코튼|cotton",
    "린넨": r"린넨|리넨|마(?!이크로)|linen|flax", "실크": r"실크|견|silk", "폴리에스터": r"폴리에스터|폴리|polyester",
    "나일론": r"나일론|nylon|polyamide", "레이온": r"레이온|비스코스|rayon|viscose", "아크릴": r"아크릴|acrylic",
    "스판덱스": r"스판덱스|스판|폴리우레탄|엘라스테인|elastane|spandex|polyurethane",
    "알파카": r"알파카|alpaca", "모헤어": r"모헤어|mohair", "텐셀": r"텐셀|라이오셀|tencel|lyocell",
}
JACKETS = [
    ("초어 재킷", r"초어|chore|워크.?재킷|work.?jacket"),
    ("봄버 재킷", r"봄버|bomber|ma[ -]?1"),
    ("해링턴 재킷", r"해링턴|harrington"),
    ("트러커 재킷", r"트러커|trucker"),
    ("필드 재킷", r"필드.?재킷|field.?jacket|m[ -]?65|사파리.?재킷|safari.?jacket"),
    ("테일러드 재킷", r"테일러드|블레이저|blazer|tailored"),
    ("셔츠 재킷", r"셔츠.?재킷|셔츠.?자켓|shirt.?jacket|overshirt|오버셔츠"),
    ("데님 재킷", r"데님.?재킷|denim.?jacket"),
    ("퀼팅 재킷", r"퀼팅|quilted"),
    ("블루종", r"블루종|blouson"),
    ("레더 재킷", r"레더.?재킷|가죽.?재킷|leather.?jacket|스웨이드.?재킷"),
]
DETAILS = {
    "패치포켓": r"패치.?포켓|patch.?pocket", "플랩포켓": r"플랩.?포켓|flap.?pocket",
    "스탠드칼라": r"스탠드.?칼라|스탠드.?카라|stand.?collar", "립": r"립.?밴드|ribbed|rib.?hem",
    "후드": r"후드|hood", "벨트": r"벨트|belt", "체크": r"체크|check", "히든여밈": r"히든|hidden.?placket",
    "퀼팅": r"퀼팅|quilt", "워싱": r"워싱|washed|garment.?wash",
}

def clean_url(u):
    return urldefrag(u)[0]

def allowed(u, domains):
    p = urlparse(u)
    return p.scheme in ("http", "https") and any(p.hostname == d or (p.hostname or "").endswith("." + d) for d in domains)

def flatten(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from flatten(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from flatten(v)

def as_text(v):
    if isinstance(v, list):
        return as_text(v[0]) if v else ""
    if isinstance(v, dict):
        return as_text(v.get("name") or v.get("value") or "")
    return str(v or "").strip()

def number(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    m = re.search(r"\d[\d,]*", str(v or ""))
    return int(m.group().replace(",", "")) if m else None

def season(text):
    text = str(text)
    m = re.search(r"(?<!\d)(20\d{2})\s*[-_/ ]?\s*(SS|S/S|FW|F/W|SPRING|SUMMER|FALL|WINTER)(?![A-Z])", text, re.I)
    if m:
        return m.group(1) + ("SS" if m.group(2).upper() in ("SS", "S/S", "SPRING", "SUMMER") else "FW"), m.group(0), "높음"
    m = re.search(r"(?<!\d)(\d{2})\s*[-_/ ]?\s*(SS|FW)(?![A-Z])", text, re.I)
    if m:
        return "20" + m.group(1) + m.group(2).upper(), m.group(0), "중간"
    return "미확인", "", "미확인"

def category(text):
    t = str(text).lower()
    rules = [("수트", r"수트|정장|suit"), ("코트", r"코트|coat|트렌치"), ("재킷", r"재킷|자켓|jacket|블레이저|blazer|블루종|bomber"),
             ("팬츠", r"팬츠|바지|trouser|pants|슬랙스"), ("셔츠", r"셔츠|shirt"), ("니트", r"니트|스웨터|knit|sweater"),
             ("아우터", r"점퍼|패딩|다운|outer|jumper"), ("상의", r"티셔츠|t-shirt|polo")]
    for label, pat in rules:
        if re.search(pat, t, re.I):
            return label
    return "미분류"

def tags(text, patterns):
    return [label for label, pat in patterns if re.search(pat, text, re.I)]

def composition(text):
    """Only explicit fiber-percentage pairs, not generic prose."""
    matches = []
    for fiber, pat in FIBERS.items():
        a = re.search(r"(?:" + pat + r")\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*%", text, re.I)
        b = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:" + pat + r")", text, re.I)
        m = a or b
        if m and 0 < float(m.group(1)) <= 100:
            matches.append((fiber, float(m.group(1)), m.group(0)))
    if not matches:
        return "", ""
    # Reject clearly impossible aggregates; multi-part items may contain >100% and need manual review.
    if sum(x[1] for x in matches) > 100.1:
        return "", "복수 부위 또는 합계 초과: 수동 검증 필요"
    return ", ".join(f"{f} {v:g}%" for f, v, _ in matches), " / ".join(x[2] for x in matches)

def metadata(soup, key, attr="property"):
    tag = soup.find("meta", attrs={attr: key})
    return tag.get("content", "").strip() if tag else ""

def image_link(value, base):
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    if isinstance(value, list):
        value = value[0] if value else ""
    value = as_text(value)
    return urljoin(base, value) if value else ""

def row_from_product(d, soup, page, brand, source_label):
    name = as_text(d.get("name")) or metadata(soup, "og:title")
    if not name:
        return None
    desc = as_text(d.get("description")) or metadata(soup, "og:description")
    pid = as_text(d.get("sku") or d.get("productID") or d.get("mpn"))
    url = urljoin(page, as_text(d.get("url")) or page)
    offers = d.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price = number(offers.get("price") or offers.get("lowPrice"))
    img = image_link(d.get("image"), page) or metadata(soup, "og:image") or metadata(soup, "twitter:image", "name")
    img = urljoin(page, img) if img else ""
    # Visible HTML text only; excludes script/style to reduce false matches.
    body = BeautifulSoup(str(soup), "html.parser")
    for el in body(["script", "style", "noscript", "nav", "footer"]):
        el.decompose()
    visible = body.get_text(" ", strip=True)[:25000]
    short = " ".join((name, desc, pid))
    s, s_evidence, confidence = season(" ".join((name, pid, url, desc)))
    comp, comp_evidence = composition(" ".join((desc, visible)))
    materials = [fiber for fiber, pat in FIBERS.items() if re.search(pat, " ".join((name, desc)), re.I)]
    jacket_types = tags(short, JACKETS)
    if not jacket_types and category(short) == "재킷":
        jacket_types = ["기타 재킷(검토 필요)"]
    fits = tags(short, [("오버핏", r"오버핏|oversized|overfit"), ("릴랙스", r"릴랙스|relaxed"),
                        ("레귤러", r"레귤러|regular"), ("슬림", r"슬림|slim"), ("크롭", r"크롭|cropped")])
    return dict(brand=brand, season=s, category=category(short), product_name=name, product_id=pid,
                price=price, list_price=None, material=", ".join(materials), composition=comp,
                url=url, source_category=source_label, collected_at=datetime.now(timezone.utc).isoformat(),
                evidence="JSON-LD Product" if d.get("@type") else "OG meta fallback",
                image_url=img, jacket_type=", ".join(jacket_types), silhouette=", ".join(fits),
                detail_tags=", ".join(tags(short, DETAILS.items())), season_evidence=s_evidence,
                season_confidence=confidence, composition_evidence=comp_evidence,
                source_type="공개 상품 페이지", classification_evidence="상품명·설명 키워드 기반(수동 검토 권장)")

def products(soup, url, brand, source_label):
    rows = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for node in flatten(payload):
            t = node.get("@type", [])
            types = t if isinstance(t, list) else [t]
            if "Product" in types:
                r = row_from_product(node, soup, url, brand, source_label)
                if r:
                    rows.append(r)
    if not rows and (metadata(soup, "og:type") == "product" or metadata(soup, "product:price:amount")):
        d = {"name": metadata(soup, "og:title"), "description": metadata(soup, "og:description"),
             "image": metadata(soup, "og:image"), "offers": {"price": metadata(soup, "product:price:amount")}}
        r = row_from_product(d, soup, url, brand, source_label)
        if r:
            rows.append(r)
    return rows

def likely_link(url, brand):
    path = urlparse(url).path.lower()
    if brand == "닥스 남성":
        return any(k in path for k in ("product", "goods", "brand", "category", "search", "item"))
    if brand == "캠브리지 멤버스":
        return any(k in path for k in ("brand", "product", "category"))
    return any(k in path for k in ("galaxy", "product", "goods", "category", "brand"))

def robots_ok(session, url, cache):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in cache:
        try:
            res = session.get(origin + "/robots.txt", timeout=10)
            if res.status_code == 404:
                cache[origin] = None
            elif res.ok:
                rp = RobotFileParser()
                rp.parse(res.text.splitlines())
                cache[origin] = rp
            else:
                cache[origin] = False  # uncertain: do not crawl
        except requests.RequestException:
            cache[origin] = False
    rule = cache[origin]
    return rule is None or (rule is not False and rule.can_fetch(HEADERS["User-Agent"], url))

def crawl(brand, max_pages, delay, extra):
    root, domains = BRANDS[brand]
    queue = deque([(root, "브랜드 홈")])
    for line in extra.splitlines():
        link = line.strip()
        if link and allowed(link, domains):
            queue.append((clean_url(link), "사용자 제공 URL"))
    seen, rows, logs, robots_cache = set(), [], [], {}
    session = requests.Session()
    session.headers.update(HEADERS)
    while queue and len(seen) < max_pages:
        url, label = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if not robots_ok(session, url, robots_cache):
            logs.append(f"robots.txt 허용 확인 불가/차단 — 건너뜀: {url}")
            continue
        try:
            response = session.get(url, timeout=20)
            if response.status_code in (403, 429):
                logs.append(f"접근 제한 HTTP {response.status_code}: {url}")
                if response.status_code == 429:
                    break
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            found = products(soup, url, brand, label)
            rows.extend(r for r in found if allowed(r["url"], domains))
            links = []
            for a in soup.select("a[href]"):
                link = clean_url(urljoin(url, a["href"]))
                if allowed(link, domains) and likely_link(link, brand) and link not in seen:
                    links.append(link)
            for link in dict.fromkeys(links):
                if len(queue) < max_pages * 8:
                    queue.append((link, "사이트 내부 링크"))
            logs.append(f"HTTP {response.status_code} / 상품 {len(found)} / 탐색 링크 {len(links)}: {url}")
        except requests.RequestException as exc:
            logs.append(f"요청 실패 ({type(exc).__name__}): {url}")
        time.sleep(delay)
    unique = {}
    for r in rows:
        key = (r["brand"], r["product_id"] or r["url"])
        if key not in unique or (not unique[key]["image_url"] and r["image_url"]):
            unique[key] = r
    return pd.DataFrame(list(unique.values()), columns=ALL_COLS), logs, len(seen)

st.set_page_config(page_title="닥스 남성복 디자인 리서치", page_icon="🧥", layout="wide")
st.title("🧥 Menswear Intel v5.0 | 닥스 남성복 디자인 리서치")
st.caption("공개 웹 상품 표본 수집 · 재킷 세부 유형 · 이미지 갤러리 · 디자인 기획 근거 확보")
st.warning("과년도 전수 데이터가 아닙니다. 현재 접근 가능한 공개 페이지의 표본만 수집합니다. 수집일은 출시일이 아니며, 가격은 과거 시즌 가격이 아닐 수 있습니다.")
brand = st.selectbox("브랜드", list(BRANDS))
max_pages = st.slider("최대 방문 페이지", 5, 100, 25, 5)
delay = st.slider("페이지 요청 간격(초)", 1.0, 5.0, 2.0, 0.5)
extra = st.text_area("상품·카테고리 URL 추가 (한 줄에 하나)", placeholder="브랜드 공식몰의 공개 상품 URL을 입력하면 우선 수집합니다.")
if st.button("공개 상품 수집", type="primary"):
    with st.spinner("robots.txt 및 공개 상품 페이지 확인 중..."):
        df, logs, visited = crawl(brand, max_pages, delay, extra)
    st.session_state["v5_df"] = df
    st.session_state["v5_logs"] = logs
    st.session_state["v5_visited"] = visited
if "v5_df" in st.session_state:
    df = st.session_state["v5_df"]
    a, b, c = st.columns(3)
    a.metric("방문 시도", st.session_state["v5_visited"])
    b.metric("상품 표본", len(df))
    c.metric("이미지 URL 확보", int(df["image_url"].fillna("").ne("").sum()))
    if len(df):
        st.subheader("카테고리 × 시즌")
        st.dataframe(pd.crosstab(df["category"], df["season"]), use_container_width=True)
        st.subheader("재킷 유형별 표본")
        jacket_df = df[df["category"] == "재킷"]
        counts = jacket_df.assign(jacket_type=jacket_df["jacket_type"].str.split(", ")).explode("jacket_type")
        if len(counts):
            st.dataframe(counts["jacket_type"].value_counts().rename_axis("유형").reset_index(name="표본 수"), hide_index=True)
        else:
            st.info("현재 재킷으로 분류된 표본이 없습니다.")
        st.subheader("상품 사진 갤러리")
        view = df[df["image_url"].fillna("").ne("")]
        if len(view):
            cats = sorted(view["category"].dropna().unique().tolist())
            selected_cat = st.selectbox("갤러리 카테고리", ["전체"] + cats)
            if selected_cat != "전체":
                view = view[view["category"] == selected_cat]
            for start in range(0, min(len(view), 36), 3):
                columns = st.columns(3)
                for col, (_, r) in zip(columns, view.iloc[start:start+3].iterrows()):
                    with col:
                        st.image(r["image_url"], use_container_width=True)
                        st.write(r["product_name"])
                        st.caption(f"{r['brand']} · {r['season']} · {r['jacket_type'] or r['category']}")
                        st.markdown(f"[공식 상품 페이지]({r['url']})")
        else:
            st.info("공개 페이지에서 대표 이미지를 확보하지 못했습니다.")
        st.subheader("원본 데이터 및 근거")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("CSV 다운로드 (기존 13개 필드 + v5 추가 필드)", df.to_csv(index=False).encode("utf-8-sig"), file_name="menswear_v5_products.csv", mime="text/csv")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="products")
        st.download_button("Excel 다운로드", buf.getvalue(), file_name="menswear_v5_products.xlsx")
    else:
        st.info("상품 0건입니다. JS 렌더링, robots.txt, 접근 제한 또는 공개 상품 URL 부족 가능성이 있습니다. 0건은 판매 상품이 없다는 뜻이 아닙니다.")
    with st.expander("수집 진단 로그"):
        st.code("\n".join(st.session_state["v5_logs"]))
st.info("안전한 별도 페이지입니다. 기존 수집 코드와 GitHub DB를 수정하지 않습니다. 데이터는 CSV/Excel로 내려받아 검토 후 병합하세요. 이미지 저작권 및 각 사이트 이용 조건을 확인하세요.")


# 실제 검증 상품 데이터
st.divider()
st.subheader("실제 상품 조사 데이터")

import pandas as pd

csv_url = (
    "https://raw.githubusercontent.com/"
    "kwonhi93723-alt/gdp-dashboard/main/"
    "daks_men_verified_research.csv"
)

try:
    verified_df = pd.read_csv(csv_url)

    st.success(f"등록된 조사 상품: {len(verified_df)}개")

    st.dataframe(
        verified_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "출처URL": st.column_config.LinkColumn("상품 상세 링크")
        },
    )

except Exception as e:
    st.error(f"상품 데이터 불러오기 실패: {e}")
