"""회원 API 주소 (router 층): Google 로그인, 가입 마치기, 토큰 다시 받기, 로그아웃, 내 정보, 탈퇴.

흐름
1. 프론트가 브라우저를 GET /api/v1/auth/oauth/google/start 로 보낸다.
2. Google 로그인 후 Google이 GET /api/v1/auth/oauth/google/callback 으로 돌려보낸다.
3. 이미 가입한 사람: 로그인 쿠키를 받고 프론트로 이동.
   처음인 사람: 가입용 쿠키를 받고 약관 동의 화면으로 이동 → POST /api/v1/auth/oauth/signup.
프론트 주소(FRONTEND_URL)가 비어 있으면 콜백은 결과를 JSON으로 보여준다(프론트 없이 확인하는 개발용).

router가 하는 일: 요청에서 값 꺼내기 → service에게 시키기 → 결과를 쿠키·리디렉션·JSON으로 돌려주기.
판단(가입 조건, 토큰 검사 등)은 service.py에 있다.
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.google import GoogleOAuthClient, get_google_client
from app.auth.repository import UserRepository, get_user_repository
from app.auth.schemas import (
    ConsentsResponse,
    GoogleCallbackResponse,
    RefreshResponse,
    SignupRequest,
    UpdateConsentsRequest,
    UpdateMeRequest,
    UserResponse,
)
from app.auth.service import AuthService, LoginTokens, to_consents_response, to_user_response
from app.core.config import Settings, get_settings
from app.core.deps import CurrentUser
from app.core.errors import AppError, error_response, get_language
from app.core.security import (
    REFRESH_COOKIE,
    SIGNUP_COOKIE,
    STATE_COOKIE,
    clear_auth_cookies,
    clear_signup_cookie,
    clear_state_cookie,
    set_access_cookie,
    set_refresh_cookie,
    set_signup_cookie,
    set_state_cookie,
)

# 주소 묶음 두 개. main.py에서 app.include_router()로 등록한다.
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])  # 로그인·토큰
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])  # 내 정보


def get_auth_service(
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(settings, repo)


# 자주 쓰는 의존성을 짧은 이름으로 묶어 둔다.
# FastAPI가 요청마다 get_settings() 등을 불러 함수 인자로 넣어 준다(테스트에서는 가짜로 바꿔 끼울 수 있다).
SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceDep = Annotated[AuthService, Depends(get_auth_service)]
GoogleDep = Annotated[GoogleOAuthClient, Depends(get_google_client)]


def _set_login_cookies(response: Response, settings: Settings, tokens: LoginTokens) -> None:
    set_access_cookie(response, settings, tokens.access)
    set_refresh_cookie(response, settings, tokens.refresh)


def _with_query(url: str, **params: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"


# ---------------------------------------------------------------- Google 로그인


@router.get("/oauth/google/start", status_code=status.HTTP_302_FOUND, response_class=RedirectResponse)
def google_start(settings: SettingsDep, service: ServiceDep, google: GoogleDep):
    """Google 로그인 화면으로 보낸다 (API 5-1). state·nonce는 서명된 쿠키에 담아 둔다."""
    url, state_token = service.start_google_login(google)
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    set_state_cookie(response, settings, state_token)
    return response


@router.get(
    "/oauth/google/callback",
    response_model=GoogleCallbackResponse,
    responses={302: {"description": "프론트 주소가 설정돼 있으면 프론트로 이동"}},
)
async def google_callback(
    settings: SettingsDep,
    service: ServiceDep,
    google: GoogleDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    state_cookie: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
):
    """Google이 로그인 후 돌려보내는 주소 (API 5-2). 프론트가 직접 부르지 않는다."""
    # 사용자가 Google 화면에서 취소하면 code 대신 error=access_denied 가 온다.
    if error:
        if settings.frontend_url:
            response = RedirectResponse(_with_query(settings.frontend_url, login_error=error), status.HTTP_302_FOUND)
            clear_state_cookie(response, settings)
            return response
        raise AppError("GOOGLE_LOGIN_CANCELLED")

    result = await service.finish_google_login(google, code=code, state=state, state_cookie=state_cookie)

    if result.user:
        body = GoogleCallbackResponse(
            status="logged_in", email=result.user.email, name=result.user.nickname, user=to_user_response(result.user)
        )
        target = settings.frontend_url
    else:
        body = GoogleCallbackResponse(status="signup_required", email=result.profile.email, name=result.profile.name)
        target = settings.frontend_signup_url or settings.frontend_url

    # 프론트 주소가 있으면 그리로 이동, 없으면(개발 중) 결과를 JSON으로 보여준다.
    response: Response
    if target:
        response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    else:
        response = JSONResponse(body.model_dump(mode="json"))

    # 쿠키 담기: 기존 회원은 로그인 토큰, 신규 회원은 가입 토큰
    if result.tokens:
        _set_login_cookies(response, settings, result.tokens)
        clear_signup_cookie(response, settings)
    else:
        set_signup_cookie(response, settings, result.signup_token)
    clear_state_cookie(response, settings)
    return response


@router.post("/oauth/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    response: Response,
    settings: SettingsDep,
    service: ServiceDep,
    signup_cookie: Annotated[str | None, Cookie(alias=SIGNUP_COOKIE)] = None,
):
    """처음 로그인한 사람이 약관에 동의하고 가입을 마친다 (API 6)."""
    user, tokens = service.signup(body, signup_cookie)
    _set_login_cookies(response, settings, tokens)
    clear_signup_cookie(response, settings)
    return to_user_response(user)


# ---------------------------------------------------------------- 토큰


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    settings: SettingsDep,
    service: ServiceDep,
    lang: Annotated[str, Depends(get_language)],
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    """액세스 토큰이 만료됐을 때 새 토큰을 받는다 (API 7)."""
    try:
        tokens = service.refresh(refresh_cookie)
    except AppError as error:
        # 쓸 수 없는 리프레시 토큰이면 남은 로그인 쿠키도 지워서, 프론트가 로그인 화면으로 가게 한다.
        response = error_response(error, lang)
        clear_auth_cookies(response, settings)
        return response
    body = RefreshResponse(expires_in=settings.access_token_minutes * 60)
    response = JSONResponse(body.model_dump())
    _set_login_cookies(response, settings, tokens)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    settings: SettingsDep,
    service: ServiceDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    """로그아웃 (API 8). 이미 로그아웃됐거나 토큰이 만료된 상태에서 불러도 204로 끝난다."""
    service.logout(refresh_cookie)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


# ---------------------------------------------------------------- 내 정보


@users_router.get("/me", response_model=UserResponse)
def read_me(user: CurrentUser):
    """내 정보 보기 (API 9)."""
    return to_user_response(user)


@users_router.patch("/me", response_model=UserResponse)
def update_me(body: UpdateMeRequest, user: CurrentUser, service: ServiceDep):
    """닉네임·언어 고치기 (API 10). 보낸 값만 바뀐다."""
    return to_user_response(service.update_me(user, body.model_dump(exclude_none=True)))


@users_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: CurrentUser, settings: SettingsDep, service: ServiceDep):
    """회원 탈퇴 (API 40). 회원 정보와 토큰을 바로 지우고 로그인 쿠키를 지운다."""
    service.delete_account(user)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


@users_router.get("/me/consents", response_model=ConsentsResponse)
def read_consents(user: CurrentUser):
    """내 동의 상태 보기 (설정 화면용)."""
    return to_consents_response(user)


@users_router.patch("/me/consents", response_model=ConsentsResponse)
def update_consents(body: UpdateConsentsRequest, user: CurrentUser, service: ServiceDep):
    """선택 동의(위치·카메라·사진 학습) 바꾸기 (API 43). 필수 동의는 탈퇴로만 철회한다."""
    return to_consents_response(service.update_consents(user, body.model_dump(exclude_none=True)))
