"""Google 로그인 (OAuth 2.0 인가 코드 방식, 서버 리디렉션).

1. build_authorization_url: Google 로그인 화면 주소를 만든다.
2. exchange_code: 콜백으로 받은 code를 Client Secret과 함께 보내 ID 토큰으로 바꾼다.
3. verify_id_token: ID 토큰의 서명(Google 공개키), 발급자, 대상(우리 Client ID), 만료, nonce를 확인한다.

회원은 이메일이 아니라 Google 계정 고유번호(sub)로 구분한다. 이메일은 바뀔 수 있기 때문이다.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SCOPES = "openid email profile"


class GoogleAuthError(Exception):
    """Google과 통신하거나 ID 토큰을 확인하다 실패했을 때."""


class GoogleEmailNotVerified(GoogleAuthError):
    pass


@dataclass
class GoogleProfile:
    sub: str
    email: str
    name: str
    picture: str | None


class GoogleOAuthClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_authorization_url(self, state: str, nonce: str) -> str:
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "prompt": "select_account",
        }
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> str:
        """code를 ID 토큰(문자열)으로 바꾼다."""
        data = {
            "code": code,
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "redirect_uri": self.settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(TOKEN_ENDPOINT, data=data)
        except httpx.HTTPError as exc:
            raise GoogleAuthError(f"token request failed: {exc}") from exc
        if response.status_code != 200:
            raise GoogleAuthError(f"token endpoint returned {response.status_code}")
        id_token = response.json().get("id_token")
        if not id_token:
            raise GoogleAuthError("no id_token in response")
        return id_token

    async def verify_id_token(self, id_token: str, nonce: str) -> GoogleProfile:
        try:
            signing_key = await run_in_threadpool(_jwks_client().get_signing_key_from_jwt, id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.settings.google_client_id,
                issuer=ISSUERS,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise GoogleAuthError(f"invalid id_token: {exc}") from exc
        if claims.get("nonce") != nonce:
            raise GoogleAuthError("nonce mismatch")
        if not claims.get("email") or claims.get("email_verified") is not True:
            raise GoogleEmailNotVerified("email not verified")
        return GoogleProfile(
            sub=claims["sub"],
            email=claims["email"],
            name=claims.get("name") or claims["email"].split("@")[0],
            picture=claims.get("picture"),
        )


_jwks: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    """Google 공개키 목록. 한 번 받아 두고 재사용한다."""
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(JWKS_URI, cache_keys=True, timeout=10)
    return _jwks
