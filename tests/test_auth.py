"""회원 API 테스트.

진짜 Google에 접속하지 않도록 GoogleOAuthClient를 가짜(FakeGoogle)로 바꿔 끼운다.
저장소와 설정도 테스트마다 새로 만들어, 테스트끼리 서로 영향을 주지 않게 한다.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import google as google_module
from app.auth.deps import get_google_client
from app.auth.google import GoogleAuthError, GoogleEmailNotVerified, GoogleOAuthClient, GoogleProfile
from app.auth.store import UserStore, get_user_store
from app.core.config import Settings, get_settings
from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE, SIGNUP_COOKIE, STATE_COOKIE
from app.main import app

CALLBACK = "/api/v1/auth/oauth/google/callback"
START = "/api/v1/auth/oauth/google/start"
PROFILE = GoogleProfile(sub="google-sub-123", email="tester@example.com", name="테스터", picture="https://img/p.png")
SIGNUP_BODY = {"agree_terms": True, "agree_privacy": True, "agree_location": True}


class FakeGoogle:
    """Google 대신 정해 둔 결과를 돌려주는 가짜."""

    def __init__(self, settings: Settings):
        self.real = GoogleOAuthClient(settings)
        self.profile = PROFILE
        self.error: Exception | None = None
        self.last_nonce: str | None = None

    def build_authorization_url(self, state: str, nonce: str) -> str:
        return self.real.build_authorization_url(state, nonce)

    async def exchange_code(self, code: str) -> str:
        if self.error:
            raise self.error
        return "fake-id-token"

    async def verify_id_token(self, id_token: str, nonce: str) -> GoogleProfile:
        self.last_nonce = nonce
        return self.profile


def make_settings(**overrides) -> Settings:
    values = dict(
        google_client_id="test-client-id",
        google_client_secret="test-secret",
        jwt_secret="test-jwt-secret-that-is-long-enough-1234",
        frontend_url="",
        frontend_signup_url="",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def env():
    """테스트용 설정·저장소·가짜 Google을 끼운 클라이언트."""
    settings = make_settings()
    store = UserStore()
    fake = FakeGoogle(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_store] = lambda: store
    app.dependency_overrides[get_google_client] = lambda: fake
    client = TestClient(app, follow_redirects=False)
    yield SimpleNamespace(client=client, settings=settings, store=store, google=fake)
    app.dependency_overrides.clear()


def start_login(client: TestClient) -> str:
    """start를 불러 state 쿠키를 받고, Google 주소에 들어 있는 state 값을 돌려준다."""
    response = client.get(START)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0]


def login_new_user(client: TestClient) -> dict:
    state = start_login(client)
    assert client.get(CALLBACK, params={"code": "abc", "state": state}).json()["status"] == "signup_required"
    response = client.post("/api/v1/auth/oauth/signup", json=SIGNUP_BODY)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------- start


def test_start_redirects_to_google_with_state_cookie(env):
    response = env.client.get(START)

    assert response.status_code == 302
    url = urlparse(response.headers["location"])
    query = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == [env.settings.google_redirect_uri]
    assert query["scope"] == ["openid email profile"]
    assert query["response_type"] == ["code"]
    assert query["state"][0] and query["nonce"][0]
    assert STATE_COOKIE in env.client.cookies


def test_start_without_google_settings_returns_503(env):
    app.dependency_overrides[get_settings] = lambda: make_settings(google_client_id="", google_client_secret="")

    response = env.client.get(START)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GOOGLE_NOT_CONFIGURED"


def test_error_message_follows_accept_language(env):
    app.dependency_overrides[get_settings] = lambda: make_settings(google_client_id="")

    response = env.client.get(START, headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.json()["detail"]["message"] == "Google sign-in is not configured yet."


# ---------------------------------------------------------------- callback


def test_callback_new_user_requires_signup(env):
    state = start_login(env.client)

    response = env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert response.status_code == 200
    assert response.json() == {
        "status": "signup_required",
        "email": "tester@example.com",
        "name": "테스터",
        "user": None,
    }
    assert SIGNUP_COOKIE in env.client.cookies
    assert ACCESS_COOKIE not in env.client.cookies


def test_callback_passes_saved_nonce_to_verification(env):
    response = env.client.get(START)
    nonce = parse_qs(urlparse(response.headers["location"]).query)["nonce"][0]
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]

    env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert env.google.last_nonce == nonce


def test_callback_rejects_wrong_state(env):
    start_login(env.client)

    response = env.client.get(CALLBACK, params={"code": "abc", "state": "forged"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_STATE"


def test_callback_rejects_missing_state_cookie(env):
    response = env.client.get(CALLBACK, params={"code": "abc", "state": "anything"})

    assert response.json()["detail"]["code"] == "INVALID_STATE"


def test_callback_cancelled_by_user(env):
    response = env.client.get(CALLBACK, params={"error": "access_denied"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "GOOGLE_LOGIN_CANCELLED"


def test_callback_cancelled_redirects_to_frontend_when_configured(env):
    app.dependency_overrides[get_settings] = lambda: make_settings(frontend_url="http://127.0.0.1:5500/")

    response = env.client.get(CALLBACK, params={"error": "access_denied"})

    assert response.status_code == 302
    assert response.headers["location"] == "http://127.0.0.1:5500/?login_error=access_denied"


def test_callback_google_failure_returns_502(env):
    env.google.error = GoogleAuthError("boom")
    state = start_login(env.client)

    response = env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "GOOGLE_AUTH_FAILED"


def test_callback_unverified_email_returns_403(env):
    env.google.error = GoogleEmailNotVerified("no")
    state = start_login(env.client)

    response = env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "GOOGLE_EMAIL_NOT_VERIFIED"


def test_callback_existing_user_logs_in(env):
    login_new_user(env.client)
    env.client.cookies.clear()

    state = start_login(env.client)
    response = env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert response.json()["status"] == "logged_in"
    assert response.json()["user"]["email"] == "tester@example.com"
    assert ACCESS_COOKIE in env.client.cookies
    assert env.client.get("/api/v1/users/me").status_code == 200


def test_callback_redirects_to_frontend_signup_page(env):
    settings = make_settings(frontend_url="http://127.0.0.1:5500/", frontend_signup_url="http://127.0.0.1:5500/#signup")
    app.dependency_overrides[get_settings] = lambda: settings
    state = start_login(env.client)

    response = env.client.get(CALLBACK, params={"code": "abc", "state": state})

    assert response.status_code == 302
    assert response.headers["location"] == "http://127.0.0.1:5500/#signup"


# ---------------------------------------------------------------- signup


def test_signup_creates_user_and_logs_in(env):
    user = login_new_user(env.client)

    assert user["email"] == "tester@example.com"
    assert user["nickname"] == "테스터"
    assert user["provider"] == "google"
    assert user["profile_image_url"] == "https://img/p.png"
    assert ACCESS_COOKIE in env.client.cookies
    assert SIGNUP_COOKIE not in env.client.cookies
    consents = env.client.get("/api/v1/users/me/consents").json()
    assert consents["terms"] and consents["privacy"] and consents["location"]
    assert consents["camera"] is False


def test_signup_requires_terms(env):
    state = start_login(env.client)
    env.client.get(CALLBACK, params={"code": "abc", "state": state})

    response = env.client.post("/api/v1/auth/oauth/signup", json={"agree_terms": True, "agree_privacy": False})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TERMS_REQUIRED"


def test_signup_without_signup_cookie_is_rejected(env):
    response = env.client.post("/api/v1/auth/oauth/signup", json=SIGNUP_BODY)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "SIGNUP_TOKEN_INVALID"


def test_signup_custom_nickname_and_language(env):
    state = start_login(env.client)
    env.client.get(CALLBACK, params={"code": "abc", "state": state})

    response = env.client.post(
        "/api/v1/auth/oauth/signup", json={**SIGNUP_BODY, "nickname": "서울산책", "language": "en"}
    )

    assert response.json()["nickname"] == "서울산책"
    assert response.json()["language"] == "en"


# ---------------------------------------------------------------- 내 정보


def test_me_requires_login(env):
    response = env.client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "NOT_AUTHENTICATED"


def test_me_accepts_bearer_header(env):
    login_new_user(env.client)
    token = env.client.cookies.get(ACCESS_COOKIE)
    env.client.cookies.clear()

    response = env.client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_me_rejects_refresh_token_used_as_access(env):
    login_new_user(env.client)
    refresh_token = env.client.cookies.get(REFRESH_COOKIE)
    env.client.cookies.clear()

    response = env.client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {refresh_token}"})

    assert response.status_code == 401


def test_update_me_changes_only_sent_fields(env):
    login_new_user(env.client)

    response = env.client.patch("/api/v1/users/me", json={"nickname": "새이름"})

    assert response.json()["nickname"] == "새이름"
    assert response.json()["language"] == "ko"


@pytest.mark.parametrize("body", [{"nickname": "a"}, {"nickname": "x" * 21}, {"language": "fr"}])
def test_update_me_validates_input(env, body):
    login_new_user(env.client)

    assert env.client.patch("/api/v1/users/me", json=body).status_code == 422


def test_update_consents(env):
    login_new_user(env.client)

    response = env.client.patch("/api/v1/users/me/consents", json={"photo_training": True, "location": False})

    assert response.json()["photo_training"] is True
    assert response.json()["location"] is False
    assert response.json()["terms"] is True


# ---------------------------------------------------------------- 토큰·로그아웃·탈퇴


def test_refresh_rotates_token(env):
    login_new_user(env.client)
    old_refresh = env.client.cookies.get(REFRESH_COOKIE)

    response = env.client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json() == {"expires_in": 3600}
    assert env.client.cookies.get(REFRESH_COOKIE) != old_refresh
    # 한 번 쓴 리프레시 토큰은 다시 쓸 수 없다.
    env.client.cookies.set(REFRESH_COOKIE, old_refresh, path="/api/v1/auth")
    assert env.client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_without_cookie_returns_401(env):
    response = env.client.post("/api/v1/auth/refresh")

    assert response.json()["detail"]["code"] == "REFRESH_TOKEN_INVALID"


def test_logout_revokes_refresh_and_clears_cookies(env):
    login_new_user(env.client)
    refresh_token = env.client.cookies.get(REFRESH_COOKIE)

    response = env.client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert ACCESS_COOKIE not in env.client.cookies
    env.client.cookies.set(REFRESH_COOKIE, refresh_token, path="/api/v1/auth")
    assert env.client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_when_not_logged_in_is_ok(env):
    assert env.client.post("/api/v1/auth/logout").status_code == 204


def test_delete_me_removes_user(env):
    user = login_new_user(env.client)
    token = env.client.cookies.get(ACCESS_COOKIE)

    response = env.client.delete("/api/v1/users/me")

    assert response.status_code == 204
    assert env.store.get(user["id"]) is None
    assert ACCESS_COOKIE not in env.client.cookies
    # 남아 있던 토큰으로도 더 이상 쓸 수 없다.
    assert env.client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---------------------------------------------------------------- ID 토큰 검증 (GoogleOAuthClient)


@pytest.fixture
def anyio_backend():
    """async 테스트를 asyncio로 실행한다 (anyio는 FastAPI와 함께 설치돼 있다)."""
    return "asyncio"


@pytest.fixture
def signing_key(monkeypatch):
    """Google 공개키 대신 테스트용 RSA 키로 서명·검증한다."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake_jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key()))
    monkeypatch.setattr(google_module, "_jwks_client", lambda: fake_jwks)
    return private_key


def make_id_token(private_key, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "sub": "google-sub-123",
        "email": "tester@example.com",
        "email_verified": True,
        "name": "테스터",
        "nonce": "n-1",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


@pytest.mark.anyio
async def test_verify_id_token_success(signing_key):
    client = GoogleOAuthClient(make_settings())

    profile = await client.verify_id_token(make_id_token(signing_key), "n-1")

    assert profile.sub == "google-sub-123"
    assert profile.email == "tester@example.com"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-else"},  # 다른 앱용 토큰
        {"iss": "https://evil.example.com"},  # Google이 발급하지 않음
        {"nonce": "other"},  # 재사용된 토큰
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},  # 만료
    ],
)
async def test_verify_id_token_rejects_bad_claims(signing_key, overrides):
    client = GoogleOAuthClient(make_settings())

    with pytest.raises(GoogleAuthError):
        await client.verify_id_token(make_id_token(signing_key, **overrides), "n-1")


@pytest.mark.anyio
async def test_verify_id_token_rejects_unverified_email(signing_key):
    client = GoogleOAuthClient(make_settings())

    with pytest.raises(GoogleEmailNotVerified):
        await client.verify_id_token(make_id_token(signing_key, email_verified=False), "n-1")
