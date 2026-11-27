# 워크크(Walk Creator Crew) 백엔드

워크크 서비스의 FastAPI 백엔드입니다. 화면은 프론트 저장소 [Meoning-Reosin-frontend](https://github.com/Meoning-Reosin/Meoning-Reosin-frontend)에 있고, 화면까지 보려면 두 저장소를 모두 실행해야 합니다.

## 1. 준비물

| 필요한 것 | 확인 명령 | 설치 (macOS) |
| --- | --- | --- |
| Git | `git --version` | `brew install git` |
| Python **3.12** | `python3.12 --version` | `brew install python@3.12` |
| `.env` 파일 | — | 강현에게 개인 메시지로 받기 (단톡방이나 깃에 올리지 않기) |

Windows는 [python.org](https://www.python.org/downloads/)에서 3.12를 설치합니다.

두 저장소를 한 폴더 아래 나란히 두는 것을 권장합니다.

```
~/wcc/
  backend/    이 저장소
  frontend/   프론트 저장소
```

## 2. 클론

```bash
mkdir -p ~/wcc && cd ~/wcc
git clone https://github.com/Meoning-Reosin/Meoning-Reosin-backend.git backend
cd backend
```

## 3. 가상환경 만들고 패키지 설치

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows(PowerShell)는 `source .venv/bin/activate` 대신 `.venv\Scripts\Activate.ps1` 을 실행합니다.

## 4. `.env` 넣기

강현에게 받은 `.env` 파일을 `backend` 폴더 바로 아래(`README.md`와 같은 위치)에 넣습니다. `.env`는 깃에 올라가지 않습니다.

받은 파일에서 **`JWT_SECRET`만 비어 있습니다.** 아래 명령으로 나온 긴 글자를 `JWT_SECRET=` 뒤에 붙여 넣습니다. 로그인 토큰을 서명하는 내 컴퓨터 전용 열쇠라서 사람마다 따로 만들고, 다른 사람과 같은 값을 쓰지 않습니다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```
JWT_SECRET=위 명령으로 나온 글자
```

나머지 값은 받은 그대로 둡니다. 모두 각자 노트북의 127.0.0.1에서 실행하는 기준이라 팀원 모두 같은 값을 씁니다.

| 변수 | 값 | 설명 |
| --- | --- | --- |
| `GOOGLE_CLIENT_ID` | 받은 그대로 | Google 로그인용. 팀 전체가 같은 값 |
| `GOOGLE_CLIENT_SECRET` | 받은 그대로 | 비밀값. 팀 전체가 같은 값 |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:8000/api/v1/auth/oauth/google/callback` | Google 콘솔에 등록된 주소와 같아야 함 |
| `JWT_SECRET` | **직접 만든 값** | 위 명령으로 만듦. 비워 두면 서버를 다시 켤 때마다 로그인이 풀림 |
| `FRONTEND_URL` | `http://127.0.0.1:5173/login/done` | 로그인 후 돌아갈 프론트 주소 |
| `FRONTEND_SIGNUP_URL` | `http://127.0.0.1:5173/signup` | 처음 로그인한 사람이 갈 가입 동의 화면 |
| `CORS_ORIGINS` | 비어 있음 | 프론트 개발 서버가 대신 전달해서 필요 없음 |
| `COOKIE_SECURE` | `false` | HTTPS로 배포할 때만 `true` |

`.env`를 아직 못 받았다면 `cp .env.example .env`로 빈 파일을 만들어도 서버는 켜집니다. 이때는 Google 로그인만 안 되고 나머지 API는 쓸 수 있습니다. Google 로그인은 Google 콘솔에 테스트 사용자로 등록된 계정만 됩니다.

## 5. 실행

```bash
cd ~/wcc/backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

다음부터는 이 5번만 하면 됩니다. 끌 때는 터미널에서 `Ctrl+C`를 누릅니다.

## 6. 확인

| 주소 | 기대 결과 |
| --- | --- |
| http://127.0.0.1:8000/health | `{"status":"ok"}` |
| http://127.0.0.1:8000/docs | API 문서 화면 |
| http://127.0.0.1:8000/api/v1/places | 관광지 10곳 |

화면까지 보려면 이어서 프론트 저장소 README대로 프론트를 켜고 **http://127.0.0.1:5173** 을 엽니다.

테스트 실행(선택):

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## 7. 자주 막히는 문제

| 증상 | 해결 |
| --- | --- |
| `Address already in use` | 8000번에 서버가 이미 켜져 있습니다. 켜 둔 터미널에서 `Ctrl+C`로 끄고 다시 실행합니다 |
| 로그인 후 `{"status":"signup_required", ...}` 글자만 보임 | `.env`의 `FRONTEND_URL`, `FRONTEND_SIGNUP_URL`을 채우고 서버를 다시 켭니다 |
| 로그인했는데 로그아웃 상태로 보임 | 프론트를 `localhost`가 아니라 **127.0.0.1:5173** 으로 엽니다 |
| Google 화면에서 "액세스 차단됨" | 강현에게 Google 콘솔 테스트 사용자 추가를 요청합니다 |
| "확인되지 않은 앱" 경고 | 앱이 테스트 상태라서 뜹니다. **계속**을 누릅니다 |
| 가입·찜·일정이 사라짐 | 아직 DB가 없어 서버를 다시 켜면 초기화됩니다. 다시 가입하면 됩니다 |
| `.venv`가 동작하지 않음 | 폴더를 옮기거나 이름을 바꾼 경우입니다. `.venv`를 지우고 3번을 다시 합니다 |
| `.env`를 고쳤는데 그대로 | `.env`는 서버를 켤 때만 읽습니다. 서버를 다시 켭니다 |
| 서버를 다시 켤 때마다 로그인이 풀림 | `.env`의 `JWT_SECRET`이 비어 있습니다. 4번 명령으로 만들어 채웁니다 |
| 받은 `.env`가 적용되지 않음 | 파일 이름이 정확히 `.env`인지(앞에 점, 뒤에 `.txt` 없이), `backend` 폴더 바로 아래에 있는지 확인합니다 |
