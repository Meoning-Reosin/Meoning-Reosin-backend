"""회원 기능 오류 코드와 언어별 메시지.

쓰는 법: raise AppError("코드"). 응답 모양과 언어 고르기는 app/core/errors.py가 맡는다.
"""

from fastapi import status

from app.core.errors import register_errors

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

register_errors(_ERRORS)
