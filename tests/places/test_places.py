"""관광지·카테고리·코스 API 테스트.

- 진짜 데이터 파일(app/places/data/places.json)을 그대로 읽어 쓴다. 데이터 실수(없는 카테고리 등)도 여기서 잡힌다.
- 찜 수는 아직 찜 기능이 없으므로 가짜 찜 창구(FakeBookmarks)를 끼워 시험한다.
- "지금 열었는지"는 시계를 정해 넣고(service의 clock) 시험한다.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth.repository import UserRepository, get_user_repository
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.geo import distance_m, walk_minutes
from app.core.security import ACCESS_COOKIE, create_token
from app.main import app
from app.places.bookmark_reader import EmptyBookmarkReader, get_bookmark_reader
from app.places.repository import DATA_FILE, PlaceRepository
from app.places.service import KST, PlaceService

PLACES = "/api/v1/places"
HWANGUDAN = (37.5652, 126.9800)  # 1번 환구단 좌표


class FakeBookmarks:
    """찜 수와 "내가 찜했는지"를 정해 둔 가짜."""

    def __init__(self, counts: dict[int, int] | None = None, mine: set[tuple[int, int]] | None = None):
        self.counts = counts or {}
        self.mine = mine or set()

    def count(self, place_id: int) -> int:
        return self.counts.get(place_id, 0)

    def is_bookmarked(self, user_id: int, place_id: int) -> bool:
        return (user_id, place_id) in self.mine


@pytest.fixture
def env():
    settings = Settings(_env_file=None, jwt_secret="test-jwt-secret-that-is-long-enough-1234")
    users = UserRepository()
    bookmarks = FakeBookmarks()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_bookmark_reader] = lambda: bookmarks
    yield SimpleNamespace(client=TestClient(app), settings=settings, users=users, bookmarks=bookmarks)
    app.dependency_overrides.clear()


def login(env) -> int:
    """회원 한 명을 만들고 로그인 쿠키를 클라이언트에 넣는다. 회원 번호를 돌려준다."""
    user = env.users.create(
        provider="google",
        provider_user_id="sub-1",
        email="a@example.com",
        nickname="테스터",
        profile_image_url=None,
        language="ko",
        consents={"terms": True, "privacy": True},
        terms_version="2026-11-27",
    )
    token, _ = create_token(env.settings, "access", str(user.id), timedelta(minutes=5))
    env.client.cookies.set(ACCESS_COOKIE, token)
    return user.id


def ids(response) -> list[int]:
    return [item["place_id"] for item in response.json()["items"]]


# ---------------------------------------------------------------- 데이터 파일 점검


def test_data_file_is_consistent():
    """코스에 든 장소, 장소의 카테고리가 모두 실제로 있는지. 언어별 글자와 대본이 다 있는지."""
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    place_ids = {p["id"] for p in data["places"]}
    category_ids = {c["id"] for c in data["categories"]}
    assert len(place_ids) == 10
    for place in data["places"]:
        assert set(place["category_ids"]) <= category_ids, place["id"]
        assert {"ko", "en"} <= set(place["name"]) and {"ko", "en"} <= set(place["scripts"]), place["id"]
    for course in data["courses"]:
        assert set(course["place_ids"]) <= place_ids
        assert len(course["place_ids"]) == 5
    # 코스 A, B가 장소 10곳을 겹치지 않게 나눠 가진다 (Q-28)
    all_course_places = [pid for c in data["courses"] for pid in c["place_ids"]]
    assert sorted(all_course_places) == sorted(place_ids)


def test_geo_helpers():
    assert distance_m(*HWANGUDAN, *HWANGUDAN) == 0
    # 환구단 → 광화문은 직선으로 약 1.2km
    assert 1100 < distance_m(*HWANGUDAN, 37.5760, 126.9769) < 1300
    assert walk_minutes(0) == 1
    assert walk_minutes(670) == 13  # 670m × 1.3 ÷ 67m/분


# ---------------------------------------------------------------- 11. 관광지 목록·검색


def test_list_defaults_to_bookmark_order_without_location(env):
    env.bookmarks.counts = {7: 5, 3: 9}
    response = env.client.get(PLACES)
    assert response.status_code == 200
    body = response.json()
    assert body["sort"] == "bookmarks" and body["total"] == 10 and body["page"] == 1 and body["size"] == 20
    assert ids(response)[:3] == [3, 7, 1]  # 찜 많은 순, 같으면 번호 순
    first = body["items"][0]
    assert first["bookmark_count"] == 9 and first["is_bookmarked"] is False
    assert first["distance_m"] is None and first["walk_minutes"] is None
    assert first["categories"] and {"category_id", "name"} <= set(first["categories"][0])


def test_list_defaults_to_distance_with_location(env):
    lat, lng = HWANGUDAN
    response = env.client.get(PLACES, params={"lat": lat, "lng": lng})
    body = response.json()
    assert body["sort"] == "distance"
    assert body["items"][0]["place_id"] == 1 and body["items"][0]["distance_m"] == 0
    distances = [item["distance_m"] for item in body["items"]]
    assert distances == sorted(distances)


def test_distance_sort_needs_location(env):
    response = env.client.get(PLACES, params={"sort": "distance"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "LOCATION_REQUIRED"


def test_lat_without_lng_is_rejected(env):
    response = env.client.get(PLACES, params={"lat": 37.5}, headers={"Accept-Language": "en"})
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "INVALID_LOCATION",
        "message": "Latitude and longitude must be sent together.",
    }


@pytest.mark.parametrize(
    ("q", "expected"),
    [("환구", [1]), ("DILKUSHA", [8]), ("탑골 공원", [4]), ("없는장소", [])],
)
def test_search_by_name(env, q, expected):
    assert ids(env.client.get(PLACES, params={"q": q})) == expected


def test_filter_by_category_and_group(env):
    assert ids(env.client.get(PLACES, params={"category_id": 6})) == [7, 10]  # 종교
    response = env.client.get(PLACES, params={"group": "sns"})
    assert response.json()["items"] == [] and response.json()["total"] == 0


def test_paging(env):
    body = env.client.get(PLACES, params={"size": 3, "page": 4}).json()
    assert body["total"] == 10 and len(body["items"]) == 1


def test_sort_by_name_uses_chosen_language(env):
    ko = env.client.get(PLACES, params={"sort": "name"}).json()["items"]
    en = env.client.get(PLACES, params={"sort": "name"}, headers={"Accept-Language": "en"}).json()["items"]
    assert [i["name"] for i in ko] == sorted(i["name"] for i in ko)
    assert [i["name"] for i in en] == sorted(i["name"] for i in en)
    assert en[0]["name"] == en[0]["name_en"]


def test_is_bookmarked_only_for_logged_in_user(env):
    env.client.get(PLACES)  # 비회원
    user_id = login(env)
    env.bookmarks.mine = {(user_id, 2)}
    items = {i["place_id"]: i for i in env.client.get(PLACES).json()["items"]}
    assert items[2]["is_bookmarked"] is True and items[1]["is_bookmarked"] is False


def test_bad_token_is_treated_as_guest(env):
    env.client.cookies.set(ACCESS_COOKIE, "not-a-token")
    assert env.client.get(PLACES).status_code == 200


# ---------------------------------------------------------------- 12. 장소 상세


def test_place_detail_in_english(env):
    response = env.client.get(f"{PLACES}/8", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Dilkusha" and body["name_en"] == "Dilkusha"
    assert body["introduction"]["summary"] == body["introduction"]["summary_en"]
    assert body["introduction"]["highlights"]
    assert body["audio"] is None
    assert [image["url"] for image in body["images"]] == ["/api/v1/media/places/8.jpg"]
    assert body["bookmark_count"] == 0 and body["is_bookmarked"] is False


# ---------------------------------------------------------------- 사진 (임시 정적 파일)


def test_every_place_and_course_has_a_photo_file(env):
    """모든 장소·코스의 대표 사진 주소가 실제 파일로 열리는지 (파일 이름 실수 잡기)."""
    places = env.client.get(PLACES, params={"size": 100}).json()["items"]
    courses = env.client.get("/api/v1/courses").json()["items"]
    urls = [p["thumbnail_url"] for p in places] + [c["thumbnail_url"] for c in courses]
    assert len(places) == 10 and all(urls)
    for url in set(urls):
        response = env.client.get(url)
        assert response.status_code == 200, url
        assert response.headers["content-type"] == "image/jpeg"


def test_unknown_photo_is_404(env):
    assert env.client.get("/api/v1/media/places/999.jpg").status_code == 404


def test_unknown_place_is_404(env):
    for path in ["/999", "/999/operating-info", "/999/script"]:
        response = env.client.get(PLACES + path)
        assert response.status_code == 404
        assert response.json()["detail"] == {"code": "PLACE_NOT_FOUND", "message": "없는 장소입니다."}


# ---------------------------------------------------------------- 13. 운영 정보


def test_operating_info_shape(env):
    body = env.client.get(f"{PLACES}/3/operating-info").json()
    assert set(body) == {
        "opening_hours", "last_admission", "closed_days", "admission_fee", "reservation",
        "expected_visit_minutes", "is_open_now", "source", "source_url", "updated_at",
    }
    assert body["last_admission"] == "17:30" and isinstance(body["is_open_now"], bool)


def make_service(now: datetime) -> PlaceService:
    return PlaceService(PlaceRepository.from_file(), EmptyBookmarkReader(), clock=lambda: now)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 30, 10, 0, tzinfo=KST), False),  # 월요일 휴관
        (datetime(2026, 12, 1, 10, 0, tzinfo=KST), True),  # 화요일 10시
        (datetime(2026, 12, 1, 8, 59, tzinfo=KST), False),  # 문 열기 전
        (datetime(2026, 12, 1, 17, 30, tzinfo=KST), False),  # 입장 마감(17:30) 시각부터는 못 들어감
    ],
)
def test_is_open_now_for_post_office(now, expected):
    service = make_service(now)
    assert service.is_open_now(service.repo.get_place(3)) is expected  # 우정총국: 09:00~18:00, 월 휴관


def test_always_open_place():
    service = make_service(datetime(2026, 11, 30, 3, 0, tzinfo=KST))  # 월요일 새벽 3시
    assert service.is_open_now(service.repo.get_place(1)) is True  # 환구단


# ---------------------------------------------------------------- 16. 해설 대본


def test_script_follows_language(env):
    ko = env.client.get(f"{PLACES}/1/script").json()
    en = env.client.get(f"{PLACES}/1/script", headers={"Accept-Language": "en"}).json()
    ja = env.client.get(f"{PLACES}/1/script", headers={"Accept-Language": "ja"}).json()
    assert (ko["language"], en["language"], ja["language"]) == ("ko", "en", "ko")  # 모르는 언어는 한국어로
    assert ko["source"] == "odii" and ko["script_id"] != en["script_id"]


def test_missing_script_language():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    del data["places"][0]["scripts"]["en"]
    service = PlaceService(PlaceRepository(data), EmptyBookmarkReader())
    with pytest.raises(AppError) as error:
        service.get_script(1, lang="en")
    assert error.value.code == "SCRIPT_NOT_FOUND"


# ---------------------------------------------------------------- 17. 카테고리


def test_categories(env):
    body = env.client.get("/api/v1/categories").json()
    assert len(body["items"]) == 9
    assert set(body["items"][0]) == {"category_id", "name", "name_en", "description", "group"}
    assert env.client.get("/api/v1/categories", params={"group": "festival"}).json()["items"] == []


# ---------------------------------------------------------------- 32·33. 코스


def test_course_list(env):
    body = env.client.get("/api/v1/courses").json()
    assert body["total"] == 2
    assert [c["course_id"] for c in body["items"]] == [1, 2]
    assert all(c["place_count"] == 5 for c in body["items"])
    assert env.client.get("/api/v1/courses", params={"category_id": 7}).json()["total"] == 1  # 정동·시청은 B만


def test_course_detail_total_minutes(env):
    body = env.client.get("/api/v1/courses/1").json()
    places = body["places"]
    assert [p["order"] for p in places] == [1, 2, 3, 4, 5]
    assert [p["place_id"] for p in places] == [1, 2, 3, 4, 5]
    assert places[0]["walk_minutes_from_previous"] is None
    assert all(p["walk_minutes_from_previous"] >= 1 for p in places[1:])
    visit = sum(p["expected_visit_minutes"] for p in places)
    walk = sum(p["walk_minutes_from_previous"] for p in places[1:])
    assert body["total_minutes"] == visit + walk
    # 목록의 총 소요 시간과 상세의 값이 같아야 한다
    listed = env.client.get("/api/v1/courses").json()["items"][0]
    assert listed["total_minutes"] == body["total_minutes"]


def test_unknown_course_is_404(env):
    response = env.client.get("/api/v1/courses/99", headers={"Accept-Language": "en"})
    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "COURSE_NOT_FOUND", "message": "Course not found."}
