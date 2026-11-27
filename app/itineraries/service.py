"""여행 일정 업무 규칙 (service 층).

규칙
- 일정은 만든 사람만 보고 고칠 수 있다. 다른 사람 일정이면 403 FORBIDDEN, 없는 일정이면 404.
  TODO(초대·참여 ITN-11): 참여자(itinerary_members)도 볼 수 있게 _check_access를 넓힌다.
- 같은 일정에 같은 장소를 두 번 담을 수 없다 (409). 코스를 담을 때는 이미 있는 장소를 건너뛴다.
- 새 장소는 맨 뒤에 담는다. 순서를 바꾸면 나머지는 저절로 밀리고, 빼면 뒤 항목이 당겨진다.
- 장소 사이 도보 시간은 직선거리로 어림한다 (app/core/geo.py). 정확한 길은 확장안(TMAP).

이 층은 HTTP를 모른다. 문제가 생기면 AppError(code)를 던진다.
"""

from datetime import UTC, date, datetime

from app.core.errors import AppError
from app.core.geo import distance_m, walk_minutes
from app.itineraries import errors as _errors  # noqa: F401  오류 코드 등록
from app.itineraries import schemas
from app.itineraries.repository import Itinerary, ItineraryRepository
from app.places import errors as _place_errors  # noqa: F401  PLACE_NOT_FOUND, COURSE_NOT_FOUND 등록
from app.places.repository import PlaceRepository, pick


