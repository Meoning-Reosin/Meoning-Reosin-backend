"""회원 기능 오류 코드와 언어별 메시지.

응답 형식은 사진 인식과 같다: {"detail": {"code": "...", "message": "..."}}
"""

from typing import Annotated

from fastapi import Header, HTTPException, status

SUPPORTED_LANGUAGES = ("ko", "en")
DEFAULT_LANGUAGE = "ko"

_ERRORS = {
    "GOOGLE_NOT_CONFIGURED": (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        {"ko": "Google 로그인이 아직 설정되지 않았습니다.", "en": "Google sign-in is not configured yet."},
    ),
    "GOOGLE_LOGIN_CANCELLED": (
        status.HTTP_400_BAD_REQUEST,
        {"ko": "Google 로그인이 취소되었습니다.", "en": "Google sign-in was cancelled."},
    ),
    "INVALID_STATE": (
        status.HTTP_400_BAD_REQUEST,
        {
            "ko": "로그인 요청이 만료되었거나 올바르지 않습니다. 처음부터 다시 로그인해 주세요.",
            "en": "The sign-in request expired or is invalid. Please sign in again.",
        },
    ),
    "GOOGLE_AUTH_FAILED": (
        status.HTTP_502_BAD_GATEWAY,
        {"ko": "Google 계정 확인에 실패했습니다. 다시 시도해 주세요.", "en": "Could not verify your Google account. Please try again."},
    ),
    "GOOGLE_EMAIL_NOT_VERIFIED": (
        status.HTTP_403_FORBIDDEN,
        {"ko": "이메일 인증이 끝난 Google 계정만 사용할 수 있습니다.", "en": "Only Google accounts with a verified email can be used."},
    ),
    "SIGNUP_TOKEN_INVALID": (
        status.HTTP_401_UNAUTHORIZED,
        {"ko": "가입 시간이 지났습니다. Google 로그인부터 다시 해 주세요.", "en": "Sign-up expired. Please sign in with Google again."},
    ),
    "TERMS_REQUIRED": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {"ko": "이용약관과 개인정보 수집·이용에 동의해야 가입할 수 있습니다.", "en": "You must agree to the terms and privacy policy to sign up."},
    ),
    "NOT_AUTHENTICATED": (
        status.HTTP_401_UNAUTHORIZED,
        {"ko": "로그인이 필요합니다.", "en": "Please sign in."},
    ),
    "REFRESH_TOKEN_INVALID": (
        status.HTTP_401_UNAUTHORIZED,
        {"ko": "로그인이 만료되었습니다. 다시 로그인해 주세요.", "en": "Your session has expired. Please sign in again."},
    ),
}


def resolve_language(accept_language: str | None) -> str:
    """Accept-Language 헤더(예: "en-US,en;q=0.9")에서 지원하는 첫 언어를 고른다."""
    if accept_language:
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in SUPPORTED_LANGUAGES:
                return code
    return DEFAULT_LANGUAGE


def get_language(accept_language: Annotated[str | None, Header()] = None) -> str:
    return resolve_language(accept_language)


def auth_error(code: str, lang: str = DEFAULT_LANGUAGE) -> HTTPException:
    status_code, messages = _ERRORS[code]
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": messages.get(lang, messages[DEFAULT_LANGUAGE])},
        headers=headers,
    )
