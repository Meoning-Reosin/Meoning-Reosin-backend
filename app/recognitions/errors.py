"""사진 인식 오류 코드와 언어별 메시지.

쓰는 법: raise AppError("코드"). 응답 모양과 언어 고르기는 app/core/errors.py가 맡는다.
"""

from fastapi import status

from app.core.errors import register_errors
from app.recognitions import config

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
}

register_errors(_ERRORS)
