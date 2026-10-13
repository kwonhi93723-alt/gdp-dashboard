# Menswear Intel — iPhone Safari 지원 웹 버전 v1.1

## 주요 기능
- 모바일 반응형 Streamlit 웹 대시보드
- 브랜드/시즌별 상품 DB, 카테고리 상품 수, 가격/소재 비교
- 공식몰 공개 HTML Product JSON-LD 기반 제한적 상품 수집
- CSV 보완 업로드, CSV/엑셀 내보내기
- 내부 판매/리퀘스트 파일 **미리보기만** 지원 (저장/자동 추천 미구현)
- `DATABASE_URL` 설정 시 PostgreSQL 영구 저장, 미설정 시 로컬 SQLite
- `APP_PASSWORD` 설정 시 비밀번호 접근 제어

## 모바일 공개 URL 만들기 (Streamlit Community Cloud)
1. GitHub 계정에서 **비공개 저장소**를 만듭니다. ZIP 안의 파일을 업로드합니다. (`.streamlit/secrets.toml` 파일은 업로드하지 마세요.)
2. PostgreSQL 호스팅 서비스(예: Supabase/Neon)에서 DB를 만들고 PostgreSQL 연결 문자열을 발급받습니다. 외부 접속이 가능한 호스트/SSL 설정을 확인하세요.
3. https://share.streamlit.io/ 에 로그인해 **Create app**을 누르고 GitHub 저장소를 선택합니다. 메인 파일은 `app.py`입니다.
4. 앱의 **Secrets** 설정에 다음 값을 넣습니다. 실제 값으로 변경하세요.

```toml
APP_PASSWORD = "긴-비밀번호로-변경"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require"
REQUIRE_CLOUD_DB = "true"
```

5. 배포 완료 후 발급된 `https://...streamlit.app` 주소를 아이폰 Safari에서 엽니다. 사이드바에서 비밀번호를 입력합니다.
6. Safari의 **공유 → 홈 화면에 추가**로 아이콘을 만들 수 있습니다.

> 배포는 사용자가 자신의 GitHub/Streamlit/DB 계정에서 직접 진행해야 합니다. 이 패키지에 실제 배포된 공개 URL은 포함되지 않습니다.

## 로컬 테스트
Python 3.10+ 설치 후:
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
브라우저에서 `http://localhost:8501`로 접속합니다. 로컬 DB는 `products.sqlite3`에 저장됩니다.

## 중요 한계
- **전수 조사 아님:** 목록 페이지 자동 순회, JS 렌더링, 페이지네이션은 아직 미구현입니다.
- 상품 상세 URL 입력이 가장 안정적입니다. 일부 공식몰은 JSON-LD를 제공하지 않습니다.
- 자동 카테고리 분류는 키워드 기반이며, 소재 혼용률은 누락될 수 있습니다.
- 수집 결과는 실제 전체 스타일 수가 아닌 수집된 상품 레코드 수입니다.
- 외부 공개 배포 시 `APP_PASSWORD`를 반드시 설정하고, PostgreSQL DB를 연결하세요. 비밀번호 방식은 소규모 시제품용이며 기업 SSO/세밀한 권한 관리 기능은 없습니다.
- 비밀번호를 공유하는 사용자들은 동일 DB를 사용합니다.
- 사내 판매/고객 리퀘스트 데이터는 회사 승인 전 클라우드 서비스에 업로드하지 마세요.
- 공식몰 이용약관과 robots 정책을 확인하고 차단·로그인·CAPTCHA를 우회하지 마세요.
