"""찜 API 테스트.

테스트마다 회원 저장소와 찜 저장소를 새로 만들어 끼운다(dependency_overrides).
관광지 데이터는 진짜 파일(app/places/data/places.json)을 쓴다.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth.repository import UserRepository, get_user_repository
from app.bookmarks.repository import BookmarkRepository, get_bookmark_repository
from app.core.config import Settings, get_settings
from app.core.security import ACCESS_COOKIE, create_token
from app.main import app

URL = "/api/v1/bookmarks"


@pytest.fixture
def env():
    settings = Settings(_env_file=None, jwt_secret="test-jwt-secret-that-is-long-enough-1234")
    users = UserRepository()
    bookmarks = BookmarkRepository()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_bookmark_repository] = lambda: bookmarks
    yield SimpleNamespace(settings=settings, users=users, bookmarks=bookmarks)
    app.dependency_overrides.clear()


def logged_in_client(env, sub: str = "sub-1") -> tuple[TestClient, int]:
    """회원을 만들고 로그인 쿠키를 넣은 클라이언트를 돌려준다."""
    user = env.users.create(
        provider="google",
        provider_user_id=sub,
        email=f"{sub}@example.com",
        nickname="테스터",
        profile_image_url=None,
        language="ko",
        consents={"terms": True, "privacy": True},
        terms_version="2026-11-27",
    )
    token, _ = create_token(env.settings, "access", str(user.id), timedelta(minutes=5))
    client = TestClient(app)
    client.cookies.set(ACCESS_COOKIE, token)
    return client, user.id


def test_login_required(env):
    client = TestClient(app)
    for response in [client.get(URL), client.post(URL, json={"place_id": 1}), client.delete(f"{URL}/1")]:
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "NOT_AUTHENTICATED"


def test_add_then_add_again(env):
    client, _ = logged_in_client(env)
    first = client.post(URL, json={"place_id": 2})
    assert first.status_code == 201
    assert first.json()["place_id"] == 2 and first.json()["bookmark_count"] == 1
    again = client.post(URL, json={"place_id": 2})
    assert again.status_code == 200  # 이미 찜함
    assert again.json() == first.json()  # 찜 수도, 처음 찜한 시각도 그대로


def test_cannot_bookmark_unknown_place(env):
    client, _ = logged_in_client(env)
    response = client.post(URL, json={"place_id": 999})
    assert response.status_code == 404 and response.json()["detail"]["code"] == "PLACE_NOT_FOUND"
    assert client.delete(f"{URL}/999").status_code == 404


def test_list_is_newest_first_and_uses_place_cards(env):
    client, _ = logged_in_client(env)
    for place_id in [3, 1, 8]:
        client.post(URL, json={"place_id": place_id})
    body = client.get(URL, headers={"Accept-Language": "en"}).json()
    assert [i["place_id"] for i in body["items"]] == [8, 1, 3]
    assert body["total"] == 3 and body["page"] == 1 and body["size"] == 20
    card = body["items"][0]
    assert card["name"] == "Dilkusha" and card["is_bookmarked"] is True and card["bookmark_count"] == 1


def test_list_paging(env):
    client, _ = logged_in_client(env)
    for place_id in range(1, 6):
        client.post(URL, json={"place_id": place_id})
    body = client.get(URL, params={"size": 2, "page": 3}).json()
    assert body["total"] == 5 and [i["place_id"] for i in body["items"]] == [1]


def test_remove_is_idempotent(env):
    client, _ = logged_in_client(env)
    client.post(URL, json={"place_id": 4})
    assert client.delete(f"{URL}/4").status_code == 204
    assert client.delete(f"{URL}/4").status_code == 204  # 이미 풀었어도 204
    assert client.get(URL).json()["total"] == 0


def test_bookmarks_are_per_user(env):
    alice, _ = logged_in_client(env, "alice")
    bob, _ = logged_in_client(env, "bob")
    alice.post(URL, json={"place_id": 5})
    assert bob.get(URL).json()["items"] == []


def test_counts_show_up_in_places(env):
    """관광지 목록의 찜 수, 찜순 정렬, 내가 찜했는지가 진짜 찜으로 움직인다."""
    alice, _ = logged_in_client(env, "alice")
    bob, _ = logged_in_client(env, "bob")
    alice.post(URL, json={"place_id": 9})
    bob.post(URL, json={"place_id": 9})
    bob.post(URL, json={"place_id": 6})

    items = alice.get("/api/v1/places").json()["items"]  # 기본 정렬: 찜 많은 순
    assert [(i["place_id"], i["bookmark_count"]) for i in items[:2]] == [(9, 2), (6, 1)]
    assert items[0]["is_bookmarked"] is True and items[1]["is_bookmarked"] is False

    detail = TestClient(app).get("/api/v1/places/9").json()  # 비회원
    assert detail["bookmark_count"] == 2 and detail["is_bookmarked"] is False


def test_account_deletion_removes_bookmarks(env):
    client, user_id = logged_in_client(env)
    client.post(URL, json={"place_id": 1})
    assert client.delete("/api/v1/users/me").status_code == 204
    assert env.bookmarks.list_place_ids(user_id) == []
    assert env.bookmarks.count(1) == 0
