"""관광지·카테고리·코스 API 주소 (router 층).

router가 하는 일은 두 가지뿐이다:
1. 요청에서 값을 꺼내고 모양을 검사한다 (Query의 ge/le, Literal 등).
2. service에게 일을 시키고 결과를 돌려준다.
service가 AppError를 던지면 app/core/errors.py가 {"detail": {"code", "message"}} 응답으로 바꿔 준다.

API 번호는 명세서의 API 목록 탭 번호다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import OptionalUser
from app.core.errors import get_language
from app.places import schemas
from app.places.bookmark_reader import BookmarkReader, get_bookmark_reader
from app.places.repository import PlaceRepository, get_place_repository
from app.places.service import PlaceService

places_router = APIRouter(prefix="/api/v1/places", tags=["관광지"])
categories_router = APIRouter(prefix="/api/v1/categories", tags=["관광지"])
courses_router = APIRouter(prefix="/api/v1/courses", tags=["코스"])


def get_place_service(
    repo: Annotated[PlaceRepository, Depends(get_place_repository)],
    bookmarks: Annotated[BookmarkReader, Depends(get_bookmark_reader)],
) -> PlaceService:
    return PlaceService(repo, bookmarks)


Service = Annotated[PlaceService, Depends(get_place_service)]
Lang = Annotated[str, Depends(get_language)]

# --- 11. 관광지 목록·검색 ---
@places_router.get("", response_model=schemas.PlaceListResponse)
def list_places(
    service: Service,
    lang: Lang,
    user: OptionalUser,
    q: Annotated[str | None, Query(max_length=50, description="장소 이름 검색어(한/영)")] = None,
    category_id: Annotated[int | None, Query(description="카테고리로 거르기")] = None,
    group: Annotated[schemas.Group | None, Query(description="큰 묶음으로 거르기")] = None,
    sort: Annotated[
        schemas.SortOrder | None,
        Query(description="distance / bookmarks / name. 안 보내면 위치가 있을 때 distance, 없으면 bookmarks"),
    ] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90, description="현재 위치 위도")] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180, description="현재 위치 경도")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return service.search_places(
        lang=lang,
        user_id=user.id if user else None,
        q=q.strip() if q and q.strip() else None,
        category_id=category_id,
        group=group,
        sort=sort,
        lat=lat,
        lng=lng,
        page=page,
        size=size,
    )


# --- 12. 장소 상세 ---
@places_router.get("/{place_id}", response_model=schemas.PlaceDetail)
def get_place(place_id: int, service: Service, lang: Lang, user: OptionalUser):
    return service.get_place_detail(place_id, lang=lang, user_id=user.id if user else None)


# --- 13. 운영 정보 ---
@places_router.get("/{place_id}/operating-info", response_model=schemas.OperatingInfoResponse)
def get_operating_info(place_id: int, service: Service, lang: Lang):
    return service.get_operating_info(place_id, lang=lang)


# --- 16. 해설 대본 ---
@places_router.get("/{place_id}/script", response_model=schemas.ScriptResponse)
def get_script(place_id: int, service: Service, lang: Lang):
    return service.get_script(place_id, lang=lang)


# --- 17. 카테고리 목록 ---
@categories_router.get("", response_model=schemas.CategoryListResponse)
def list_categories(
    service: Service,
    lang: Lang,
    group: Annotated[schemas.Group | None, Query(description="큰 묶음만 보기")] = None,
):
    return service.list_categories(lang=lang, group=group)


# --- 32. 추천 코스 목록 ---
@courses_router.get("", response_model=schemas.CourseListResponse)
def list_courses(
    service: Service,
    lang: Lang,
    category_id: Annotated[int | None, Query()] = None,
    group: Annotated[schemas.Group | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return service.list_courses(lang=lang, category_id=category_id, group=group, page=page, size=size)


# --- 33. 코스 상세 ---
@courses_router.get("/{course_id}", response_model=schemas.CourseDetail)
def get_course(course_id: int, service: Service, lang: Lang):
    return service.get_course_detail(course_id, lang=lang)
