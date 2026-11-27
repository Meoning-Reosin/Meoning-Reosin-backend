"""관광지·카테고리·코스 API의 응답 모양.

필드 이름과 뜻은 API 명세서(응답 필드 탭)의 11, 12, 13, 16, 17, 32, 33번과 같다.
name, area, summary처럼 언어가 있는 값은 Accept-Language로 고른 언어로 채우고,
name_en처럼 _en이 붙은 값은 언제나 영어다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Group = Literal["history", "sns", "content", "festival"]
SortOrder = Literal["distance", "bookmarks", "name"]


class CategoryBrief(BaseModel):
    category_id: int
    name: str


# --- 11. 관광지 목록·검색 ---
class PlaceCard(BaseModel):
    place_id: int
    name: str
    name_en: str
    area: str
    thumbnail_url: str | None  # 사진이 오기 전까지 null
    address: str
    lat: float
    lng: float
    distance_m: int | None  # 위치를 안 보내면 null
    walk_minutes: int | None
    bookmark_count: int
    is_bookmarked: bool  # 비회원이면 false
    expected_visit_minutes: int
    categories: list[CategoryBrief]


class PlaceListResponse(BaseModel):
    items: list[PlaceCard]
    sort: SortOrder
    page: int
    size: int
    total: int


# --- 12. 장소 상세 ---
class PlaceImage(BaseModel):
    image_id: int
    url: str
    author: str | None
    license: str | None
    license_url: str | None
    source: str | None


class Introduction(BaseModel):
    summary: str  # 고른 언어
    summary_en: str
    highlights: list[str]  # 관람 포인트 (고른 언어)


class Audio(BaseModel):
    url: str
    duration_seconds: int | None
    source: str  # odii


class PlaceDetail(BaseModel):
    place_id: int
    name: str
    name_en: str
    area: str
    address: str
    lat: float
    lng: float
    images: list[PlaceImage]
    categories: list[CategoryBrief]
    introduction: Introduction
    audio: Audio | None  # 음성이 없으면 null
    is_bookmarked: bool
    bookmark_count: int


# --- 13. 운영 정보 ---
class OperatingInfoResponse(BaseModel):
    opening_hours: str
    last_admission: str | None
    closed_days: str
    admission_fee: str
    reservation: str
    expected_visit_minutes: int
    is_open_now: bool
    source: str | None
    source_url: str | None
    updated_at: datetime | None  # TourAPI에서 가져온 시각. 임시 데이터는 null


# --- 16. 해설 대본 ---
class ScriptResponse(BaseModel):
    script_id: int
    language: str
    content: str
    source: str  # odii
    audio_url: str | None
    duration_seconds: int | None


# --- 17. 카테고리 목록 ---
class CategoryItem(BaseModel):
    category_id: int
    name: str
    name_en: str
    description: str
    group: Group


class CategoryListResponse(BaseModel):
    items: list[CategoryItem]


# --- 32. 추천 코스 목록 ---
class CourseCard(BaseModel):
    course_id: int
    title: str
    title_en: str
    subtitle: str
    group: Group
    thumbnail_url: str | None
    place_count: int
    total_minutes: int  # 관람 + 도보 (어림값)


class CourseListResponse(BaseModel):
    items: list[CourseCard]
    page: int
    size: int
    total: int


# --- 33. 코스 상세 ---
class CoursePlace(BaseModel):
    order: int  # 1부터
    place_id: int
    name: str
    name_en: str
    thumbnail_url: str | None
    expected_visit_minutes: int
    walk_minutes_from_previous: int | None  # 앞 장소에서 걸어오는 시간. 첫 장소는 null


class CourseDetail(BaseModel):
    course_id: int
    title: str
    title_en: str
    subtitle: str
    description: str
    places: list[CoursePlace]
    total_minutes: int
