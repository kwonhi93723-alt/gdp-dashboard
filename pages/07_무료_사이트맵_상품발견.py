
"""No-key, no-payment discovery of public product URLs through permitted XML sitemaps."""
import re, time, gzip, io
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title='무료 상품 URL 발견', page_icon='🧭', layout='wide')
st.title('🧭 Menswear Intel | 무료 사이트맵 상품 발견')
st.caption('API 키·카드·Google Cloud 불필요. 공개 사이트맵과 robots.txt에서 허용된 URL만 탐색합니다.')
st.warning('사이트맵에 상품이 없거나 접근이 제한되면 결과는 0건일 수 있습니다. 상품명·연도·이미지는 검증 없이 추정하지 않습니다.')

SITES = {
    'LF몰 (닥스)': 'https://www.lfmall.co.kr',
    'SSG.COM': 'https://www.ssg.com',
    '롯데ON': 'https://www.lotteon.com',
    '신세계인터내셔날': 'https://www.sivillage.com'
}
KEYWORDS = {
    '닥스': '닥스|daks',
    '갤럭시': '갤럭시|galaxy',
    '캠브리지멤버스': '캠브리지|cambridge'
}
UA = 'MenswearIntelPublicResearch/5.2'
HEAD = {'User-Agent': UA}

def check(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname:
        return False, 'HTTPS URL 아님'
    try:
        r = requests.get(
            f'{p.scheme}://{p.netloc}/robots.txt',
            headers=HEAD, timeout=9
        )
        if r.status_code == 404:
            return True, 'robots.txt 404'
        if r.status_code != 200:
            return False, f'robots.txt HTTP {r.status_code}'
        parser = RobotFileParser()
        parser.parse(r.text.splitlines())
        return parser.can_fetch(UA, url), 'robots.txt 확인'
    except requests.RequestException as e:
        return False, type(e).__name__

def get_xml(url):
    ok, reason = check(url)
    if not ok:
        return None, '차단/확인 불가: ' + reason
    try:
        r = requests.get(url, headers=HEAD, timeout=14)
        if r.status_code != 200:
            return None, f'HTTP {r.status_code}'
        data = r.content
        if len(data) > 8_000_000:
            return None, '파일 용량 초과'
        if data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)
        return ET.fromstring(data), 'OK'
    except (requests.RequestException, ET.ParseError, OSError) as e:
        return None, type(e).__name__

def urls_in(root):
    return [
        x.text.strip()
        for x in root.iter()
        if x.tag.split('}')[-1] == 'loc' and x.text
    ]

site = st.selectbox('조사 사이트', list(SITES))
brand = st.selectbox('브랜드', list(KEYWORDS))
max_maps = st.slider('확인할 사이트맵 개수', 2, 25, 8)
max_pages = st.slider('상품 상세 확인 상한', 0, 30, 8)

if st.button('무료로 자동 탐색', type='primary'):
    root = SITES[site]
    todo = [root+'/sitemap.xml', root+'/sitemap_index.xml']
    seen = set()
    candidates = []
    logs = []

    with st.spinner('사이트맵 접근 권한과 상품 후보를 확인하는 중...'):
        while todo and len(seen) < max_maps:
            u = todo.pop(0)
            if u in seen or urlparse(u).netloc != urlparse(root).netloc:
                continue

            seen.add(u)
            xml, status = get_xml(u)
            logs.append(f'{u}: {status}')

            if xml is None:
                continue

            links = urls_in(xml)
            if xml.tag.split('}')[-1] == 'sitemapindex':
                todo.extend(
                    x for x in links
                    if urlparse(x).netloc == urlparse(root).netloc
                )
            else:
                candidates.extend(
                    x for x in links
                    if urlparse(x).netloc == urlparse(root).netloc
                )
            time.sleep(.4)

        pat = re.compile(KEYWORDS[brand], re.I)
        product_pat = re.compile(
            r'product|goods|item|prd|/p/|/detail|/shop/', re.I
        )
        hits = list(dict.fromkeys(
            x for x in candidates
            if pat.search(x) and product_pat.search(x)
        ))

        rows = []
        for u in hits:
            rows.append({
                '브랜드': brand,
                '상품명': '미확인',
                '분류': '미확인',
                '시즌': '미확인',
                '이미지': '',
                '상품 URL': u,
                '확인상태': '사이트맵 URL 후보'
            })

        for r in rows[:max_pages]:
            u = r['상품 URL']
            ok, why = check(u)
            if not ok:
                logs.append('상세 접근 생략: ' + why)
                continue

            try:
                response = requests.get(
                    u, headers=HEAD, timeout=12
                )
                if (
                    response.status_code != 200
                    or 'html' not in response.headers.get(
                        'content-type', ''
                    ).lower()
                ):
                    continue

                soup = BeautifulSoup(
                    response.text, 'html.parser'
                )
                title = soup.find(
                    'meta', attrs={'property': 'og:title'}
                )
                img = soup.find(
                    'meta', attrs={'property': 'og:image'}
                )

                if title:
                    r['상품명'] = (
                        title.get('content', '') or '미확인'
                    )
                if img:
                    r['이미지'] = urljoin(
                        u, img.get('content', '')
                    )
                r['확인상태'] = (
                    'HTML 메타데이터 확인 (상품 검증 별도)'
                )

            except requests.RequestException as e:
                logs.append(
                    '상세 확인 실패: ' + type(e).__name__
                )
            time.sleep(.5)

        df = pd.DataFrame(rows, columns=[
            '브랜드', '상품명', '분류', '시즌',
            '이미지', '상품 URL', '확인상태'
        ])

    st.metric('발견된 URL 후보', len(df))

    if not df.empty:
        st.dataframe(
            df, use_container_width=True, hide_index=True
        )
        st.download_button(
            'CSV 다운로드',
            df.to_csv(index=False).encode('utf-8-sig'),
            'public_product_candidates.csv',
            'text/csv'
        )
    else:
        st.info(
            '이 사이트의 공개 사이트맵에서 브랜드가 포함된 '
            '상품 URL을 찾지 못했습니다. 검색 API 없이 '
            '모든 쇼핑몰 상품을 자동 발견하는 것은 보장할 수 없습니다.'
        )

    with st.expander('접근·진단 로그', expanded=True):
        st.code('\n'.join(logs))
