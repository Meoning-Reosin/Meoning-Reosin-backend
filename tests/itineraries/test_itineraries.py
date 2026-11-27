"""여행 일정 API 테스트 (명세서 23~31번).

테스트마다 회원·찜·일정 저장소를 새로 만들어 끼운다. 관광지·코스는 진짜 데이터 파일을 쓴다.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth.repository import UserRepository, get_user_repository
from app.bookmarks.repository import BookmarkRepository, get_bookmark_repository
from app.core.config import Settings, get_settings
from app.core.security import ACCESS_COOKIE, create_token
from app.itineraries.repository import ItineraryRepository, get_itinerary_repository
from app.main import app

URL = "/api/v1/itineraries"


@pytest.fixture
def env():
    settings = Settings(_env_file=None, jwt_secret="test-jwt-secret-that-is-long-enough-1234")
    users, itineraries = UserRepository(), ItineraryRepository()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_bookmark_repository] = BookmarkRepository
    app.dependency_overrides[get_itinerary_repository] = lambda: itineraries
    yield SimpleNamespace(settings=settings, users=users, itineraries=itineraries)
    app.dependency_overrides.clear()


def client_for(env, sub: str = "alice") -> TestClient:
    """회원을 만들고 로그인 쿠키를 넣은 클라이언트."""
    user = env.users.create(
        provider="google",
        provider_user_id=sub,
        email=f"{sub}@example.com",
        nickname=sub,
        profile_image_url=None,
        language="ko",
        consents={"terms": True, "privacy": True},
        terms_version="2026-11-27",
    )
    token, _ = create_token(env.settings, "access", str(user.id), timedelta(minutes=5))
    client = TestClient(app)
    client.cookies.set(ACCESS_COOKIE, token)
    client.user_id = user.id
    return client


def new_itinerary(client: TestClient, title: str = "정동 산책", place_ids=()) -> int:
    itinerary_id = client.post(URL, json={"title": title}).json()["itinerary_id"]
    for place_id in place_ids:
        assert client.post(f"{URL}/items", json={"itinerary_id": itinerary_id, "place_id": place_id}).status_code == 201
    return itinerary_id


def order_of(detail: dict) -> list[int]:
    return [item["place"]["place_id"] for item in detail["items"]]


# ---------------------------------------------------------------- 로그인·권한


def test_login_required(env):
    client = TestClient(app)
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"title": "x"}).status_code == 401


def test_other_users_itinerary_is_forbidden(env):
    alice, bob = client_for(env, "alice"), client_for(env, "bob")
    itinerary_id = new_itinerary(alice, place_ids=[1])
    for response in [
        bob.get(f"{URL}/{itinerary_id}"),
        bob.patch(f"{URL}/{itinerary_id}", json={"title": "x"}),
        bob.delete(f"{URL}/{itinerary_id}"),
        bob.post(f"{URL}/items", json={"itinerary_id": itinerary_id, "place_id": 2}),
    ]:
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "FORBIDDEN"
    assert bob.get(URL).json()["total"] == 0  # 목록에도 안 보임


def test_unknown_itinerary_is_404(env):
    client = client_for(env)
    response = client.get(f"{URL}/999", headers={"Accept-Language": "en"})
    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "ITINERARY_NOT_FOUND", "message": "Itinerary not found."}


# ---------------------------------------------------------------- 24~27


def test_create_and_view(env):
    client = client_for(env)
    response = client.post(URL, json={"title": "  덕수궁 산책 ", "travel_date": "2026-11-29"})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "덕수궁 산책" and body["travel_date"] == "2026-11-29"
    assert body["items"] == [] and body["total_minutes"] == 0
    assert body["my_role"] == "owner" and body["member_count"] == 1 and body["is_public"] is False
    assert client.get(f"{URL}/{body['itinerary_id']}").json()["title"] == "덕수궁 산책"


@pytest.mark.parametrize("title", ["", "   ", "가" * 51])
def test_title_is_validated(env, title):
    assert client_for(env).post(URL, json={"title": title}).status_code == 422


def test_update_only_sent_fields(env):
    client = client_for(env)
    itinerary_id = client.post(URL, json={"title": "처음", "travel_date": "2026-12-01"}).json()["itinerary_id"]

    body = client.patch(f"{URL}/{itinerary_id}", json={"title": "바꾼 이름"}).json()
    assert body["title"] == "바꾼 이름" and body["travel_date"] == "2026-12-01"  # 날짜는 그대로

    body = client.patch(f"{URL}/{itinerary_id}", json={"travel_date": None}).json()
    assert body["title"] == "바꾼 이름" and body["travel_date"] is None  # null을 보내면 날짜 지우기


def test_delete_itinerary(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1, 2])
    assert client.delete(f"{URL}/{itinerary_id}").status_code == 204
    assert client.get(f"{URL}/{itinerary_id}").status_code == 404


# ---------------------------------------------------------------- 23. 목록


def test_list_newest_first_with_contains_place(env):
    client = client_for(env)
    first = new_itinerary(client, "첫 일정", place_ids=[1])
    second = new_itinerary(client, "둘째 일정")

    body = client.get(URL).json()
    assert [i["itinerary_id"] for i in body["items"]] == [second, first]
    assert all(i["contains_place"] is None for i in body["items"])  # place_id를 안 보내면 null

    marked = {i["itinerary_id"]: i["contains_place"] for i in client.get(URL, params={"place_id": 1}).json()["items"]}
    assert marked == {first: True, second: False}

    # 첫 일정에 장소를 담으면 "최근에 바뀐 일정"이 되어 맨 위로 올라온다
    client.post(f"{URL}/items", json={"itinerary_id": first, "place_id": 2})
    assert client.get(URL).json()["items"][0]["itinerary_id"] == first


# ---------------------------------------------------------------- 28. 장소 담기


def test_add_place_appends_and_rejects_duplicates(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1])
    response = client.post(f"{URL}/items", json={"itinerary_id": itinerary_id, "place_id": 2, "memo": "오전"})
    assert response.status_code == 201
    assert response.json()["visit_order"] == 2

    again = client.post(f"{URL}/items", json={"itinerary_id": itinerary_id, "place_id": 2})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "PLACE_ALREADY_IN_ITINERARY"

    unknown = client.post(f"{URL}/items", json={"itinerary_id": itinerary_id, "place_id": 999})
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "PLACE_NOT_FOUND"


def test_detail_calculates_walk_and_totals(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[6, 7, 10])
    body = client.get(f"{URL}/{itinerary_id}", params={"lat": 37.5684, "lng": 126.9713}).json()
    items = body["items"]
    assert [i["visit_order"] for i in items] == [1, 2, 3]
    assert items[0]["walk_minutes_from_previous"] is None and items[0]["distance_m_from_previous"] is None
    assert all(i["walk_minutes_from_previous"] >= 1 for i in items[1:])
    assert items[0]["place"]["distance_m"] == 0  # 현재 위치 = 1번 장소 위치
    assert body["total_visit_minutes"] == sum(i["place"]["expected_visit_minutes"] for i in items)
    assert body["total_walk_minutes"] == sum(i["walk_minutes_from_previous"] for i in items[1:])
    assert body["total_minutes"] == body["total_visit_minutes"] + body["total_walk_minutes"]


def test_lat_without_lng_is_rejected(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client)
    response = client.get(f"{URL}/{itinerary_id}", params={"lat": 37.5})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "INVALID_LOCATION"


# ---------------------------------------------------------------- 29. 순서·메모·방문 체크


def item_ids(client, itinerary_id) -> list[int]:
    return [i["item_id"] for i in client.get(f"{URL}/{itinerary_id}").json()["items"]]


def test_move_item_shifts_others(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1, 2, 3, 4])
    ids = item_ids(client, itinerary_id)

    body = client.patch(f"{URL}/{itinerary_id}/items/{ids[3]}", json={"visit_order": 1}).json()
    assert order_of(body) == [4, 1, 2, 3]

    body = client.patch(f"{URL}/{itinerary_id}/items/{ids[3]}", json={"visit_order": 99}).json()
    assert order_of(body) == [1, 2, 3, 4]  # 마지막보다 크면 맨 뒤로

    assert client.patch(f"{URL}/{itinerary_id}/items/{ids[0]}", json={"visit_order": 0}).status_code == 422


def test_memo_and_visit_check(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1, 2])
    first = item_ids(client, itinerary_id)[0]

    body = client.patch(f"{URL}/{itinerary_id}/items/{first}", json={"memo": "사진 찍기", "visited": True}).json()
    item = body["items"][0]
    assert item["memo"] == "사진 찍기" and item["visited"] is True and item["visited_at"] is not None
    assert body["visited_count"] == 1
    checked_at = item["visited_at"]

    # 다시 true를 보내도 처음 체크한 시각은 그대로, 메모도 안 보냈으니 그대로
    item = client.patch(f"{URL}/{itinerary_id}/items/{first}", json={"visited": True}).json()["items"][0]
    assert item["visited_at"] == checked_at and item["memo"] == "사진 찍기"

    item = client.patch(f"{URL}/{itinerary_id}/items/{first}", json={"visited": False, "memo": None}).json()["items"][0]
    assert item["visited"] is False and item["visited_at"] is None and item["memo"] is None


def test_unknown_item_is_404(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1])
    response = client.patch(f"{URL}/{itinerary_id}/items/999", json={"memo": "x"})
    assert response.status_code == 404 and response.json()["detail"]["code"] == "ITEM_NOT_FOUND"
    assert client.delete(f"{URL}/{itinerary_id}/items/999").status_code == 404


# ---------------------------------------------------------------- 30. 빼기


def test_remove_item_pulls_others_forward(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[1, 2, 3])
    second = item_ids(client, itinerary_id)[1]
    assert client.delete(f"{URL}/{itinerary_id}/items/{second}").status_code == 204
    body = client.get(f"{URL}/{itinerary_id}").json()
    assert order_of(body) == [1, 3] and [i["visit_order"] for i in body["items"]] == [1, 2]


# ---------------------------------------------------------------- 31. 코스 담기


def test_add_course_skips_existing_places(env):
    client = client_for(env)
    itinerary_id = new_itinerary(client, place_ids=[2, 4])  # 코스 A(1~5) 중 두 곳이 이미 있음
    response = client.post(f"{URL}/courses", json={"course_id": 1, "itinerary_id": itinerary_id})
    assert response.status_code == 201
    assert response.json() == {"itinerary_id": itinerary_id, "added_count": 3, "skipped_count": 2}
    assert order_of(client.get(f"{URL}/{itinerary_id}").json()) == [2, 4, 1, 3, 5]


def test_add_course_without_itinerary_creates_one(env):
    client = client_for(env)
    body = client.post(f"{URL}/courses", json={"course_id": 2}).json()
    assert body["added_count"] == 5 and body["skipped_count"] == 0
    detail = client.get(f"{URL}/{body['itinerary_id']}").json()
    assert detail["title"] == "서울에 남은 외국인의 집과 흔적"
    assert order_of(detail) == [6, 7, 8, 9, 10]


def test_add_unknown_course(env):
    response = client_for(env).post(f"{URL}/courses", json={"course_id": 99})
    assert response.status_code == 404 and response.json()["detail"]["code"] == "COURSE_NOT_FOUND"


# ---------------------------------------------------------------- 탈퇴


def test_account_deletion_removes_itineraries(env):
    client = client_for(env)
    new_itinerary(client, place_ids=[1])
    assert client.delete("/api/v1/users/me").status_code == 204
    assert env.itineraries.list_owned(client.user_id) == []
