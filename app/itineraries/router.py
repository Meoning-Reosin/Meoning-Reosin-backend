"""여행 일정 API 주소 (router 층). 모두 로그인 필수 (CurrentUser).

23. GET    /api/v1/itineraries                               내 일정 목록 (?place_id= 로 "이미 담김" 표시)
24. POST   /api/v1/itineraries                               일정 만들기
25. GET    /api/v1/itineraries/{itinerary_id}                일정 보기 (?lat=&lng= 로 현재 위치에서 거리)
26. PATCH  /api/v1/itineraries/{itinerary_id}                이름·날짜 고치기
27. DELETE /api/v1/itineraries/{itinerary_id}                일정 지우기
28. POST   /api/v1/itineraries/items                         장소를 일정에 담기
29. PATCH  /api/v1/itineraries/{itinerary_id}/items/{item_id} 순서·메모·방문 체크
30. DELETE /api/v1/itineraries/{itinerary_id}/items/{item_id} 일정에서 장소 빼기
31. POST   /api/v1/itineraries/courses                       코스를 일정에 담기

주의: "/items", "/courses"는 "/{itinerary_id}"보다 먼저 등록해야 한다.
(지금은 POST만 있어 겹치지 않지만, 나중에 GET을 추가할 때 순서가 바뀌면 "items"를 일정 번호로 읽으려다 422가 난다.)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser
from app.core.errors import get_language
from app.itineraries import schemas
from app.itineraries.repository import ItineraryRepository, get_itinerary_repository
from app.itineraries.service import ItineraryService
from app.places.repository import PlaceRepository, get_place_repository

router = APIRouter(prefix="/api/v1/itineraries", tags=["여행 일정"])


def get_itinerary_service(
    repo: Annotated[ItineraryRepository, Depends(get_itinerary_repository)],
    places: Annotated[PlaceRepository, Depends(get_place_repository)],
) -> ItineraryService:
    return ItineraryService(repo, places)


Service = Annotated[ItineraryService, Depends(get_itinerary_service)]
Lang = Annotated[str, Depends(get_language)]


# ---------------------------------------------------------------- 담기 (먼저 등록)


@router.post("/items", response_model=schemas.AddPlaceResponse, status_code=status.HTTP_201_CREATED)
def add_place(body: schemas.AddPlaceRequest, user: CurrentUser, service: Service):
    """장소를 일정에 담기 (API 28). 맨 뒤에 담긴다. 이미 담긴 장소면 409."""
    return service.add_place(user.id, body)


@router.post("/courses", response_model=schemas.AddCourseResponse, status_code=status.HTTP_201_CREATED)
def add_course(body: schemas.AddCourseRequest, user: CurrentUser, service: Service, lang: Lang):
    """코스를 일정에 담기 (API 31). 이미 담긴 장소는 건너뛴다."""
    return service.add_course(user.id, body, lang=lang)


# ---------------------------------------------------------------- 일정


@router.get("", response_model=schemas.ItineraryListResponse)
def list_itineraries(
    user: CurrentUser,
    service: Service,
    place_id: Annotated[int | None, Query(description="이 장소가 이미 담긴 일정인지 알려줌(contains_place)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """내 여행 일정 목록 (API 23). 최근에 바뀐 일정부터."""
    return service.list_itineraries(user.id, place_id=place_id, page=page, size=size)


@router.post("", response_model=schemas.ItineraryDetail, status_code=status.HTTP_201_CREATED)
def create_itinerary(body: schemas.ItineraryCreateRequest, user: CurrentUser, service: Service, lang: Lang):
    """여행 일정 만들기 (API 24). 응답은 일정 보기(25번)와 같은 모양, 항목은 빈 배열."""
    return service.create(user.id, body.title, body.travel_date, lang=lang)


@router.get("/{itinerary_id}", response_model=schemas.ItineraryDetail)
def get_itinerary(
    itinerary_id: int,
    user: CurrentUser,
    service: Service,
    lang: Lang,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
):
    """여행 일정 보기 (API 25). 장소 순서, 방문 여부, 장소 사이 도보 시간, 합계."""
    return service.get_detail(user.id, itinerary_id, lang=lang, lat=lat, lng=lng)


@router.patch("/{itinerary_id}", response_model=schemas.ItineraryDetail)
def update_itinerary(
    itinerary_id: int, body: schemas.ItineraryUpdateRequest, user: CurrentUser, service: Service, lang: Lang
):
    """여행 일정 고치기 (API 26). 보낸 값만 바뀐다."""
    return service.update(user.id, itinerary_id, body, lang=lang)


@router.delete("/{itinerary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_itinerary(itinerary_id: int, user: CurrentUser, service: Service):
    """여행 일정 지우기 (API 27). 담긴 장소도 모두 지운다."""
    service.delete(user.id, itinerary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 일정 항목


@router.patch("/{itinerary_id}/items/{item_id}", response_model=schemas.ItineraryDetail)
def update_item(
    itinerary_id: int,
    item_id: int,
    body: schemas.ItemUpdateRequest,
    user: CurrentUser,
    service: Service,
    lang: Lang,
):
    """일정 항목 고치기 (API 29): 순서 바꾸기, 메모, 방문 체크. 일정 전체를 돌려준다."""
    return service.update_item(user.id, itinerary_id, item_id, body, lang=lang)


@router.delete("/{itinerary_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(itinerary_id: int, item_id: int, user: CurrentUser, service: Service):
    """일정에서 장소 빼기 (API 30). 뒤 항목의 순서가 하나씩 당겨진다."""
    service.remove_item(user.id, itinerary_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
