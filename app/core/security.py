"""JWT 토큰 만들기·확인과 로그인 쿠키 다루기.

토큰 종류(type 클레임)
- access:  API를 부를 때 쓰는 토큰 (1시간)
- refresh: access가 만료됐을 때 새로 받을 때만 쓰는 토큰 (14일, 서버에 기록해 두고 로그아웃 때 폐기)
- signup:  처음 로그인한 사람이 약관 동의를 마칠 때까지 쓰는 토큰 (10분, Google 정보가 들어 있음)
- oauth_state: Google 로그인 시작~콜백 사이의 위조 방지 값 (10분)

토큰은 HttpOnly 쿠키에 담는다. 브라우저 자바스크립트가 읽을 수 없어 토큰을 훔치기 어렵다.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Response

from app.core.config import Settings

logger = logging.getLogger(__name__)

# 쿠키 이름 앞의 wcc_는 서비스 이름 워크크(Walk Creator Crew)의 약자. 같은 주소(127.0.0.1)에서 도는
# 다른 앱의 쿠키와 이름이 겹치지 않게 붙인다. 프론트 코드는 HttpOnly라 이 쿠키를 읽을 수 없고, 읽을 필요도 없다.
ACCESS_COOKIE = "wcc_access"
REFRESH_COOKIE = "wcc_refresh"
SIGNUP_COOKIE = "wcc_signup"
STATE_COOKIE = "wcc_oauth_state"

# 쿠키를 보낼 주소 범위. refresh·signup은 인증 API에만 보내 노출을 줄인다.
ACCESS_COOKIE_PATH = "/"
AUTH_COOKIE_PATH = "/api/v1/auth"
STATE_COOKIE_PATH = "/api/v1/auth/oauth/google"

_fallback_secret: str | None = None


class TokenError(Exception):
    """토큰이 없거나, 위조됐거나, 만료됐거나, 종류가 다를 때."""


def _secret(settings: Settings) -> str:
    global _fallback_secret
    if settings.jwt_secret:
        return settings.jwt_secret
    if _fallback_secret is None:
        _fallback_secret = secrets.token_urlsafe(48)
        logger.warning("JWT_SECRET이 비어 있어 임시 비밀키를 만들었습니다. 서버를 다시 켜면 로그인이 풀립니다.")
    return _fallback_secret


def create_token(
    settings: Settings,
    token_type: str,
    subject: str,
    expires_in: timedelta,
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """토큰 문자열과 그 안에 담긴 값(claims)을 함께 돌려준다."""
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,  # 누구의 토큰인지 (회원 번호, 가입 토큰은 Google sub)
        "type": token_type,  # 토큰 종류. 다른 용도의 토큰을 섞어 쓰지 못하게 확인한다.
        "iat": now,  # 발급 시각
        "exp": now + expires_in,  # 만료 시각. 지나면 decode가 실패한다.
        "jti": uuid.uuid4().hex,  # 토큰 고유번호. 리프레시 토큰 폐기(로그아웃)에 쓴다.
        **(extra or {}),
    }
    # 비밀키로 서명한다. 내용은 누구나 볼 수 있지만(암호화 아님), 고치면 서명이 맞지 않아 거부된다.
    token = jwt.encode(claims, _secret(settings), algorithm=settings.jwt_algorithm)
    return token, claims


def decode_token(settings: Settings, token: str | None, expected_type: str) -> dict[str, Any]:
    if not token:
        raise TokenError("missing")
    try:
        claims = jwt.decode(
            token,
            _secret(settings),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("type") != expected_type:
        raise TokenError("wrong type")
    return claims


def _set_cookie(response: Response, settings: Settings, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,  # 초 단위. 지나면 브라우저가 쿠키를 지운다(토큰 만료 시간과 같게 둔다).
        path=path,  # 이 주소로 시작하는 요청에만 쿠키를 보낸다.
        httponly=True,  # 자바스크립트(document.cookie)로 읽을 수 없게 한다 → 토큰 도난 방지.
        secure=settings.cookie_secure,  # True면 HTTPS에서만 보낸다. 로컬(http)에서는 False.
        samesite="lax",  # 다른 사이트에서 몰래 보내는 POST 요청에는 쿠키를 붙이지 않는다(CSRF 방지).
    )


def _delete_cookie(response: Response, settings: Settings, name: str, path: str) -> None:
    response.delete_cookie(name, path=path, httponly=True, secure=settings.cookie_secure, samesite="lax")


def set_access_cookie(response: Response, settings: Settings, token: str) -> None:
    _set_cookie(response, settings, ACCESS_COOKIE, token, settings.access_token_minutes * 60, ACCESS_COOKIE_PATH)


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    _set_cookie(response, settings, REFRESH_COOKIE, token, settings.refresh_token_days * 86400, AUTH_COOKIE_PATH)


def set_signup_cookie(response: Response, settings: Settings, token: str) -> None:
    _set_cookie(response, settings, SIGNUP_COOKIE, token, settings.signup_token_minutes * 60, AUTH_COOKIE_PATH)


def set_state_cookie(response: Response, settings: Settings, token: str) -> None:
    _set_cookie(response, settings, STATE_COOKIE, token, 600, STATE_COOKIE_PATH)


def clear_signup_cookie(response: Response, settings: Settings) -> None:
    _delete_cookie(response, settings, SIGNUP_COOKIE, AUTH_COOKIE_PATH)


def clear_state_cookie(response: Response, settings: Settings) -> None:
    _delete_cookie(response, settings, STATE_COOKIE, STATE_COOKIE_PATH)


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    _delete_cookie(response, settings, ACCESS_COOKIE, ACCESS_COOKIE_PATH)
    _delete_cookie(response, settings, REFRESH_COOKIE, AUTH_COOKIE_PATH)
    clear_signup_cookie(response, settings)
