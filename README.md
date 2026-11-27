# Meoning-Reosion-backend

Python 3.12를 사용합니다. 저장소를 클론한 뒤 프로젝트 폴더에서 실행합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env   # 처음 한 번. 값 채우는 방법은 .env.example 안의 설명을 보세요
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 서버 상태 확인은 http://127.0.0.1:8000/health 에서 합니다. `{"status":"ok"}`가 나오면 성공입니다.
- API 문서는 http://127.0.0.1:8000/docs 에서 확인할 수 있습니다.
- 주소는 `localhost`가 아니라 **`127.0.0.1`** 로 여세요. Google 로그인 리디렉션 주소가 127.0.0.1로 등록돼 있어서, localhost로 열면 로그인 쿠키가 전달되지 않습니다.

## Google 로그인 확인 (프론트 없이)

1. `.env`에 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `JWT_SECRET`을 채웁니다. `FRONTEND_URL`은 비워 둡니다.
2. 브라우저에서 http://127.0.0.1:8000/api/v1/auth/oauth/google/start 를 엽니다.
3. Google 콘솔에 테스트 사용자로 등록된 계정을 고릅니다.
4. 처음이면 `{"status": "signup_required", ...}`가 보입니다. http://127.0.0.1:8000/docs 에서 `POST /api/v1/auth/oauth/signup`을 실행해 가입을 마칩니다.
5. `GET /api/v1/users/me`에서 내 정보가 나오면 성공입니다.

회원 정보는 아직 DB가 없어 메모리에만 저장됩니다. 서버를 다시 켜면 사라집니다.

## 폴더 구조

```
app/
  main.py          앱 시작점. 라우터 등록, CORS
  core/            여러 기능이 함께 쓰는 것: 설정(config), JWT·쿠키(security)
  auth/            회원: Google 로그인, 가입, 토큰, 내 정보, 탈퇴
  recognitions/    사진 인식
  places/          관광지 (예정)
  itineraries/     여행 일정 (예정)
tests/             pytest 테스트
```

기능 폴더마다 `router.py`(주소), `schemas.py`(요청·응답 모양), `service.py` 또는 기능별 파일(실제 처리)이 있습니다.

## 테스트

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```
