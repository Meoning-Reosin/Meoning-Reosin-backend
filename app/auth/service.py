"""회원 기능의 업무 규칙 (service 층).

여기서 하는 일: 로그인 시작 값(state, nonce) 만들기, Google 결과 확인, 가입 조건 확인,
닉네임 정하기, 토큰 발급·교체·폐기, 내 정보·동의 바꾸기, 탈퇴.

이 층의 규칙:
- 쿠키, 리디렉션 같은 HTTP 일은 모른다. 토큰 "값"만 만들어 돌려주고, 쿠키에 담는 일은 router가 한다.
- 데이터를 어디에 저장하는지 모른다. UserRepository에게 맡긴다.
- 문제가 생기면 AppError(code)를 던진다.
"""

import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.auth import errors as _errors  # noqa: F401  오류 코드 등록
from app.auth.google import GoogleAuthError, GoogleEmailNotVerified, GoogleOAuthClient, GoogleProfile
from app.auth.repository import CONSENT_TYPES, User, UserRepository
from app.auth.schemas import ConsentsResponse, SignupRequest, UserResponse
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import TokenError, create_token, decode_token


@dataclass
class LoginTokens:
    access: str
    refresh: str


@dataclass
class CallbackResult:
    """Google 콜백 결과. user가 있으면 기존 회원(바로 로그인), 없으면 신규(가입 필요)."""

    profile: GoogleProfile
    user: User | None
    tokens: LoginTokens | None  # 기존 회원일 때만
    signup_token: str | None  # 신규 회원일 때만


