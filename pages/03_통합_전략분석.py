"""Menswear Intel v3.4 — Streamlit page: pages/03_통합_전략분석.py."""
import base64
import io
import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from html import escape
from urllib.parse import urldefrag, urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

BRANDS = {
    '캠브리지 멤버스': ('https://www.kolonmall.com/Brands/CAMBRIDGE-MEMBERS', 'kolonmall.com'),
    '갤럭시': ('https://m.ssfshop.com/Galaxy/main?brandShopNo=BDMA04A01&brndShopId=HMBGA', 'ssfshop.com'),
}
COLS = ['brand', 'season', 'category', 'product_name', 'product_id', 'price', 'list_price',
        'material', 'composition', 'url', 'source_category', 'collected_at', 'evidence']
CATEGORY_RULES = [
    ('수트', ['수트', '정장', 'SUIT', '셋업']),
    ('재킷', ['재킷', '자켓', 'JACKET', 'BLAZER']),
    ('아우터', ['아우터', '코트', '점퍼', '패딩', '다운', 'OUTER', 'COAT', 'JUMPER']),
    ('셔츠', ['셔츠', 'SHIRT']),
    ('니트', ['니트', '스웨터', '가디건', 'KNIT', 'SWEATER']),
    ('팬츠', ['팬츠', '바지', '슬랙스', 'TROUSER', 'PANTS', 'SLACKS']),
    ('티셔츠', ['티셔츠', 'T-SHIRT', 'POLO']),
    ('액세서리', ['ACC', '벨트', '타이', 'SCARF']),
]
MATERIALS = ['캐시미어', '울', '모헤어', '알파카', '린넨', '리넨', '면', '코튼', '실크',
             '폴리에스터', '나일론', '레이온', '비스코스', '스판', '라이오셀', '텐셀', '가죽', '스웨이드', '다운']
HEADERS = {'User-Agent': 'MenswearIntelResearch/3.4 (public pages, low request rate)'}
REMOTE_PATH = 'data/menswear_public_products.csv'
HISTORY_PATH = 'data/menswear_public_history.csv'


