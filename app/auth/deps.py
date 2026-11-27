"""로그인이 필요한 API에 붙이는 장치(의존성).

사용 예:
    @router.get("/something")
    def something(user: Annotated[User, Depends(get_current_user)]): ...

토큰은 sw_access 쿠키에서 먼저 찾고, 없으면 Authorization: Bearer 헤더에서 찾는다.
(헤더는 /docs에서 직접 시험하거나 나중에 앱을 만들 때 쓸 수 있게 열어 둔다.)
"""

from typing import Annotated

from fastapi import Cookie, Depends, Header

from app.auth.errors import auth_error, get_language
from app.auth.google import GoogleOAuthClient
from app.auth.store import User, UserStore, get_user_store
from app.core.config import Settings, get_settings
from app.core.security import ACCESS_COOKIE, TokenError, decode_token


def get_google_client(settings: Annotated[Settings, Depends(get_settings)]) -> GoogleOAuthClient:
    return GoogleOAuthClient(settings)


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[UserStore, Depends(get_user_store)],
    lang: Annotated[str, Depends(get_language)],
    access_cookie: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = access_cookie or _bearer_token(authorization)
    try:
        claims = decode_token(settings, token, "access")
        user_id = int(claims["sub"])
    except (TokenError, ValueError):
        raise auth_error("NOT_AUTHENTICATED", lang)
    user = store.get(user_id)
    if user is None:
        raise auth_error("NOT_AUTHENTICATED", lang)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
