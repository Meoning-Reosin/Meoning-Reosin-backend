"""관광지·카테고리·코스의 업무 규칙 (service 층).

여기서 하는 일: 검색어·카테고리로 거르기, 정렬, 페이지 나누기, 거리·도보 시간 계산,
지금 열었는지 판단, 코스 총 소요 시간 계산, 고른 언어로 응답 채우기.

이 층의 규칙:
- 데이터가 어디에 있는지(JSON인지 DB인지) 모른다. repository에게 달라고만 한다.
- HTTP를 모른다. 문제가 생기면 AppError(code)를 던진다. 응답으로 바꾸는 일은 app/core/errors.py가 한다.
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.errors import AppError
from app.core.geo import distance_m, walk_minutes
from app.places import errors as _errors  # noqa: F401  오류 코드 등록
from app.places import schemas
from app.places.bookmark_reader import BookmarkReader
from app.places.repository import Course, Place, PlaceRepository, pick

KST = ZoneInfo("Asia/Seoul")


def _now_kst() -> datetime:
    return datetime.now(KST)


class PlaceService:
    def __init__(
        self,
        repo: PlaceRepository,
        bookmarks: BookmarkReader,
        clock: Callable[[], datetime] = _now_kst,  # 테스트에서 "지금"을 정해 넣을 수 있게
    ) -> None:
        self.repo = repo
        self.bookmarks = bookmarks
        self.clock = clock

    # ------------------------------------------------------------------
    # 11. 관광지 목록·검색
    # ------------------------------------------------------------------
    def search_places(
        self,
        *,
        lang: str,
        user_id: int | None,
        q: str | None = None,
        category_id: int | None = None,
        group: str | None = None,
        sort: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        page: int = 1,
        size: int = 20,
    ) -> schemas.PlaceListResponse:
        has_location = _check_location(lat, lng)
        # 정렬 기본값: 위치가 있으면 가까운 순, 없으면 찜이 많은 순 (명세서 11번)
        sort = sort or ("distance" if has_location else "bookmarks")
        if sort == "distance" and not has_location:
            raise AppError("LOCATION_REQUIRED")

        places = [p for p in self.repo.list_places() if self._matches(p, q, category_id, group)]
        cards = [self._card(p, lang, user_id, lat, lng) for p in places]

        if sort == "distance":
            cards.sort(key=lambda c: (c.distance_m, c.place_id))
        elif sort == "bookmarks":
            cards.sort(key=lambda c: (-c.bookmark_count, c.place_id))
        else:  # name
            cards.sort(key=lambda c: (c.name, c.place_id))

        start = (page - 1) * size
        return schemas.PlaceListResponse(
            items=cards[start : start + size], sort=sort, page=page, size=size, total=len(cards)
        )

    def _matches(self, place: Place, q: str | None, category_id: int | None, group: str | None) -> bool:
        if q:
            # 한국어·영어 이름 어디에든 검색어가 들어 있으면 찾음. 띄어쓰기와 대소문자는 무시
            needle = q.replace(" ", "").lower()
            names = [n.replace(" ", "").lower() for n in place.name.values()]
            if not any(needle in n for n in names):
                return False
        if category_id is not None and category_id not in place.category_ids:
            return False
        if group is not None:
            groups = {c.group for c in self._categories_of(place)}
            if group not in groups:
                return False
        return True

    def _card(
        self, place: Place, lang: str, user_id: int | None, lat: float | None, lng: float | None
    ) -> schemas.PlaceCard:
        dist = distance_m(lat, lng, place.lat, place.lng) if lat is not None and lng is not None else None
        return schemas.PlaceCard(
            place_id=place.id,
            name=pick(place.name, lang),
            name_en=pick(place.name, "en"),
            area=pick(place.area, lang),
            thumbnail_url=place.thumbnail_url,
            address=place.address,
            lat=place.lat,
            lng=place.lng,
            distance_m=dist,
            walk_minutes=walk_minutes(dist) if dist is not None else None,
            bookmark_count=self.bookmarks.count(place.id),
            is_bookmarked=self._is_bookmarked(user_id, place.id),
            expected_visit_minutes=place.expected_visit_minutes,
            categories=self._category_briefs(place, lang),
        )

    def place_cards(self, place_ids: list[int], *, lang: str, user_id: int | None) -> list[schemas.PlaceCard]:
        """장소 번호 순서 그대로 장소 카드를 만든다. 다른 기능(찜 목록 등)이 같은 카드 모양을 쓸 때 부른다.

        없는 장소 번호는 건너뛴다 (예: 찜한 뒤 장소 데이터에서 빠진 경우).
        """
        places = [p for pid in place_ids if (p := self.repo.get_place(pid)) is not None]
        return [self._card(p, lang, user_id, None, None) for p in places]

    def ensure_place_exists(self, place_id: int) -> None:
        """없는 장소면 PLACE_NOT_FOUND."""
        self._get_place(place_id)

    # ------------------------------------------------------------------
    # 12. 장소 상세
    # ------------------------------------------------------------------
    def get_place_detail(self, place_id: int, *, lang: str, user_id: int | None) -> schemas.PlaceDetail:
        place = self._get_place(place_id)
        return schemas.PlaceDetail(
            place_id=place.id,
            name=pick(place.name, lang),
            name_en=pick(place.name, "en"),
            area=pick(place.area, lang),
            address=place.address,
            lat=place.lat,
            lng=place.lng,
            images=[schemas.PlaceImage(**img) for img in place.images],
            categories=self._category_briefs(place, lang),
            introduction=schemas.Introduction(
                summary=pick(place.summary, lang),
                summary_en=pick(place.summary, "en"),
                highlights=place.highlights.get(lang) or place.highlights.get("ko", []),
            ),
            audio=schemas.Audio(**place.audio) if place.audio else None,
            is_bookmarked=self._is_bookmarked(user_id, place.id),
            bookmark_count=self.bookmarks.count(place.id),
        )

    # ------------------------------------------------------------------
    # 13. 운영 정보
    # ------------------------------------------------------------------
    def get_operating_info(self, place_id: int, *, lang: str) -> schemas.OperatingInfoResponse:
        place = self._get_place(place_id)
        op = place.operating
        return schemas.OperatingInfoResponse(
            opening_hours=pick(op.opening_hours, lang),
            last_admission=op.last_admission,
            closed_days=pick(op.closed_days, lang),
            admission_fee=pick(op.admission_fee, lang),
            reservation=pick(op.reservation, lang),
            expected_visit_minutes=place.expected_visit_minutes,
            is_open_now=self.is_open_now(place),
            # TODO(TourAPI): 가져온 값으로 바꾸면 source="한국관광공사 TourAPI", updated_at=가져온 시각
            source=None,
            source_url=op.source_url,
            updated_at=None,
        )

    def is_open_now(self, place: Place) -> bool:
        """지금(한국 시간) 들어갈 수 있는지. 입장 마감 시각이 있으면 그 시각까지만 열린 것으로 본다."""
        op = place.operating
        if op.always_open:
            return True
        now = self.clock().astimezone(KST)
        if now.weekday() in op.closed_weekdays:
            return False
        current = now.strftime("%H:%M")  # "09:30"처럼 같은 모양이면 글자 비교로 시각을 비교할 수 있다
        last_entry = op.last_admission or op.close
        return op.open <= current < last_entry

    # ------------------------------------------------------------------
    # 16. 해설 대본
    # ------------------------------------------------------------------
    def get_script(self, place_id: int, *, lang: str) -> schemas.ScriptResponse:
        place = self._get_place(place_id)
        script = place.scripts.get(lang)
        if script is None:
            raise AppError("SCRIPT_NOT_FOUND")
        return schemas.ScriptResponse(
            script_id=script.script_id,
            language=lang,
            content=script.content,
            source="odii",
            audio_url=script.audio_url,
            duration_seconds=script.duration_seconds,
        )

    # ------------------------------------------------------------------
    # 17. 카테고리 목록
    # ------------------------------------------------------------------
    def list_categories(self, *, lang: str, group: str | None = None) -> schemas.CategoryListResponse:
        items = [
            schemas.CategoryItem(
                category_id=c.id,
                name=pick(c.name, lang),
                name_en=pick(c.name, "en"),
                description=pick(c.description, lang),
                group=c.group,
            )
            for c in self.repo.list_categories()
            if group is None or c.group == group
        ]
        return schemas.CategoryListResponse(items=items)

    # ------------------------------------------------------------------
    # 32. 추천 코스 목록 / 33. 코스 상세
    # ------------------------------------------------------------------
    def list_courses(
        self,
        *,
        lang: str,
        category_id: int | None = None,
        group: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> schemas.CourseListResponse:
        courses = [
            c
            for c in self.repo.list_courses()
            if (category_id is None or category_id in c.category_ids) and (group is None or c.group == group)
        ]
        cards = [
            schemas.CourseCard(
                course_id=c.id,
                title=pick(c.title, lang),
                title_en=pick(c.title, "en"),
                subtitle=pick(c.subtitle, lang),
                group=c.group,
                thumbnail_url=c.thumbnail_url,
                place_count=len(c.place_ids),
                total_minutes=self._course_places(c, lang)[1],
            )
            for c in courses
        ]
        start = (page - 1) * size
        return schemas.CourseListResponse(items=cards[start : start + size], page=page, size=size, total=len(cards))

    def get_course_detail(self, course_id: int, *, lang: str) -> schemas.CourseDetail:
        course = self.repo.get_course(course_id)
        if course is None:
            raise AppError("COURSE_NOT_FOUND")
        places, total = self._course_places(course, lang)
        return schemas.CourseDetail(
            course_id=course.id,
            title=pick(course.title, lang),
            title_en=pick(course.title, "en"),
            subtitle=pick(course.subtitle, lang),
            description=pick(course.description, lang),
            places=places,
            total_minutes=total,
        )

    def _course_places(self, course: Course, lang: str) -> tuple[list[schemas.CoursePlace], int]:
        """코스 장소를 순서대로 만들고, 총 소요 시간(관람 + 장소 사이 도보)을 함께 돌려준다."""
        items: list[schemas.CoursePlace] = []
        total = 0
        previous: Place | None = None
        for order, place_id in enumerate(course.place_ids, start=1):
            place = self.repo.get_place(place_id)
            if place is None:  # 데이터 실수로 없는 장소가 들어 있으면 건너뜀 (테스트로 막아 둠)
                continue
            walk = None
            if previous is not None:
                walk = walk_minutes(distance_m(previous.lat, previous.lng, place.lat, place.lng))
                total += walk
            total += place.expected_visit_minutes
            items.append(
                schemas.CoursePlace(
                    order=order,
                    place_id=place.id,
                    name=pick(place.name, lang),
                    name_en=pick(place.name, "en"),
                    thumbnail_url=place.thumbnail_url,
                    expected_visit_minutes=place.expected_visit_minutes,
                    walk_minutes_from_previous=walk,
                )
            )
            previous = place
        return items, total

    # ------------------------------------------------------------------
    # 공통 도우미
    # ------------------------------------------------------------------
    def _get_place(self, place_id: int) -> Place:
        place = self.repo.get_place(place_id)
        if place is None:
            raise AppError("PLACE_NOT_FOUND")
        return place

    def _categories_of(self, place: Place):
        return [c for cid in place.category_ids if (c := self.repo.get_category(cid)) is not None]

    def _category_briefs(self, place: Place, lang: str) -> list[schemas.CategoryBrief]:
        return [schemas.CategoryBrief(category_id=c.id, name=pick(c.name, lang)) for c in self._categories_of(place)]

    def _is_bookmarked(self, user_id: int | None, place_id: int) -> bool:
        return user_id is not None and self.bookmarks.is_bookmarked(user_id, place_id)


def _check_location(lat: float | None, lng: float | None) -> bool:
    """위치를 보냈는지. 둘 중 하나만 보냈으면 오류."""
    if (lat is None) != (lng is None):
        raise AppError("INVALID_LOCATION")
    return lat is not None
