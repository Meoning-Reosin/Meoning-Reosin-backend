"""회원 API: Google 로그인, 가입 마치기, 토큰 다시 받기, 로그아웃, 내 정보, 탈퇴.

흐름
1. 프론트가 브라우저를 GET /api/v1/auth/oauth/google/start 로 보낸다.
2. Google 로그인 후 Google이 GET /api/v1/auth/oauth/google/callback 으로 돌려보낸다.
3. 이미 가입한 사람: 로그인 쿠키를 받고 프론트로 이동.
   처음인 사람: 가입용 쿠키를 받고 약관 동의 화면으로 이동 → POST /api/v1/auth/oauth/signup.
프론트 주소(FRONTEND_URL)가 비어 있으면 콜백은 결과를 JSON으로 보여준다(프론트 없이 확인하는 개발용).
"""

import secrets
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.deps import CurrentUser, get_google_client
from app.auth.errors import auth_error, get_language
from app.auth.google import GoogleAuthError, GoogleEmailNotVerified, GoogleOAuthClient
from app.auth.schemas import (
    ConsentsResponse,
    GoogleCallbackResponse,
    RefreshResponse,
    SignupRequest,
    UpdateConsentsRequest,
    UpdateMeRequest,
    UserResponse,
)
from app.auth.store import CONSENT_TYPES, User, UserStore, get_user_store
from app.core.config import Settings, get_settings
from app.core.security import (
    REFRESH_COOKIE,
    SIGNUP_COOKIE,
    STATE_COOKIE,
    TokenError,
    clear_auth_cookies,
    clear_signup_cookie,
    clear_state_cookie,
    create_token,
    decode_token,
    set_access_cookie,
    set_refresh_cookie,
    set_signup_cookie,
    set_state_cookie,
)

# 주소 묶음 두 개. main.py에서 app.include_router()로 등록한다.
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])  # 로그인·토큰
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])  # 내 정보

# 자주 쓰는 의존성을 짧은 이름으로 묶어 둔다.
# FastAPI가 요청마다 get_settings() 등을 불러 함수 인자로 넣어 준다(테스트에서는 가짜로 바꿔 끼울 수 있다).
SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[UserStore, Depends(get_user_store)]
LangDep = Annotated[str, Depends(get_language)]  # Accept-Language 헤더 → "ko" 또는 "en"


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        profile_image_url=user.profile_image_url,
        language=user.language,
        provider=user.provider,
        created_at=user.created_at,
    )


def to_consents_response(user: User) -> ConsentsResponse:
    return ConsentsResponse(
        **{name: user.consents.get(name, False) for name in CONSENT_TYPES},
        terms_version=user.terms_version,
        updated_at=user.consents_updated_at,
    )


def issue_login_tokens(response: Response, settings: Settings, store: UserStore, user: User) -> None:
    """액세스·리프레시 토큰을 만들어 쿠키에 담고, 리프레시 토큰을 저장소에 기록한다."""
    access, _ = create_token(settings, "access", str(user.id), timedelta(minutes=settings.access_token_minutes))
    refresh, claims = create_token(settings, "refresh", str(user.id), timedelta(days=settings.refresh_token_days))
    store.save_refresh_token(claims["jti"], user.id, claims["exp"])
    set_access_cookie(response, settings, access)
    set_refresh_cookie(response, settings, refresh)


