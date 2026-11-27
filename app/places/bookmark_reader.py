"""관광지 화면에 필요한 찜 정보(찜 수, 내가 찜했는지)를 읽는 창구.

관광지 기능은 찜이 어떻게 저장되는지 모르고, 이 창구(BookmarkReader)로 두 가지만 묻는다.
실제로는 찜 저장소(app/bookmarks/repository.py)가 이 창구 역할을 한다.
테스트에서는 get_bookmark_reader를 가짜로 바꿔 끼워 찜 수를 마음대로 정할 수 있다.
"""

from typing import Annotated, Protocol

from fastapi import Depends

from app.bookmarks.repository import BookmarkRepository, get_bookmark_repository


class BookmarkReader(Protocol):
    def count(self, place_id: int) -> int:
        """이 장소를 찜한 사람 수."""
        ...

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        """이 회원이 이 장소를 찜했는지."""
        ...


class EmptyBookmarkReader:
    """찜이 하나도 없는 창구. 테스트처럼 찜과 상관없이 관광지만 볼 때 쓴다."""

    def count(self, place_id: int) -> int:
        return 0

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        return False


def get_bookmark_reader(
    bookmarks: Annotated[BookmarkRepository, Depends(get_bookmark_repository)],
) -> BookmarkReader:
    return bookmarks
