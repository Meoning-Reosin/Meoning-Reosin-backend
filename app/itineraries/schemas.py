"""여행 일정 API의 요청·응답 모양 (명세서 23~31번).

고치기(PATCH) 요청은 "보낸 값만 바뀐다". 그래서 값을 안 보낸 것과 null을 보낸 것을 구분한다.
예: {"memo": null}은 메모 지우기, {}는 아무것도 안 바꾸기.
service는 model_fields_set(실제로 보낸 칸 이름들)을 보고 판단한다.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Role = Literal["owner", "member"]  # 만든 사람 / 참여자 (참여자는 초대 기능 ITN-11에서)

TITLE = Field(min_length=1, max_length=50, description="일정 이름 (1~50자)")
MEMO = Field(None, max_length=200, description="메모 (200자까지). 안 보내도 됨")


# ---------------------------------------------------------------- 요청


class ItineraryCreateRequest(BaseModel):
    title: str = TITLE
    travel_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value):
        """앞뒤 띄어쓰기를 지운다. "  " 처럼 띄어쓰기만 보내면 빈 글자가 되어 1자 미만 오류가 난다."""
        return value.strip() if isinstance(value, str) else value


class ItineraryUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=50)
    travel_date: date | None = None  # null을 보내면 날짜를 지움

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value):
        """앞뒤 띄어쓰기를 지운다. "  " 처럼 띄어쓰기만 보내면 빈 글자가 되어 1자 미만 오류가 난다."""
        return value.strip() if isinstance(value, str) else value


class AddPlaceRequest(BaseModel):
    """28. 장소를 일정에 담기"""

    itinerary_id: int = Field(description="담을 일정. 일정이 없으면 먼저 24번으로 만든 뒤 그 ID를 보냄")
    place_id: int
    memo: str | None = MEMO


class ItemUpdateRequest(BaseModel):
    """29. 일정 항목 고치기. 보낸 값만 바뀜"""

    visit_order: int | None = Field(None, ge=1, description="새 방문 순서(1부터). 마지막보다 크면 맨 뒤로")
    memo: str | None = MEMO
    visited: bool | None = Field(None, description="true면 방문 완료, false면 취소")


class AddCourseRequest(BaseModel):
    """31. 코스를 일정에 담기"""

    course_id: int
    itinerary_id: int | None = Field(None, description="담을 일정. 안 보내면 코스 이름으로 새 일정을 만들어 담음")


# ---------------------------------------------------------------- 응답


class ItinerarySummary(BaseModel):
    """23. 목록의 한 줄"""

    itinerary_id: int
    title: str
    travel_date: date | None
    item_count: int
    my_role: Role
    is_public: bool
    updated_at: datetime
    contains_place: bool | None  # place_id를 보냈을 때만 true/false, 안 보냈으면 null


class ItineraryListResponse(BaseModel):
    items: list[ItinerarySummary]
    page: int
    size: int
    total: int


class ItemPlace(BaseModel):
    place_id: int
    name: str
    name_en: str
    thumbnail_url: str | None
    lat: float
    lng: float
    distance_m: int | None  # 현재 위치(lat, lng)를 보냈을 때 거기서부터의 직선거리
    expected_visit_minutes: int


class ItineraryItemResponse(BaseModel):
    item_id: int
    visit_order: int  # 1부터
    memo: str | None
    visited: bool
    visited_at: datetime | None
    distance_m_from_previous: int | None  # 앞 장소에서의 직선거리. 첫 장소는 null
    walk_minutes_from_previous: int | None  # 앞 장소에서 걸어오는 시간(어림값). 첫 장소는 null
    place: ItemPlace


class ItineraryDetail(BaseModel):
    """25. 여행 일정 보기 (24, 26, 29번도 같은 모양)"""

    itinerary_id: int
    title: str
    travel_date: date | None
    my_role: Role
    is_public: bool
    member_count: int  # 함께하는 사람 수 (초대 기능 전까지는 1)
    item_count: int
    visited_count: int
    total_visit_minutes: int  # 관람 시간 합계
    total_walk_minutes: int  # 장소 사이 도보 시간 합계 (ITN-08)
    total_minutes: int  # 관람 + 도보
    created_at: datetime
    updated_at: datetime
    items: list[ItineraryItemResponse]


class AddPlaceResponse(BaseModel):
    """28번 응답"""

    itinerary_id: int
    item_id: int
    visit_order: int


class AddCourseResponse(BaseModel):
    """31번 응답"""

    itinerary_id: int
    added_count: int
    skipped_count: int  # 이미 담겨 있어서 건너뛴 장소 수