def _with_query(url: str, **params: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"


# ---------------------------------------------------------------- Google 로그인


@router.get("/oauth/google/start", status_code=status.HTTP_302_FOUND, response_class=RedirectResponse)
def google_start(
    settings: SettingsDep,
    google: Annotated[GoogleOAuthClient, Depends(get_google_client)],
    lang: LangDep,
):
    """Google 로그인 화면으로 보낸다 (API 5-1).

    위조 방지 값(state)과 재사용 방지 값(nonce)을 서명된 쿠키에 담아 두고 콜백에서 확인한다.
    """
    if not settings.google_configured:
        raise auth_error("GOOGLE_NOT_CONFIGURED", lang)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    state_token, _ = create_token(
        settings, "oauth_state", "google", timedelta(minutes=10), extra={"state": state, "nonce": nonce}
    )
    response = RedirectResponse(google.build_authorization_url(state, nonce), status_code=status.HTTP_302_FOUND)
    set_state_cookie(response, settings, state_token)
    return response


@router.get(
    "/oauth/google/callback",
    response_model=GoogleCallbackResponse,
    responses={302: {"description": "프론트 주소가 설정돼 있으면 프론트로 이동"}},
)
async def google_callback(
    settings: SettingsDep,
    store: StoreDep,
    google: Annotated[GoogleOAuthClient, Depends(get_google_client)],
    lang: LangDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    state_cookie: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
):
    """Google이 로그인 후 돌려보내는 주소 (API 5-2). 프론트가 직접 부르지 않는다."""
    # 1) 사용자가 Google 화면에서 취소하면 code 대신 error=access_denied 가 온다.
    if error:
        if settings.frontend_url:
            response = RedirectResponse(_with_query(settings.frontend_url, login_error=error), status.HTTP_302_FOUND)
            clear_state_cookie(response, settings)
            return response
        raise auth_error("GOOGLE_LOGIN_CANCELLED", lang)

    # 2) start에서 쿠키에 넣어 둔 state와 Google이 돌려준 state가 같은지 확인한다.
    #    다르면 우리가 시작하지 않은 로그인(위조 요청)이므로 거부한다.
    #    compare_digest는 비교 시간으로 값을 추측하지 못하게 하는 안전한 비교 함수다.
    try:
        saved = decode_token(settings, state_cookie, "oauth_state")
    except TokenError:
        raise auth_error("INVALID_STATE", lang)
    if not code or not state or not secrets.compare_digest(state, saved["state"]):
        raise auth_error("INVALID_STATE", lang)

    # 3) code → ID 토큰 교환, ID 토큰 검증 (Google과 통신)
    try:
        id_token = await google.exchange_code(code)
        profile = await google.verify_id_token(id_token, saved["nonce"])
    except GoogleEmailNotVerified:
        raise auth_error("GOOGLE_EMAIL_NOT_VERIFIED", lang)
    except GoogleAuthError:
        raise auth_error("GOOGLE_AUTH_FAILED", lang)

    # 4) Google 계정 고유번호(sub)로 가입한 적이 있는지 찾는다.
    user = store.get_by_provider("google", profile.sub)
    if user:
        result = GoogleCallbackResponse(
            status="logged_in", email=user.email, name=user.nickname, user=to_user_response(user)
        )
        target = settings.frontend_url
    else:
        result = GoogleCallbackResponse(status="signup_required", email=profile.email, name=profile.name)
        target = settings.frontend_signup_url or settings.frontend_url

    # 5) 프론트 주소가 있으면 그리로 이동, 없으면(개발 중) 결과를 JSON으로 보여준다.
    response: Response
    if target:
        response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    else:
        response = JSONResponse(result.model_dump(mode="json"))

    # 6) 쿠키 담기: 기존 회원은 로그인 토큰, 신규 회원은 10분짜리 가입 토큰(Google 이메일·이름 포함).
    #    가입 토큰은 아직 회원이 아니므로 다른 API는 쓸 수 없고, 가입 마치기(signup)에만 쓴다.
    if user:
        issue_login_tokens(response, settings, store, user)
        clear_signup_cookie(response, settings)
    else:
        signup_token, _ = create_token(
            settings,
            "signup",
            profile.sub,
            timedelta(minutes=settings.signup_token_minutes),
            extra={"email": profile.email, "name": profile.name, "picture": profile.picture},
        )
        set_signup_cookie(response, settings, signup_token)
    clear_state_cookie(response, settings)
    return response


@router.post("/oauth/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    response: Response,
    settings: SettingsDep,
    store: StoreDep,
    lang: LangDep,
    signup_cookie: Annotated[str | None, Cookie(alias=SIGNUP_COOKIE)] = None,
):
    """처음 로그인한 사람이 약관에 동의하고 가입을 마친다 (API 6)."""
    try:
        claims = decode_token(settings, signup_cookie, "signup")
    except TokenError:
        raise auth_error("SIGNUP_TOKEN_INVALID", lang)
    if not (body.agree_terms and body.agree_privacy):
        raise auth_error("TERMS_REQUIRED", lang)

    # 닉네임: 보낸 값 → 없으면 Google 이름(최대 20자) → 그것도 2자 미만이면 이메일 앞부분 (Q-35)
    nickname = body.nickname or (claims.get("name") or "")[:20]
    if len(nickname) < 2:
        nickname = (claims.get("email") or "user").split("@")[0][:20].ljust(2, "_")

    user = store.create(
        provider="google",
        provider_user_id=claims["sub"],
        email=claims["email"],
        nickname=nickname,
        profile_image_url=claims.get("picture"),
        language=body.language,
        consents={
            "terms": True,
            "privacy": True,
            "location": body.agree_location,
            "camera": body.agree_camera,
            "photo_training": body.agree_photo_training,
        },
        terms_version=body.terms_version,
    )
    issue_login_tokens(response, settings, store, user)
    clear_signup_cookie(response, settings)
    return to_user_response(user)


# ---------------------------------------------------------------- 토큰


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    response: Response,
    settings: SettingsDep,
    store: StoreDep,
    lang: LangDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    """액세스 토큰이 만료됐을 때 새 토큰을 받는다 (API 7).

    쓴 리프레시 토큰은 폐기하고 새 리프레시 토큰도 함께 준다(도난 피해를 줄이기 위해).
    """
    try:
        claims = decode_token(settings, refresh_cookie, "refresh")
        user_id = int(claims["sub"])
    except (TokenError, ValueError):
        raise auth_error("REFRESH_TOKEN_INVALID", lang)
    user = store.get(user_id)
    if user is None or not store.is_refresh_token_active(claims["jti"], user_id):
        clear_auth_cookies(response, settings)
        raise auth_error("REFRESH_TOKEN_INVALID", lang)
    store.revoke_refresh_token(claims["jti"])
    issue_login_tokens(response, settings, store, user)
    return RefreshResponse(expires_in=settings.access_token_minutes * 60)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    settings: SettingsDep,
    store: StoreDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    """로그아웃 (API 8). 리프레시 토큰을 폐기하고 로그인 쿠키를 지운다.

    이미 로그아웃됐거나 액세스 토큰이 만료된 상태에서 불러도 204로 끝난다.
    """
    try:
        claims = decode_token(settings, refresh_cookie, "refresh")
        store.revoke_refresh_token(claims["jti"])
    except TokenError:
        pass
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


# ---------------------------------------------------------------- 내 정보


@users_router.get("/me", response_model=UserResponse)
def read_me(user: CurrentUser):
    """내 정보 보기 (API 9)."""
    return to_user_response(user)


@users_router.patch("/me", response_model=UserResponse)
def update_me(body: UpdateMeRequest, user: CurrentUser, store: StoreDep):
    """닉네임·언어 고치기 (API 10). 보낸 값만 바뀐다."""
    changes = body.model_dump(exclude_none=True)
    if changes:
        user = store.update(user.id, **changes) or user
    return to_user_response(user)


@users_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: CurrentUser, settings: SettingsDep, store: StoreDep):
    """회원 탈퇴 (API 40). 회원 정보와 토큰을 바로 지우고 로그인 쿠키를 지운다."""
    store.delete(user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


@users_router.get("/me/consents", response_model=ConsentsResponse)
def read_consents(user: CurrentUser):
    """내 동의 상태 보기 (설정 화면용)."""
    return to_consents_response(user)


@users_router.patch("/me/consents", response_model=ConsentsResponse)
def update_consents(body: UpdateConsentsRequest, user: CurrentUser, store: StoreDep):
    """선택 동의(위치·카메라·사진 학습) 바꾸기 (API 43). 필수 동의는 탈퇴로만 철회한다."""
    changes = body.model_dump(exclude_none=True)
    if changes:
        user = store.update_consents(user.id, changes) or user
    return to_consents_response(user)