class ItineraryService:
    def __init__(self, repo: ItineraryRepository, places: PlaceRepository) -> None:
        self.repo = repo
        self.places = places

    # ------------------------------------------------------------------ 23. 목록
    def list_itineraries(
        self, user_id: int, *, place_id: int | None, page: int, size: int
    ) -> schemas.ItineraryListResponse:
        itineraries = self.repo.list_owned(user_id)
        summaries = [
            schemas.ItinerarySummary(
                itinerary_id=it.id,
                title=it.title,
                travel_date=it.travel_date,
                item_count=len(it.items),
                my_role="owner",
                is_public=it.is_public,
                updated_at=it.updated_at,
                # "일정에 추가" 창: 이 장소가 이미 담긴 일정에 표시하려고 쓴다
                contains_place=None if place_id is None else any(i.place_id == place_id for i in it.items),
            )
            for it in itineraries
        ]
        start = (page - 1) * size
        return schemas.ItineraryListResponse(
            items=summaries[start : start + size], page=page, size=size, total=len(summaries)
        )

    # ------------------------------------------------------------------ 24~27. 만들기·보기·고치기·지우기
    def create(self, user_id: int, title: str, travel_date: date | None, *, lang: str) -> schemas.ItineraryDetail:
        itinerary = self.repo.create(user_id, title, travel_date)
        return self.detail(itinerary, lang=lang)

    def get_detail(
        self, user_id: int, itinerary_id: int, *, lang: str, lat: float | None = None, lng: float | None = None
    ) -> schemas.ItineraryDetail:
        if (lat is None) != (lng is None):
            raise AppError("INVALID_LOCATION")
        return self.detail(self._get_own(user_id, itinerary_id), lang=lang, lat=lat, lng=lng)

    def update(
        self, user_id: int, itinerary_id: int, body: schemas.ItineraryUpdateRequest, *, lang: str
    ) -> schemas.ItineraryDetail:
        itinerary = self._get_own(user_id, itinerary_id)
        # 보낸 칸만 바꾼다. title에 null을 보내면 무시(이름은 비울 수 없음), travel_date에 null이면 날짜 지우기.
        changes = {}
        if "title" in body.model_fields_set and body.title is not None:
            changes["title"] = body.title
        if "travel_date" in body.model_fields_set:
            changes["travel_date"] = body.travel_date
        if changes:
            itinerary = self.repo.update(itinerary.id, **changes)
        return self.detail(itinerary, lang=lang)

    def delete(self, user_id: int, itinerary_id: int) -> None:
        self._get_own(user_id, itinerary_id)
        self.repo.delete(itinerary_id)

    # ------------------------------------------------------------------ 28. 장소 담기
    def add_place(self, user_id: int, body: schemas.AddPlaceRequest) -> schemas.AddPlaceResponse:
        itinerary = self._get_own(user_id, body.itinerary_id)
        if self.places.get_place(body.place_id) is None:
            raise AppError("PLACE_NOT_FOUND")
        if any(item.place_id == body.place_id for item in itinerary.items):
            raise AppError("PLACE_ALREADY_IN_ITINERARY")
        item = self.repo.add_item(itinerary.id, body.place_id, body.memo)
        return schemas.AddPlaceResponse(itinerary_id=itinerary.id, item_id=item.id, visit_order=len(itinerary.items))

    # ------------------------------------------------------------------ 29. 항목 고치기 (순서, 메모, 방문 체크)
    def update_item(
        self, user_id: int, itinerary_id: int, item_id: int, body: schemas.ItemUpdateRequest, *, lang: str
    ) -> schemas.ItineraryDetail:
        itinerary = self._get_own(user_id, itinerary_id)
        item = self.repo.get_item(itinerary.id, item_id)
        if item is None:
            raise AppError("ITEM_NOT_FOUND")

        sent = body.model_fields_set
        changes = {}
        if "memo" in sent:
            changes["memo"] = body.memo  # null이면 메모 지우기
        if "visited" in sent and body.visited is not None:
            # 이미 방문 체크한 항목을 다시 true로 보내도 처음 체크한 시각을 그대로 둔다
            if body.visited and item.visited_at is None:
                changes["visited_at"] = datetime.now(UTC)
            elif not body.visited:
                changes["visited_at"] = None
        if changes:
            self.repo.update_item(itinerary.id, item.id, **changes)

        if "visit_order" in sent and body.visit_order is not None:
            # 1부터 세는 순서를 0부터 세는 자리로 바꾸고, 마지막보다 크면 맨 뒤로
            new_index = min(body.visit_order, len(itinerary.items)) - 1
            self.repo.move_item(itinerary.id, item.id, new_index)

        return self.detail(self.repo.get(itinerary.id), lang=lang)

    # ------------------------------------------------------------------ 30. 장소 빼기
    def remove_item(self, user_id: int, itinerary_id: int, item_id: int) -> None:
        itinerary = self._get_own(user_id, itinerary_id)
        if self.repo.get_item(itinerary.id, item_id) is None:
            raise AppError("ITEM_NOT_FOUND")
        self.repo.remove_item(itinerary.id, item_id)

    # ------------------------------------------------------------------ 31. 코스 담기
    def add_course(self, user_id: int, body: schemas.AddCourseRequest, *, lang: str) -> schemas.AddCourseResponse:
        course = self.places.get_course(body.course_id)
        if course is None:
            raise AppError("COURSE_NOT_FOUND")
        if body.itinerary_id is None:
            # 일정을 고르지 않았으면 코스 이름으로 새 일정을 만든다 (제목 50자 제한에 맞춰 자름)
            itinerary = self.repo.create(user_id, (pick(course.title, lang) or "")[:50], None)
        else:
            itinerary = self._get_own(user_id, body.itinerary_id)

        already = {item.place_id for item in itinerary.items}
        added = skipped = 0
        for place_id in course.place_ids:
            if place_id in already or self.places.get_place(place_id) is None:
                skipped += 1
                continue
            self.repo.add_item(itinerary.id, place_id, None)
            already.add(place_id)
            added += 1
        return schemas.AddCourseResponse(itinerary_id=itinerary.id, added_count=added, skipped_count=skipped)

    # ------------------------------------------------------------------ 탈퇴
    def delete_user_data(self, user_id: int) -> None:
        self.repo.delete_owned_by(user_id)

    # ------------------------------------------------------------------ 공통
    def _get_own(self, user_id: int, itinerary_id: int) -> Itinerary:
        """일정을 꺼내고 볼 수 있는 사람인지 확인한다."""
        itinerary = self.repo.get(itinerary_id)
        if itinerary is None:
            raise AppError("ITINERARY_NOT_FOUND")
        if itinerary.owner_id != user_id:
            raise AppError("FORBIDDEN")
        return itinerary

    def detail(
        self, itinerary: Itinerary, *, lang: str, lat: float | None = None, lng: float | None = None
    ) -> schemas.ItineraryDetail:
        """일정 상세 응답을 만든다. 장소 사이 거리·도보 시간과 합계를 여기서 계산한다 (ITN-04, ITN-08)."""
        items: list[schemas.ItineraryItemResponse] = []
        total_visit = total_walk = visited = 0
        previous = None
        order = 0
        for item in itinerary.items:
            place = self.places.get_place(item.place_id)
            if place is None:  # 장소 데이터에서 빠진 장소는 건너뜀
                continue
            order += 1
            gap = walk = None
            if previous is not None:
                gap = distance_m(previous.lat, previous.lng, place.lat, place.lng)
                walk = walk_minutes(gap)
                total_walk += walk
            total_visit += place.expected_visit_minutes
            visited += item.visited_at is not None
            items.append(
                schemas.ItineraryItemResponse(
                    item_id=item.id,
                    visit_order=order,
                    memo=item.memo,
                    visited=item.visited_at is not None,
                    visited_at=item.visited_at,
                    distance_m_from_previous=gap,
                    walk_minutes_from_previous=walk,
                    place=schemas.ItemPlace(
                        place_id=place.id,
                        name=pick(place.name, lang),
                        name_en=pick(place.name, "en"),
                        thumbnail_url=place.thumbnail_url,
                        lat=place.lat,
                        lng=place.lng,
                        distance_m=distance_m(lat, lng, place.lat, place.lng) if lat is not None else None,
                        expected_visit_minutes=place.expected_visit_minutes,
                    ),
                )
            )
            previous = place
        return schemas.ItineraryDetail(
            itinerary_id=itinerary.id,
            title=itinerary.title,
            travel_date=itinerary.travel_date,
            my_role="owner",
            is_public=itinerary.is_public,
            member_count=1,  # TODO(ITN-12): 참여자 수
            item_count=len(items),
            visited_count=visited,
            total_visit_minutes=total_visit,
            total_walk_minutes=total_walk,
            total_minutes=total_visit + total_walk,
            created_at=itinerary.created_at,
            updated_at=itinerary.updated_at,
            items=items,
        )
