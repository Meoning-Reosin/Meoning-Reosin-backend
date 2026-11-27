"""관광지·코스 오류 코드와 언어별 메시지.

쓰는 법: raise AppError("코드"). 응답 모양과 언어 고르기는 app/core/errors.py가 맡는다.
"""

from fastapi import status

from app.core.errors import register_errors

_ERRORS = {
    "PLACE_NOT_FOUND": (
        status.HTTP_404_NOT_FOUND,
        {"ko": "없는 장소입니다.", "en": "Place not found."},
    ),
    "SCRIPT_NOT_FOUND": (
        status.HTTP_404_NOT_FOUND,
        {"ko": "이 언어로 된 해설이 아직 없습니다.", "en": "No narration is available in this language yet."},
    ),
    "COURSE_NOT_FOUND": (
        status.HTTP_404_NOT_FOUND,
        {"ko": "없는 코스입니다.", "en": "Course not found."},
    ),
    "LOCATION_REQUIRED": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {"ko": "가까운 순으로 보려면 현재 위치(lat, lng)가 필요합니다.", "en": "Sorting by distance needs your location (lat, lng)."},
    ),
}

register_errors(_ERRORS)
