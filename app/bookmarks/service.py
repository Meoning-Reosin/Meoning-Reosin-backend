"""찜 업무 규칙 (service 층).

- 없는 장소는 찜할 수 없다 (PLACE_NOT_FOUND).
- 같은 장소를 두 번 찜해도 하나만 남는다. 두 번째는 "이미 찜함"으로 알려준다(router가 200으로 응답).
- 찜하지 않은 장소를 풀어도 오류가 아니다(멱등). 버튼을 두 번 눌러도 문제없게.
- 찜 목록은 관광지 카드 모양을 그대로 쓰기 위해 PlaceService에게 카드를 만들어 달라고 한다.
"""

from app.bookmarks import schemas
from app.bookmarks.repository import BookmarkRepository
from app.places.service import PlaceService


class BookmarkService:
    def __init__(self, repo: BookmarkRepository, places: PlaceService) -> None:
        self.repo = repo
        self.places = places

    def list_bookmarks(self, user_id: int, *, lang: str, page: int, size: int) -> schemas.BookmarkListResponse:
        """20. 내 찜 목록."""
        cards = self.places.place_cards(self.repo.list_place_ids(user_id), lang=lang, user_id=user_id)
        start = (page - 1) * size
        return schemas.BookmarkListResponse(items=cards[start : start + size], page=page, size=size, total=len(cards))

    def add(self, user_id: int, place_id: int) -> tuple[schemas.BookmarkResponse, bool]:
        """21. 찜하기. (응답, 새로 찜했는지)를 돌려준다."""
        self.places.ensure_place_exists(place_id)
        created_at, created = self.repo.add(user_id, place_id)
        response = schemas.BookmarkResponse(
            place_id=place_id, bookmark_count=self.repo.count(place_id), created_at=created_at
        )
        return response, created

    def remove(self, user_id: int, place_id: int) -> None:
        """22. 찜 해제. 없는 장소면 PLACE_NOT_FOUND, 찜하지 않았던 장소면 그냥 끝낸다."""
        self.places.ensure_place_exists(place_id)
        self.repo.remove(user_id, place_id)
