"""관광지 화면에 필요한 찜 정보(찜 수, 내가 찜했는지)를 읽는 창구.

찜 기능(bookmarks 패키지)은 아직 없다. 그래서 지금은 "찜 0개, 찜 안 함"을 돌려주는 빈 버전을 쓴다.
bookmarks 패키지를 만들 때 get_bookmark_reader가 진짜 찜 저장소를 돌려주게 바꾸면
관광지 코드는 고칠 필요가 없다.
"""

from typing import Protocol


class BookmarkReader(Protocol):
    def count(self, place_id: int) -> int:
        """이 장소를 찜한 사람 수."""
        ...

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        """이 회원이 이 장소를 찜했는지."""
        ...


class EmptyBookmarkReader:
    """찜 기능이 생기기 전까지 쓰는 빈 버전."""

    def count(self, place_id: int) -> int:
        return 0

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        return False


_empty = EmptyBookmarkReader()


def get_bookmark_reader() -> BookmarkReader:
    # TODO(bookmarks 패키지): 찜 저장소를 돌려주게 바꾼다.
    return _empty
