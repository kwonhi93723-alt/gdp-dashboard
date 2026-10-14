
import streamlit as st
import requests
import os
import urllib.request
from urllib.parse import urlparse

st.set_page_config(page_title="네트워크 진단", page_icon="🔍")
st.title("🔍 Menswear Intel | 네트워크 진단")

st.info(
    "API 키 없이 공개 사이트 접속 상태를 확인합니다. "
    "기존 수집 파일은 수정하지 않습니다."
)

SITES = {
    "Python 공식 사이트": "https://www.python.org/",
    "GitHub": "https://github.com/",
    "LF몰 robots.txt": "https://www.lfmall.co.kr/robots.txt",
    "SSG robots.txt": "https://www.ssg.com/robots.txt",
}

def diagnose(name, url):
    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        return {
            "사이트": name,
            "HTTP 코드": response.status_code,
            "결과": "접속 성공" if response.ok else "HTTP 오류",
            "상세": response.reason,
        }
    except requests.exceptions.ProxyError:
        detail = "프록시 연결 또는 인증 오류"
    except requests.exceptions.SSLError:
        detail = "SSL 인증 오류"
    except requests.exceptions.Timeout:
        detail = "연결 시간 초과"
    except requests.exceptions.RequestException as e:
        detail = type(e).__name__

    return {
        "사이트": name,
        "HTTP 코드": "-",
        "결과": "연결 실패",
        "상세": detail,
    }

if st.button("네트워크 진단 시작", type="primary"):
    results = [
        diagnose(name, url)
        for name, url in SITES.items()
    ]

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("프록시 설정 확인")

    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    ]

    for key in proxy_keys:
        value = os.environ.get(key)
        st.write(
            f"{key}: {'설정됨' if value else '설정 없음'}"
        )

    st.caption(
        "프록시 주소, 계정 정보 및 API 키는 출력하지 않습니다."
    )
