"""여행 일정 데이터 읽기·쓰기 (repository 층, 임시: 메모리).

DB가 준비되기 전까지 일정과 일정 항목을 메모리에 둔다. 서버를 다시 켜면 사라진다.
DB 테이블: itineraries, itinerary_items (명세서 데이터 요구사항 탭).
DB를 붙일 때는 이 파일의 ItineraryRepository만 DB 버전으로 바꾸고, service와 router는 그대로 둔다.

방문 순서(visit_order)는 따로 저장하지 않고 "목록 안의 위치 + 1"로 계산한다.
그러면 항목을 빼거나 옮겨도 순서가 1, 2, 3 …으로 저절로 맞춰진다.
(DB 버전에서는 visit_order 칸에 저장하고, 옮길 때 한 트랜잭션 안에서 다시 매긴다.)

이 층의 규칙: 저장하고 꺼내기만 한다. "누가 볼 수 있는지", "같은 장소를 두 번 담을 수 있는지" 같은 판단은 service가 한다.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ItineraryItem:
    id: int
    itinerary_id: int
    place_id: int
    memo: str | None
    visited_at: datetime | None  # 방문 체크한 시각. 아직이면 None
    created_at: datetime


@dataclass
class Itinerary:
    id: int
    owner_id: int  # 만든 회원
    title: str
    travel_date: date | None
    created_at: datetime
    updated_at: datetime  # 제목·날짜·항목이 바뀔 때마다 갱신 (목록 정렬 기준)
    is_public: bool = False  # 공개 코스 기능(ITN-09)에서 씀
    items: list[ItineraryItem] = field(default_factory=list)  # 방문 순서대로


class ItineraryRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._itineraries: dict[int, Itinerary] = {}
        self._next_itinerary_id = 1
        self._next_item_id = 1

    # --- 일정 ---
    def create(self, owner_id: int, title: str, travel_date: date | None) -> Itinerary:
        with self._lock:
            now = _now()
            itinerary = Itinerary(
                id=self._next_itinerary_id,
                owner_id=owner_id,
                title=title,
                travel_date=travel_date,
                created_at=now,
                updated_at=now,
            )
            self._itineraries[itinerary.id] = itinerary
            self._next_itinerary_id += 1
            return itinerary

    def get(self, itinerary_id: int) -> Itinerary | None:
        return self._itineraries.get(itinerary_id)

    def list_owned(self, owner_id: int) -> list[Itinerary]:
        """이 회원이 만든 일정. 최근에 바뀐 것부터.

        TODO(초대·참여 ITN-11): 참여한 일정도 함께 돌려준다 (itinerary_members).
        """
        mine = [i for i in self._itineraries.values() if i.owner_id == owner_id]
        mine.sort(key=lambda i: (i.updated_at, i.id), reverse=True)
        return mine

    def update(self, itinerary_id: int, **changes) -> Itinerary:
        with self._lock:
            itinerary = self._itineraries[itinerary_id]
            for key, value in changes.items():
                setattr(itinerary, key, value)
            itinerary.updated_at = _now()
            return itinerary

    def delete(self, itinerary_id: int) -> None:
        """일정과 담긴 항목을 모두 지운다."""
        with self._lock:
            self._itineraries.pop(itinerary_id, None)

    def delete_owned_by(self, owner_id: int) -> None:
        """회원 탈퇴 때 그 회원이 만든 일정을 모두 지운다."""
        with self._lock:
            for itinerary_id in [i.id for i in self._itineraries.values() if i.owner_id == owner_id]:
                del self._itineraries[itinerary_id]

    # --- 일정 항목 ---
    def add_item(self, itinerary_id: int, place_id: int, memo: str | None) -> ItineraryItem:
        """맨 뒤에 담는다."""
        with self._lock:
            itinerary = self._itineraries[itinerary_id]
            item = ItineraryItem(
                id=self._next_item_id,
                itinerary_id=itinerary_id,
                place_id=place_id,
                memo=memo,
                visited_at=None,
                created_at=_now(),
            )
            itinerary.items.append(item)
            itinerary.updated_at = _now()
            self._next_item_id += 1
            return item

    def get_item(self, itinerary_id: int, item_id: int) -> ItineraryItem | None:
        itinerary = self._itineraries.get(itinerary_id)
        if itinerary is None:
            return None
        return next((item for item in itinerary.items if item.id == item_id), None)

    def update_item(self, itinerary_id: int, item_id: int, **changes) -> None:
        with self._lock:
            itinerary = self._itineraries[itinerary_id]
            item = next(item for item in itinerary.items if item.id == item_id)
            for key, value in changes.items():
                setattr(item, key, value)
            itinerary.updated_at = _now()

    def move_item(self, itinerary_id: int, item_id: int, new_index: int) -> None:
        """항목을 new_index(0부터) 자리로 옮긴다. 나머지는 한 칸씩 밀리거나 당겨진다."""
        with self._lock:
            itinerary = self._itineraries[itinerary_id]
            item = next(item for item in itinerary.items if item.id == item_id)
            itinerary.items.remove(item)
            itinerary.items.insert(new_index, item)
            itinerary.updated_at = _now()

    def remove_item(self, itinerary_id: int, item_id: int) -> None:
        """항목을 뺀다. 뒤 항목들의 순서가 하나씩 당겨진다."""
        with self._lock:
            itinerary = self._itineraries[itinerary_id]
            itinerary.items = [item for item in itinerary.items if item.id != item_id]
            itinerary.updated_at = _now()


_repository = ItineraryRepository()


def get_itinerary_repository() -> ItineraryRepository:
    """서버 전체가 함께 쓰는 일정 저장소 하나. 테스트에서는 dependency_overrides로 새것을 끼운다."""
    return _repository
