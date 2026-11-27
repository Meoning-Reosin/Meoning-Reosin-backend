"""관광지 데이터 읽기 (repository 층).

지금은 app/places/data/places.json을 읽어 메모리에 둔다 (임시 데이터, Q-26).
DB가 준비되면 이 파일의 PlaceRepository만 DB 버전으로 바꾸고, service와 router는 그대로 둔다.
DB 테이블과의 대응: places, place_images, place_scripts, categories, place_categories,
place_operating_info, courses, course_items.

이 층의 규칙: 데이터를 꺼내 주기만 한다. 정렬·거르기·계산 같은 판단은 service가 한다.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "places.json"

# 언어별 글자: {"ko": "...", "en": "..."}
Localized = dict[str, str]


def pick(text: Localized | None, lang: str) -> str | None:
    """고른 언어의 글자를 꺼낸다. 그 언어가 없으면 한국어로."""
    if not text:
        return None
    return text.get(lang) or text.get("ko")


@dataclass(frozen=True)
class Category:
    id: int
    group: str  # history / sns / content / festival
    name: Localized
    description: Localized


@dataclass(frozen=True)
class OperatingInfo:
    always_open: bool  # 바깥 유적처럼 언제나 볼 수 있으면 True
    open: str | None  # "09:00" (always_open이면 None)
    close: str | None
    closed_weekdays: tuple[int, ...]  # 쉬는 요일. 월=0 ... 일=6
    opening_hours: Localized  # 화면에 보여줄 문구
    last_admission: str | None
    closed_days: Localized
    admission_fee: Localized
    reservation: Localized
    source_url: str | None


@dataclass(frozen=True)
class Script:
    script_id: int
    content: str
    audio_url: str | None
    duration_seconds: int | None


@dataclass(frozen=True)
class Place:
    id: int
    name: Localized
    area: Localized
    address: str
    lat: float
    lng: float
    category_ids: tuple[int, ...]
    expected_visit_minutes: int
    thumbnail_url: str | None
    images: tuple[dict, ...]  # url, author, license, license_url, source (사진이 오면 채움)
    summary: Localized
    highlights: dict[str, list[str]]
    audio: dict | None  # url, duration_seconds, source
    operating: OperatingInfo
    scripts: dict[str, Script]  # 언어 코드 → 해설 대본


@dataclass(frozen=True)
class Course:
    id: int
    group: str
    category_ids: tuple[int, ...]
    title: Localized
    subtitle: Localized
    description: Localized
    thumbnail_url: str | None
    place_ids: tuple[int, ...]  # 걷는 순서대로


class PlaceRepository:
    def __init__(self, data: dict) -> None:
        self._categories = {c["id"]: _to_category(c) for c in data["categories"]}
        self._places = {p["id"]: _to_place(p) for p in data["places"]}
        self._courses = {c["id"]: _to_course(c) for c in data["courses"]}

    @classmethod
    def from_file(cls, path: Path = DATA_FILE) -> "PlaceRepository":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    # --- 장소 ---
    def list_places(self) -> list[Place]:
        return list(self._places.values())

    def get_place(self, place_id: int) -> Place | None:
        return self._places.get(place_id)

    # --- 카테고리 ---
    def list_categories(self) -> list[Category]:
        return list(self._categories.values())

    def get_category(self, category_id: int) -> Category | None:
        return self._categories.get(category_id)

    # --- 코스 ---
    def list_courses(self) -> list[Course]:
        return list(self._courses.values())

    def get_course(self, course_id: int) -> Course | None:
        return self._courses.get(course_id)


@lru_cache
def get_place_repository() -> PlaceRepository:
    """서버가 켜질 때 한 번만 파일을 읽는다. 테스트에서는 dependency_overrides로 바꿔 끼운다."""
    return PlaceRepository.from_file()


# --- JSON → 데이터 클래스 ---
def _to_category(raw: dict) -> Category:
    return Category(id=raw["id"], group=raw["group"], name=raw["name"], description=raw["description"])


def _to_place(raw: dict) -> Place:
    op = raw["operating"]
    return Place(
        id=raw["id"],
        name=raw["name"],
        area=raw["area"],
        address=raw["address"],
        lat=raw["lat"],
        lng=raw["lng"],
        category_ids=tuple(raw["category_ids"]),
        expected_visit_minutes=raw["expected_visit_minutes"],
        thumbnail_url=raw.get("thumbnail_url"),
        images=tuple(raw.get("images", [])),
        summary=raw["summary"],
        highlights=raw.get("highlights", {}),
        audio=raw.get("audio"),
        operating=OperatingInfo(
            always_open=op["always_open"],
            open=op.get("open"),
            close=op.get("close"),
            closed_weekdays=tuple(op.get("closed_weekdays", [])),
            opening_hours=op["opening_hours"],
            last_admission=op.get("last_admission"),
            closed_days=op["closed_days"],
            admission_fee=op["admission_fee"],
            reservation=op["reservation"],
            source_url=op.get("source_url"),
        ),
        scripts={lang: Script(**s) for lang, s in raw.get("scripts", {}).items()},
    )


def _to_course(raw: dict) -> Course:
    return Course(
        id=raw["id"],
        group=raw["group"],
        category_ids=tuple(raw["category_ids"]),
        title=raw["title"],
        subtitle=raw["subtitle"],
        description=raw["description"],
        thumbnail_url=raw.get("thumbnail_url"),
        place_ids=tuple(raw["place_ids"]),
    )
