"""사진 인식 오류 코드와 언어별 메시지.

응답 형식: {"detail": {"code": "IMAGE_TOO_LARGE", "message": "..."}}
프론트엔드는 code로 분기하고, message는 그대로 보여줘도 된다.
"""

from fastapi import HTTPException, status

from app.recognitions import config

SUPPORTED_LANGUAGES = ("ko", "en")
DEFAULT_LANGUAGE = "ko"

_ERRORS = {
    "EMPTY_FILE": (
        status.HTTP_400_BAD_REQUEST,
        {"ko": "빈 파일입니다.", "en": "The file is empty."},
    ),
    "IMAGE_TOO_LARGE": (
        status.HTTP_413_CONTENT_TOO_LARGE,
        {
            "ko": f"이미지 용량은 {config.MAX_IMAGE_MB}MB 이하여야 합니다.",
            "en": f"Image must be {config.MAX_IMAGE_MB}MB or smaller.",
        },
    ),
    "UNSUPPORTED_IMAGE_TYPE": (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        {
            "ko": "지원하지 않는 이미지 형식입니다. (jpeg, png, webp, heic)",
            "en": "Unsupported image type. (jpeg, png, webp, heic)",
        },
    ),
    "INVALID_LOCATION": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {
            "ko": "위치는 위도와 경도를 함께 보내야 합니다.",
            "en": "Latitude and longitude must be sent together.",
        },
    ),
}


def resolve_language(accept_language: str | None) -> str:
    """Accept-Language 헤더의 첫 번째 언어를 고른다. 지원하지 않으면 기본값(ko)."""
    if not accept_language:
        return DEFAULT_LANGUAGE
    first = accept_language.split(",")[0].strip().lower()
    lang = first.split("-")[0].split(";")[0]
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def recognition_error(code: str, lang: str) -> HTTPException:
    status_code, messages = _ERRORS[code]
    return HTTPException(status_code=status_code, detail={"code": code, "message": messages[lang]})
