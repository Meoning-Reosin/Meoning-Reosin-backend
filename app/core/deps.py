"""여러 기능이 함께 쓰는 로그인 확인 장치(의존성).

쓰는 법
    from app.core.deps import CurrentUser, OptionalUser

    @router.get("/bookmarks")
    def my_bookmarks(user: CurrentUser): ...       # 로그인 필수. 아니면 401 NOT_AUTHENTICATED

    @router.get("/places")
    def places(user: OptionalUser): ...            # 로그인 선택. 비회원이면 user는 None

토큰은 wcc_access 쿠키에서 먼저 찾고, 없으면 Authorization: Bearer 헤더에서 찾는다.
(헤더는 /docs에서 직접 시험하거나 나중에 앱을 만들 때 쓸 수 있게 열어 둔다.)
"""

from typing import Annotated

from fastapi import Cookie, Depends, Header

import app.auth.errors  # noqa: F401  NOT_AUTHENTICATED 오류 코드를 등록하기 위해 불러 둔다
from app.auth.repository import User, UserRepository, get_user_repository
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import ACCESS_COOKIE, TokenError, decode_token


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _user_from_token(settings: Settings, repo: UserRepository, token: str | None) -> User | None:
    """액세스 토큰을 확인해 회원을 찾는다. 토큰이 없거나 틀렸거나 탈퇴한 회원이면 None."""
    if not token:
        return None
    try:
        claims = decode_token(settings, token, "access")
        return repo.get(int(claims["sub"]))
    except (TokenError, ValueError):
        return None


def get_optional_user(
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[UserRepository, Depends(get_user_repository)],
    access_cookie: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """로그인이 "선택"인 API용. 예: 관광지 목록은 비회원도 보지만, 로그인했으면 찜 여부를 함께 보여준다."""
    return _user_from_token(settings, repo, access_cookie or _bearer_token(authorization))


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    """로그인이 "필수"인 API용. 로그인하지 않았으면 401."""
    if user is None:
        raise AppError("NOT_AUTHENTICATED")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
