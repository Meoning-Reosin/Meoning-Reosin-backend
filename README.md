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

## 관광지 API 확인

서버를 켜고 http://127.0.0.1:8000/docs 에서 아래를 실행해 봅니다. 데이터는 `app/places/data/places.json`의 임시 데이터(A/B 코스 10곳)입니다.

- `GET /api/v1/places`: 관광지 목록. `lat`, `lng`를 보내면 가까운 순, `q=환구`로 검색
- `GET /api/v1/places/1`: 장소 상세. 헤더 `Accept-Language: en`이면 영어
- `GET /api/v1/places/1/operating-info`, `/script`: 운영 정보, 해설 대본
- `GET /api/v1/categories`, `GET /api/v1/courses`, `GET /api/v1/courses/1`: 카테고리, 추천 코스
- 찜(로그인 필요): Google 로그인을 마친 같은 브라우저에서 `POST /api/v1/bookmarks` (`{"place_id": 2}`), `GET /api/v1/bookmarks`, `DELETE /api/v1/bookmarks/2`. 찜하면 관광지 목록의 `bookmark_count`가 바로 바뀝니다

## 폴더 구조

기능별 폴더(auth, places …) 안을 다시 층(layer)으로 나눕니다. 요청은 위에서 아래로 내려갑니다.

```
요청 → router.py → service.py → repository.py / client.py → 데이터(JSON·DB) / 외부 API
```

| 파일 | 하는 일 | 하지 않는 일 |
|---|---|---|
| `router.py` | 주소, 입력 검사, 쿠키·리디렉션 | 판단(업무 규칙) |
| `schemas.py` | 요청·응답 모양 | |
| `service.py` | 업무 규칙: 가입 조건, 정렬, 거리·시간 계산 | HTTP, SQL |
| `repository.py` | 데이터 읽기·쓰기. DB를 붙일 때 이 파일만 바꿈 | 업무 규칙 |
| `client.py` / `google.py` | 외부 API 호출 (Azure, Google, TourAPI …) | 업무 규칙 |
| `errors.py` | 그 기능의 오류 코드와 한·영 메시지 | |

```
app/
  main.py          앱 시작점: 공통 오류 처리, CORS, 라우터 등록
  core/            모든 기능이 함께 쓰는 것
    config.py        설정 (.env)
    security.py      JWT·쿠키
    deps.py          로그인 확인: CurrentUser(필수), OptionalUser(선택)
    errors.py        AppError, 오류 응답 모양, Accept-Language 고르기
    geo.py           거리·도보 시간 계산
  auth/            회원: Google 로그인, 가입, 토큰, 내 정보, 탈퇴
  places/          관광지·카테고리·추천 코스 (data/places.json은 임시 데이터)
  bookmarks/       찜 (지금은 메모리 저장, 서버를 다시 켜면 사라짐)
  recognitions/    사진 인식 (client.py에 Azure AI Vision을 연결할 예정)
  itineraries/     여행 일정 (예정)
tests/             기능별 폴더 (auth/, places/, bookmarks/, recognitions/)
```

오류를 낼 때는 `raise AppError("PLACE_NOT_FOUND")`처럼 코드만 던집니다. 응답 모양 `{"detail": {"code", "message"}}`과 언어는 `core/errors.py`가 맞춰 줍니다. 새 오류 코드는 그 기능의 `errors.py`에 추가합니다.

## 테스트

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```
