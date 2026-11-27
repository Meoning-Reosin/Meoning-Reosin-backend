"""찜 데이터 읽기·쓰기 (repository 층, 임시: 메모리).

DB가 준비되기 전까지 찜을 메모리에 둔다. 서버를 다시 켜면 사라진다.
DB 테이블: bookmarks (user_id, place_id, created_at). (user_id, place_id)는 겹칠 수 없다(UNIQUE).
DB를 붙일 때는 이 파일의 BookmarkRepository만 DB 버전으로 바꾸고, service와 router는 그대로 둔다.

이 클래스는 관광지 기능이 쓰는 찜 창구(app/places/bookmark_reader.py의 BookmarkReader)도 겸한다.
count()와 is_bookmarked()가 그 역할이다.
"""

import threading
from datetime import UTC, datetime


class BookmarkRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (회원 번호, 장소 번호) → 찜한 시각
        self._items: dict[tuple[int, int], datetime] = {}

    def add(self, user_id: int, place_id: int) -> tuple[datetime, bool]:
        """찜을 추가한다. (찜한 시각, 새로 추가했는지)를 돌려준다. 이미 있으면 그대로 둔다."""
        with self._lock:
            key = (user_id, place_id)
            if key in self._items:
                return self._items[key], False
            now = datetime.now(UTC)
            self._items[key] = now
            return now, True

    def remove(self, user_id: int, place_id: int) -> None:
        """찜을 지운다. 없으면 아무 일도 하지 않는다."""
        with self._lock:
            self._items.pop((user_id, place_id), None)

    def list_place_ids(self, user_id: int) -> list[int]:
        """이 회원이 찜한 장소 번호. 최근에 찜한 것부터."""
        # 파이썬 dict는 넣은 순서를 기억하므로, 거꾸로 읽으면 최근 것부터 나온다.
        # (시각으로 정렬하면 아주 빠르게 두 번 찜했을 때 시각이 같아 순서가 흔들릴 수 있다.)
        # DB 버전에서는 ORDER BY created_at DESC, id DESC 로 같은 결과를 낸다.
        return [pid for (uid, pid) in reversed(self._items) if uid == user_id]

    def count(self, place_id: int) -> int:
        """이 장소를 찜한 사람 수 (전체 회원 기준)."""
        return sum(1 for (_, pid) in self._items if pid == place_id)

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        return (user_id, place_id) in self._items

    def delete_user(self, user_id: int) -> None:
        """회원 탈퇴 때 그 회원의 찜을 모두 지운다."""
        with self._lock:
            for key in [k for k in self._items if k[0] == user_id]:
                del self._items[key]


_repository = BookmarkRepository()


def get_bookmark_repository() -> BookmarkRepository:
    """서버 전체가 함께 쓰는 찜 저장소 하나. 테스트에서는 dependency_overrides로 새것을 끼운다."""
    return _repository