def clean_text(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ''
    return str(value).strip()


def normalize_brand(value):
    text = clean_text(value)
    lower = text.lower()
    if 'cambridge' in lower or '캠브리지' in lower:
        return '캠브리지 멤버스'
    if 'galaxy' in lower or '갤럭시' in lower:
        return '갤럭시'
    if 'daks' in lower or '닥스' in lower:
        return '닥스'
    return text or '미확인'


def category_of(value):
    text = clean_text(value).upper()
    for category, keys in CATEGORY_RULES:
        if any(key.upper() in text for key in keys):
            return category
    return '미분류'


def season_of(value):
    text = clean_text(value).upper()
    match = re.search(r'(?<!\d)(20\d{2})\s*[-_/ ]?\s*(SS|S/S|FW|F/W)(?![A-Z])', text)
    if match:
        return match.group(1) + ('SS' if match.group(2) in ('SS', 'S/S') else 'FW')
    match = re.search(r'(?<!\d)(\d{2})\s*[-_/ ]?\s*(SS|FW)(?![A-Z])', text)
    return '20' + match.group(1) + match.group(2) if match else '미확인'


def number(value):
    if isinstance(value, (int, float)) and pd.notna(value):
        return float(value)
    text = re.sub(r'[^\d.]', '', clean_text(value))
    try:
        return float(text) if text else None
    except ValueError:
        return None


def first(value):
    if isinstance(value, list):
        return first(value[0]) if value else ''
    if isinstance(value, dict):
        return clean_text(value.get('name') or value.get('value'))
    return clean_text(value)


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def extract(soup, url, brand, source_category):
    rows = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (ValueError, TypeError):
            continue
        for item in objects(data):
            kind = item.get('@type', [])
            if not (('Product' in kind) if isinstance(kind, list) else kind == 'Product'):
                continue
            name = first(item.get('name'))
            if not name:
                continue
            offers = item.get('offers') or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if not isinstance(offers, dict):
                offers = {}
            description = first(item.get('description'))
            product_id = first(item.get('sku') or item.get('productID'))
            product_url = urljoin(url, first(item.get('url')) or url)
            materials = ', '.join(m for m in MATERIALS if m in (name + ' ' + description))
            rows.append(dict(
                brand=brand, season=season_of(' '.join([name, description, product_id, product_url])),
                category=category_of(source_category + ' ' + name), product_name=name,
                product_id=product_id, price=number(offers.get('price') or offers.get('lowPrice')),
                list_price=None, material=materials, composition=description[:500],
                url=product_url, source_category=source_category,
                collected_at=datetime.now(timezone.utc).isoformat(), evidence='Product JSON-LD'))
    return rows



def extract_product_meta(soup, url, brand, source_category):
    """Conservative fallback for product detail pages lacking Product JSON-LD."""
    def meta(*keys):
        for key in keys:
            tag = soup.find('meta', attrs={'property': key}) or soup.find('meta', attrs={'name': key})
            if tag and tag.get('content'):
                return tag['content'].strip()
        return ''

    title = meta('og:title', 'twitter:title')
    price = meta('product:price:amount', 'og:price:amount', 'twitter:data1')
    description = meta('og:description', 'description')
    canonical = soup.find('link', rel='canonical')
    product_url = urljoin(url, canonical.get('href')) if canonical and canonical.get('href') else url
    # Do not invent products from listing/category pages or generic site titles.
    if not title or not price or number(price) is None:
        return []
    if any(word in title.lower() for word in ['공식 온라인', '브랜드관', 'brand shop']):
        return []
    product_id = meta('product:retailer_item_id', 'product:sku')
    material = ', '.join(m for m in MATERIALS if m in title + ' ' + description)
    return [dict(brand=brand, season=season_of(' '.join([title, description, product_id, product_url])),
                 category=category_of(source_category + ' ' + title), product_name=title,
                 product_id=product_id, price=number(price), list_price=None,
                 material=material, composition=description[:500], url=product_url,
                 source_category=source_category, collected_at=datetime.now(timezone.utc).isoformat(),
                 evidence='상품 상세 메타태그 (검증 필요)')]

def in_domain(url, domain):
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and (parsed.hostname == domain or
                                                     (parsed.hostname or '').endswith('.' + domain))


def link_kind(url, brand):
    path = urlparse(url).path.lower()
    if brand == '캠브리지 멤버스' and '/brands/cambridge-members/' not in path:
        return None
    if brand == '갤럭시' and not any(x in path for x in ['galaxy', 'product', 'goods', 'category']):
        return None
    if any(x in path for x in ['/product/', '/goods/', '/goodsdetail', '/productdetail']):
        return 'product'
    if any(x in path for x in ['/list/', '/category/', '/categories/', '/special/', '/collection/']):
        return 'listing'
    return None


def crawl(brand, max_pages=60, delay=1.5, extra=''):
    root, domain = BRANDS[brand]
    listings = deque([(root, '브랜드 메인')])
    products = deque()
    seen, queued = set(), {root}
    rows, logs = [], []
    links_found = 0
    detail_visited = 0
    jsonld_found = 0
    meta_found = 0
    listing_streak = 0
    for raw in extra.splitlines():
        url = urldefrag(raw.strip())[0]
        if in_domain(url, domain) and url not in queued:
            listings.append((url, '사용자 지정'))
            queued.add(url)
    session = requests.Session()
    session.headers.update(HEADERS)
    while (listings or products) and len(seen) < max_pages:
        # Visit product details after at most two listing pages.
        take_product = bool(products) and (not listings or listing_streak >= 2)
        if take_product:
            url, source = products.popleft()
            listing_streak = 0
        else:
            url, source = listings.popleft()
            listing_streak += 1
        is_detail = link_kind(url, brand) == 'product'
        if is_detail:
            detail_visited += 1
        if url in seen:
            continue
        seen.add(url)
        try:
            response = session.get(url, timeout=15, allow_redirects=True)
            if not in_domain(response.url, domain):
                logs.append(f'외부 도메인 리다이렉트 제외: {url}')
                continue
            if response.status_code in (403, 429):
                logs.append(f'접근 제한 HTTP {response.status_code}: {url}')
                break
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type', '').lower():
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            found = extract(soup, response.url, brand, source)
            if found:
                jsonld_found += len(found)
            elif is_detail:
                found = extract_product_meta(soup, response.url, brand, source)
                meta_found += len(found)
            rows.extend(found)
            discovered = 0
            for anchor in soup.select('a[href]'):
                target = urldefrag(urljoin(response.url, anchor['href']))[0]
                if not in_domain(target, domain) or target in queued:
                    continue
                kind = link_kind(target, brand)
                if kind is None:
                    continue
                queued.add(target)
                discovered += 1
                links_found += 1
                if len(queued) > max_pages * 100:
                    break
                (listings if kind == 'listing' else products).append(
                    (target, category_of(anchor.get_text(' ', strip=True) + ' ' + target)))
            logs.append(f'HTTP {response.status_code} / 상품 {len(found)} / 신규링크 {discovered}: {url}')
        except requests.RequestException as exc:
            logs.append(f'요청 실패 {type(exc).__name__}: {url}')
        time.sleep(delay)
    frame = pd.DataFrame(rows, columns=COLS)
    if not frame.empty:
        frame = standardize(frame)[COLS]
    return frame, logs, {'visited': len(seen), 'discovered': links_found,
                         'listing_queue_remaining': len(listings),
                         'product_queue_remaining': len(products), 'extracted': len(frame),
                         'detail_visited': detail_visited, 'jsonld_found': jsonld_found,
                         'meta_found': meta_found}


def empty_frame():
    return pd.DataFrame(columns=COLS)


def standardize(raw, source_name=''):
    """Handles empty frames, duplicate/aliased columns and missing values safely."""
    if raw is None:
        raw = empty_frame()
    df = raw.copy()
    alias = {'브랜드': 'brand', '시즌': 'season', '카테고리': 'category',
             '상품명': 'product_name', '품번': 'product_id', '판매가': 'price',
             '정상가': 'list_price', '소재': 'material', '혼용률': 'composition',
             '상품URL': 'url', '상품 url': 'url'}
    df.columns = [alias.get(str(col).strip(), str(col).strip()) for col in df.columns]
    # Duplicate columns can arise when Korean/English CSV headers coexist.
    if df.columns.duplicated().any():
        consolidated = {}
        for col in dict.fromkeys(df.columns):
            matching = df.loc[:, df.columns == col]
            if matching.shape[1] == 1:
                consolidated[col] = matching.iloc[:, 0]
            else:
                consolidated[col] = matching.replace(r'^\s*$', pd.NA, regex=True).bfill(axis=1).iloc[:, 0]
        df = pd.DataFrame(consolidated, index=df.index)
    if 'brand' not in df.columns:
        df['brand'] = normalize_brand(source_name)
    for col in COLS:
        if col not in df.columns:
            df[col] = None
    df = df[COLS].copy()
    if df.empty:
        df['style_key'] = pd.Series(dtype='str')
        df['data_quality'] = pd.Series(dtype='float64')
        return df
    df['brand'] = df['brand'].map(normalize_brand)
    text_cols = ['product_name', 'product_id', 'url', 'material', 'composition',
                 'source_category', 'season', 'category', 'collected_at', 'evidence']
    for col in text_cols:
        df[col] = df[col].map(clean_text)
    df['season'] = df.apply(
        lambda row: row['season'].upper() if re.fullmatch(r'20\d{2}(SS|FW)', row['season'].upper())
        else season_of(' '.join([row['season'], row['product_name'], row['product_id'], row['url']])), axis=1)
    df['category'] = df.apply(
        lambda row: row['category'] if row['category'] not in ('', '미분류')
        else category_of(row['product_name'] + ' ' + row['source_category']), axis=1)
    for col in ['price', 'list_price']:
        df[col] = pd.to_numeric(df[col].map(number), errors='coerce')
        df.loc[df[col] <= 0, col] = float('nan')
    # Prefer product ID; URL fallback; product name last.
    df['style_key'] = df.apply(
        lambda row: row['product_id'] or (row['product_name'] if '/search/' in row['url'] else (row['url'] or row['product_name'])), axis=1)
    df = df[df['style_key'].str.len() > 0].copy()
    df = df.drop_duplicates(['brand', 'style_key'], keep='last').reset_index(drop=True)
    if df.empty:
        df['data_quality'] = pd.Series(dtype='float64')
    else:
        df['data_quality'] = df.apply(
            lambda row: sum([bool(row['product_name']), row['category'] != '미분류',
                             row['season'] != '미확인', pd.notna(row['price']),
                             bool(row['material'])]) / 5, axis=1)
    return df


def merge_latest(*frames):
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return standardize(empty_frame())
    return standardize(pd.concat(usable, ignore_index=True))


def group_stats(df):
    if df.empty:
        return pd.DataFrame(columns=['brand', 'season', 'category', 'styles', 'median_price',
                                     'min_price', 'max_price', 'material_coverage', 'quality'])
    return df.groupby(['brand', 'season', 'category'], dropna=False).agg(
        styles=('style_key', 'nunique'), median_price=('price', 'median'),
        min_price=('price', 'min'), max_price=('price', 'max'),
        material_coverage=('material', lambda s: round(s.fillna('').astype(str).str.len().gt(0).mean() * 100, 1)),
        quality=('data_quality', 'mean')).reset_index()


def insights(df, season):
    sample = df if season == '전체' else df[df['season'] == season]
    if sample.empty:
        return ['선택한 시즌에 분석할 상품이 없습니다.']
    results = []
    if sample['brand'].nunique() < 2:
        results.append('비교 브랜드가 1개뿐이므로 브랜드 간 상품 공백을 판단할 수 없습니다.')
    if (sample['season'] == '미확인').mean() > .2:
        results.append('시즌 미확인 상품이 많습니다. 시즌별 비교 전 원문 검증이 필요합니다.')
    if (sample['category'] == '미분류').mean() > .15:
        results.append('미분류 상품이 많아 카테고리 구성비가 왜곡될 수 있습니다.')
    if sample['price'].notna().mean() < .6:
        results.append('가격 확보율이 낮아 가격 포지셔닝 판단을 보류해야 합니다.')
    daks = sample[sample['brand'] == '닥스']
    competitors = sample[sample['brand'].isin(BRANDS)]
    if daks.empty:
        results.append('닥스 비교 데이터가 없습니다. 공개 상품 CSV를 추가할 수 있습니다.')
    elif not competitors.empty:
        results.append('닥스 6건의 검색 표본은 전수조사가 아니므로 경쟁사와 상품 공백·구성비를 직접 비교할 수 없습니다.')
        gaps = sorted((set(competitors['category']) - set(daks['category'])) - {'미분류'})
        if gaps:
            results.append('탐색용: 현재 경쟁사 표본에만 보이는 카테고리 — ' + ', '.join(gaps) + '. 닥스 미전개를 뜻하지는 않습니다.')
    results.append('모든 결과는 확보된 공개몰 표본 기준이며 매출, 판매량, 수요를 의미하지 않습니다.')
    return results


def report_html(df, season, notes):
    view = df if season == '전체' else df[df['season'] == season]
    summary = group_stats(view)
    table = summary.to_html(index=False, border=0, na_rep='—', escape=True)
    bullets = ''.join('<li>' + escape(note) + '</li>' for note in notes)
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Menswear Intel v3.4</title>'
            '<style>body{font-family:Arial,sans-serif;max-width:1080px;margin:40px auto;color:#20242b}'
            'h1{color:#12354b}table{border-collapse:collapse;width:100%;font-size:13px}'
            'td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}th{background:#e9f0f4}'
            '.muted{color:#777}</style></head><body>'
            '<h1>Menswear Intel v3.4 | 시즌별 상품기획 리포트</h1>'
            '<p class="muted">시즌: ' + escape(season) + ' · 생성: ' + datetime.now().strftime('%Y-%m-%d %H:%M') + '</p>'
            '<h2>분석 범위</h2><p>확보 상품 ' + str(len(view)) + '개 · 브랜드 ' +
            str(view['brand'].nunique()) + '개 · 공개몰 표본 (전수조사 아님)</p>'
            '<h2>경쟁사 비교</h2>' + table + '<h2>기획 검토 포인트</h2><ul>' + bullets + '</ul>'
            '<h2>검증 절차</h2><p>시즌·품번 검증 → 수집 범위 확인 → 가격·소재 원문 검증 → MD 의견 대조 → 개발 우선순위 결정</p>'
            '<p class="muted">자동 분석은 의사결정 보조 자료입니다.</p></body></html>')


