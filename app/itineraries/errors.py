"""여행 일정 오류 코드와 언어별 메시지.

쓰는 법: raise AppError("코드"). 응답 모양과 언어 고르기는 app/core/errors.py가 맡는다.
PLACE_NOT_FOUND, COURSE_NOT_FOUND는 관광지 기능(app/places/errors.py)에 이미 있어서 그대로 쓴다.
"""

from fastapi import status

from app.core.errors import register_errors

_ERRORS = {
    "ITINERARY_NOT_FOUND": (
        status.HTTP_404_NOT_FOUND,
        {"ko": "없는 여행 일정입니다.", "en": "Itinerary not found."},
    ),
    "FORBIDDEN": (
        status.HTTP_403_FORBIDDEN,
        {"ko": "이 여행 일정에 접근할 수 없습니다.", "en": "You cannot access this itinerary."},
    ),
    "ITEM_NOT_FOUND": (
        status.HTTP_404_NOT_FOUND,
        {"ko": "일정에 없는 항목입니다.", "en": "Item not found in this itinerary."},
    ),
    "PLACE_ALREADY_IN_ITINERARY": (
        status.HTTP_409_CONFLICT,
        {"ko": "이미 이 일정에 담긴 장소입니다.", "en": "This place is already in the itinerary."},
    ),
}

register_errors(_ERRORS)