class AuthService:
    def __init__(self, settings: Settings, repo: UserRepository) -> None:
        self.settings = settings
        self.repo = repo

    # ------------------------------------------------------------------ Google 로그인
    def start_google_login(self, google: GoogleOAuthClient) -> tuple[str, str]:
        """(Google 로그인 주소, state 쿠키에 담을 서명된 토큰)을 돌려준다 (API 5-1).

        state: 위조 요청을 막는 값. 콜백에서 Google이 돌려준 값과 쿠키 속 값이 같아야 한다.
        nonce: ID 토큰을 재사용하지 못하게 하는 값. Google이 ID 토큰 안에 그대로 넣어 준다.
        """
        if not self.settings.google_configured:
            raise AppError("GOOGLE_NOT_CONFIGURED")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        state_token, _ = create_token(
            self.settings, "oauth_state", "google", timedelta(minutes=10), extra={"state": state, "nonce": nonce}
        )
        return google.build_authorization_url(state, nonce), state_token

    async def finish_google_login(
        self, google: GoogleOAuthClient, *, code: str | None, state: str | None, state_cookie: str | None
    ) -> CallbackResult:
        """Google 콜백 처리 (API 5-2): state 확인 → 코드 교환 → ID 토큰 검증 → 회원 찾기."""
        # 1) start에서 쿠키에 넣어 둔 state와 Google이 돌려준 state가 같은지 확인한다.
        #    compare_digest는 비교 시간으로 값을 추측하지 못하게 하는 안전한 비교 함수다.
        try:
            saved = decode_token(self.settings, state_cookie, "oauth_state")
        except TokenError:
            raise AppError("INVALID_STATE")
        if not code or not state or not secrets.compare_digest(state, saved["state"]):
            raise AppError("INVALID_STATE")

        # 2) code → ID 토큰 교환, ID 토큰 검증 (Google과 통신)
        try:
            id_token = await google.exchange_code(code)
            profile = await google.verify_id_token(id_token, saved["nonce"])
        except GoogleEmailNotVerified:
            raise AppError("GOOGLE_EMAIL_NOT_VERIFIED")
        except GoogleAuthError:
            raise AppError("GOOGLE_AUTH_FAILED")

        # 3) Google 계정 고유번호(sub)로 가입한 적이 있는지 찾는다. 이메일은 바뀔 수 있어서 쓰지 않는다.
        user = self.repo.get_by_provider("google", profile.sub)
        if user:
            return CallbackResult(profile=profile, user=user, tokens=self.issue_tokens(user), signup_token=None)

        # 4) 신규 회원: 10분짜리 가입 토큰(Google 이메일·이름 포함)을 만든다.
        #    아직 회원이 아니므로 다른 API는 쓸 수 없고, 가입 마치기(signup)에만 쓴다.
        signup_token, _ = create_token(
            self.settings,
            "signup",
            profile.sub,
            timedelta(minutes=self.settings.signup_token_minutes),
            extra={"email": profile.email, "name": profile.name, "picture": profile.picture},
        )
        return CallbackResult(profile=profile, user=None, tokens=None, signup_token=signup_token)

    def signup(self, body: SignupRequest, signup_cookie: str | None) -> tuple[User, LoginTokens]:
        """약관 동의 후 가입을 마친다 (API 6)."""
        try:
            claims = decode_token(self.settings, signup_cookie, "signup")
        except TokenError:
            raise AppError("SIGNUP_TOKEN_INVALID")
        if not (body.agree_terms and body.agree_privacy):
            raise AppError("TERMS_REQUIRED")

        user = self.repo.create(
            provider="google",
            provider_user_id=claims["sub"],
            email=claims["email"],
            nickname=_choose_nickname(body.nickname, claims),
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
        return user, self.issue_tokens(user)

    # ------------------------------------------------------------------ 토큰
    def issue_tokens(self, user: User) -> LoginTokens:
        """액세스·리프레시 토큰을 만들고, 리프레시 토큰 번호(jti)를 저장해 둔다(나중에 폐기할 수 있게)."""
        s = self.settings
        access, _ = create_token(s, "access", str(user.id), timedelta(minutes=s.access_token_minutes))
        refresh, claims = create_token(s, "refresh", str(user.id), timedelta(days=s.refresh_token_days))
        self.repo.save_refresh_token(claims["jti"], user.id, claims["exp"])
        return LoginTokens(access=access, refresh=refresh)

    def refresh(self, refresh_cookie: str | None) -> LoginTokens:
        """리프레시 토큰으로 새 토큰을 받는다 (API 7).

        쓴 리프레시 토큰은 폐기하고 새 리프레시 토큰도 함께 준다(도난 피해를 줄이기 위해).
        """
        try:
            claims = decode_token(self.settings, refresh_cookie, "refresh")
            user_id = int(claims["sub"])
        except (TokenError, ValueError):
            raise AppError("REFRESH_TOKEN_INVALID")
        user = self.repo.get(user_id)
        if user is None or not self.repo.is_refresh_token_active(claims["jti"], user_id):
            raise AppError("REFRESH_TOKEN_INVALID")
        self.repo.revoke_refresh_token(claims["jti"])
        return self.issue_tokens(user)

    def logout(self, refresh_cookie: str | None) -> None:
        """리프레시 토큰을 폐기한다 (API 8). 토큰이 없거나 틀려도 조용히 끝낸다."""
        try:
            claims = decode_token(self.settings, refresh_cookie, "refresh")
        except TokenError:
            return
        self.repo.revoke_refresh_token(claims["jti"])

    # ------------------------------------------------------------------ 내 정보
    def update_me(self, user: User, changes: dict) -> User:
        """닉네임·언어 고치기 (API 10). 보낸 값만 바뀐다."""
        if not changes:
            return user
        return self.repo.update(user.id, **changes) or user

    def update_consents(self, user: User, changes: dict[str, bool]) -> User:
        """선택 동의 바꾸기 (API 43)."""
        if not changes:
            return user
        return self.repo.update_consents(user.id, changes) or user

    def delete_account(self, user: User) -> None:
        """회원 탈퇴 (API 40). 회원 정보와 토큰을 바로 지운다.

        TODO: 일정·찜·공개 코스가 생기면 여기서 함께 지운다 (Q-33).
        """
        self.repo.delete(user.id)


def _choose_nickname(requested: str | None, claims: dict) -> str:
    """닉네임: 보낸 값 → 없으면 Google 이름(최대 20자) → 그것도 2자 미만이면 이메일 앞부분 (Q-35)."""
    nickname = requested or (claims.get("name") or "")[:20]
    if len(nickname) < 2:
        nickname = (claims.get("email") or "user").split("@")[0][:20].ljust(2, "_")
    return nickname


# ---------------------------------------------------------------------- 응답 모양으로 바꾸기
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