def github_config():
    try:
        return (str(st.secrets.get('GITHUB_TOKEN', '')),
                str(st.secrets.get('GITHUB_DATA_REPO', '')),
                str(st.secrets.get('GITHUB_DATA_BRANCH', 'main')))
    except Exception:
        return '', '', 'main'


def github_request(method, path, payload=None, sha=None):
    token, repo, branch = github_config()
    if not (token and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo)):
        raise RuntimeError('GitHub 저장소 연결이 설정되지 않았습니다.')
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    if method == 'GET':
        response = requests.get(url, headers=headers, params={'ref': branch}, timeout=20)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    body = {'message': 'Update Menswear Intel public data',
            'content': base64.b64encode(payload).decode('ascii'), 'branch': branch}
    if sha:
        body['sha'] = sha
    response = requests.put(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response.json()


def read_remote(path):
    obj = github_request('GET', path)
    if obj is None:
        return empty_frame(), None
    content = base64.b64decode(obj['content'])
    if not content.strip():
        return empty_frame(), obj['sha']
    return pd.read_csv(io.BytesIO(content), encoding='utf-8-sig'), obj['sha']


def write_remote(path, frame, sha):
    github_request('PUT', path, frame.to_csv(index=False).encode('utf-8-sig'), sha=sha)


def load_remote():
    raw, _ = read_remote(REMOTE_PATH)
    return standardize(raw)[COLS]


def save_remote(frame):
    """Save latest snapshot and append date-based history. Only call for public crawls."""
    if frame.empty:
        return len(load_remote()), 0
    # Save history first so failures are visible; latest snapshot stays compatible with old data.
    history_raw, history_sha = read_remote(HISTORY_PATH)
    new = standardize(frame)[COLS].copy()
    history = pd.concat([history_raw, new], ignore_index=True)
    history = history.reindex(columns=COLS)
    # A row represents a distinct product on a collection date; repeated reruns don't duplicate it.
    history['_date'] = history['collected_at'].fillna('').astype(str).str[:10]
    history['_identity'] = history['product_id'].fillna('').astype(str).str.strip()
    blank = history['_identity'].eq('')
    history.loc[blank, '_identity'] = history.loc[blank, 'url'].fillna('').astype(str)
    blank = history['_identity'].eq('')
    history.loc[blank, '_identity'] = history.loc[blank, 'product_name'].fillna('').astype(str)
    history = history.drop_duplicates(['brand', '_identity', '_date'], keep='last')
    history = history[COLS]
    write_remote(HISTORY_PATH, history, history_sha)
    old_raw, old_sha = read_remote(REMOTE_PATH)
    latest = merge_latest(old_raw, new)[COLS]
    write_remote(REMOTE_PATH, latest, old_sha)
    return len(latest), len(history)


def add_public(frame):
    if frame.empty:
        st.warning('이번 수집에서 추출된 상품이 0건입니다. 기존 데이터는 유지하며 GitHub에도 빈 결과를 저장하지 않습니다.')
        return
    old = st.session_state.get('v3_crawl', empty_frame())
    st.session_state['v3_crawl'] = merge_latest(old, frame)[COLS]
    token, repo, _ = github_config()
    if token and repo:
        try:
            count, history_count = save_remote(frame)
            st.success(f'GitHub 공개 상품 저장 완료: 최신 {count}건 / 날짜별 기록 {history_count}건')
        except Exception as exc:
            st.error(f'GitHub 저장 실패: {type(exc).__name__}. 아래 누적 CSV를 백업해 주세요.')
    else:
        st.info('GitHub 연결이 없어 현재 세션에만 저장했습니다. CSV 백업을 이용해 주세요.')


st.set_page_config(page_title='Menswear Intel v3.4 통합 전략', page_icon='📊', layout='wide')
st.title('📊 Menswear Intel v3.4 | 통합 전략 분석')
st.caption('공개몰 수집 → 데이터 누적·정제 → 경쟁사 비교 → 시즌별 기획 리포트')
st.warning('공개 Streamlit 앱에는 사내 매출·원가·고객정보를 업로드하지 마세요. GitHub 자동 저장은 공개몰 수집 결과에만 적용됩니다.')

if 'v3_remote_checked' not in st.session_state:
    st.session_state['v3_remote_checked'] = True
    token, repo, _ = github_config()
    if token and repo:
        try:
            st.session_state['v3_crawl'] = load_remote()
        except Exception as exc:
            st.warning(f'GitHub 저장 데이터 불러오기 실패: {type(exc).__name__}')

with st.expander('① 경쟁사 공식몰 추가 수집 (카테고리 우선 탐색)'):
    st.caption('공식몰 공개 HTML의 Product JSON-LD 및 상품 상세 메타태그를 확인합니다. JavaScript 전용 상품 정보는 수집되지 않을 수 있으며 전체 상품 수집은 보장하지 않습니다.')
    brand = st.selectbox('브랜드', list(BRANDS), key='v3_brand')
    pages = st.slider('최대 방문 페이지', 10, 200, 60, 10, key='v3_pages')
    delay = st.slider('요청 간 대기(초)', 1.0, 5.0, 1.5, .5, key='v3_delay')
    extra = st.text_area('추가 카테고리 URL (선택)', key='v3_extra')
    if st.button('카테고리 우선 수집 실행', type='primary'):
        with st.spinner('공식몰 공개 페이지를 확인하고 있습니다...'):
            data, logs, crawl_stats = crawl(brand, pages, delay, extra)
        add_public(data)
        st.session_state['v3_logs'] = logs
        st.session_state['v3_stats'] = crawl_stats
    if 'v3_stats' in st.session_state:
        crawl_stats = st.session_state['v3_stats']
        a, b, c = st.columns(3)
        a.metric('방문 페이지', crawl_stats['visited'])
        b.metric('신규 링크', crawl_stats['discovered'])
        c.metric('이번 추출 상품', crawl_stats['extracted'])
        st.caption(f"상품 상세 방문 {crawl_stats.get('detail_visited', 0)} / JSON-LD 발견 {crawl_stats.get('jsonld_found', 0)} / 메타태그 발견 {crawl_stats.get('meta_found', 0)}")
        st.caption(f"남은 목록 {crawl_stats['listing_queue_remaining']} / 남은 상품 상세 {crawl_stats['product_queue_remaining']}")
        if crawl_stats['extracted'] == 0:
            st.info('상품 상세 페이지 방문 후에도 0건이면 사이트가 JavaScript/API로 데이터를 제공할 수 있습니다. 수집 로그와 상품 상세 URL을 확인해 주세요.')
        with st.expander('수집 로그'):
            st.code('\n'.join(st.session_state.get('v3_logs', [])))

st.subheader('② 데이터 통합 및 품질 확인')
with st.expander('💾 데이터 영구 보관 상태 / 복원'):
    token, repo, _ = github_config()
    st.write('GitHub 저장 연결: ' + (f'설정됨 ({repo})' if token and repo else '미설정'))
    st.caption('설정됨은 Secrets 확인 상태입니다. 실제 쓰기 성공 여부는 수집 후 저장 완료 메시지로 확인해 주세요.')
    if token and repo and st.button('저장된 공개 상품 다시 불러오기'):
        try:
            remote = load_remote()
            st.session_state['v3_crawl'] = merge_latest(
                st.session_state.get('v3_crawl', empty_frame()), remote)[COLS]
            st.success(f'복원 완료: GitHub 최신 상품 {len(remote)}건')
        except Exception as exc:
            st.error(f'복원 실패: {type(exc).__name__}')

st.info('닥스 데이터는 2026-10-13 LF몰 검색결과의 6건 표본입니다. 전체 브랜드 구성비·상품 공백 판단에 사용하면 안 됩니다.')
DAKS_PUBLIC = [
 ('닥스','미확인','티셔츠','[EXCLUSIVE] 다크 블루 기모 마이크로 투톤 카라넥 티셔츠','','185490','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 블루 고밀도 데님 세미 오버 핏 셔츠','','169290','','면','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 라이트블루 린넨100% 닥스훈트 반팔 셔츠','','112770','','린넨','린넨100%','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','팬츠','[EXCLUSIVE] 라이트블루 스트레치 치노 팬츠','','125370','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','티셔츠','[EXCLUSIVE] 블루 링클프리 마이크로 반팔 티셔츠','','125370','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
 ('닥스','미확인','셔츠','[EXCLUSIVE] 블루 시어서커 스트라이프 반팔 셔츠','','112770','','','','https://m.lfmall.co.kr/app/search/result/LF%EB%AA%B0DAKS%EB%B8%94%EB%A3%A8','LF몰 검색 스냅샷 2026-10-13','2026-10-13','공개 검색결과 · 판매가'),
]
daks_public_df = pd.DataFrame(DAKS_PUBLIC, columns=COLS)
st.download_button('닥스 공개 검색 스냅샷 CSV 다운로드 (6건)',
                   daks_public_df.to_csv(index=False).encode('utf-8-sig'),
                   file_name='daks_public_sample_2026_10.csv', mime='text/csv')
if st.button('닥스 공개 검색 스냅샷 6건 비교에 추가'):
    old = st.session_state.get('v3_crawl', empty_frame())
    st.session_state['v3_crawl'] = merge_latest(old, daks_public_df)[COLS]
    st.success('닥스 공개 샘플을 현재 세션에 추가했습니다. GitHub에는 자동 저장하지 않습니다.')

current = st.session_state.get('v3_crawl', empty_frame())
if not current.empty:
    st.download_button('현재 누적 수집 결과 백업 CSV', current[COLS].to_csv(index=False).encode('utf-8-sig'),
                       file_name='menswear_intel_all_brands_backup.csv', mime='text/csv')

files = st.file_uploader('상품 CSV 업로드 (여러 개 선택 가능)', type=['csv'],
                         accept_multiple_files=True, key='v3_upload')
frames = [current] if not current.empty else []
for file in files or []:
    try:
        content = file.getvalue()
        try:
            raw = pd.read_csv(io.BytesIO(content), encoding='utf-8-sig')
        except UnicodeDecodeError:
            raw = pd.read_csv(io.BytesIO(content), encoding='cp949')
        frames.append(raw)
    except Exception as exc:
        st.error(f'{file.name} 읽기 실패: {type(exc).__name__}')

if frames:
    df = merge_latest(*frames)
    if df.empty:
        st.info('분석 가능한 상품이 없습니다. 다른 CSV를 업로드하거나 수집을 실행해 주세요.')
    else:
        seasons = ['전체'] + sorted(df['season'].unique().tolist(), reverse=True)
        season = st.selectbox('분석 시즌', seasons, key='v3_season')
        view = df if season == '전체' else df[df['season'] == season]
        a, b, c, d = st.columns(4)
        a.metric('표본 스타일/SKU', len(view))
        b.metric('브랜드', view['brand'].nunique())
        c.metric('시즌 확인율', f"{(view['season'] != '미확인').mean():.0%}" if len(view) else '—')
        d.metric('가격 확보율', f"{view['price'].notna().mean():.0%}" if len(view) else '—')
        st.caption('품번이 없으면 URL, 상품명 순서로 중복 제거합니다. 동일 디자인의 컬러별 SKU는 별도 집계될 수 있습니다.')
        st.dataframe(view[['brand','season','category','product_name','product_id','price','material','data_quality','url']],
                     use_container_width=True, hide_index=True)
        if '닥스' in view['brand'].values and view['brand'].nunique() > 1:
            st.warning('닥스 6건은 특정 검색어의 편향 표본입니다. 다른 브랜드와 동등한 모집단으로 해석하지 마세요.')
        st.subheader('③ 브랜드별 상품 구성')
        counts = pd.crosstab(view['category'], view['brand'])
        if not counts.empty:
            st.bar_chart(counts)
            st.dataframe(counts, use_container_width=True)
            pct = counts.div(counts.sum(axis=0).replace(0, float('nan')), axis=1).mul(100).round(1)
            st.caption('브랜드별 카테고리 구성비 (%) — 확보된 표본 기준')
            st.dataframe(pct, use_container_width=True)
        st.subheader('④ 가격 및 소재 분석')
        stats = group_stats(view)
        st.dataframe(stats, use_container_width=True, hide_index=True)
        materials = view[view['material'].str.len() > 0].copy()
        if not materials.empty:
            materials['material_token'] = materials['material'].str.split(', ')
            materials = materials.explode('material_token')
            st.caption('소재 언급 빈도 (혼용률 아님)')
            st.dataframe(pd.crosstab(materials['material_token'], materials['brand']), use_container_width=True)
        st.subheader('⑤ 자동 인사이트 · 개발 검토 포인트')
        notes = insights(df, season)
        for note in notes:
            st.info(note)
        st.subheader('⑥ 시즌별 상품기획 리포트')
        html = report_html(df, season, notes)
        st.download_button('상품기획 HTML 리포트 다운로드', html.encode('utf-8'),
                           file_name='menswear_intel_v3_report.html', mime='text/html')
        st.download_button('정제 데이터 CSV 다운로드', df[COLS].to_csv(index=False).encode('utf-8-sig'),
                           file_name='menswear_intel_v3_cleaned.csv', mime='text/csv')
        st.download_button('비교 요약 CSV 다운로드', stats.to_csv(index=False).encode('utf-8-sig'),
                           file_name='menswear_intel_v3_summary.csv', mime='text/csv')
else:
    st.info('먼저 공식몰 수집을 실행하거나 기존 CSV를 업로드해 주세요.')
