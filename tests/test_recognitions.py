import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recognitions import config, service
from app.recognitions.errors import resolve_language
from app.recognitions.image_type import detect_image_type

client = TestClient(app)
URL = "/api/v1/recognitions"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
PDF = b"%PDF-1.7\n" + b"\x00" * 16


def upload(content: bytes = JPEG, content_type: str = "image/jpeg", data=None, headers=None):
    return client.post(
        URL,
        files={"image": ("photo.jpg", content, content_type)},
        data=data,
        headers=headers,
    )


@pytest.mark.parametrize(
    ("data", "expected"),
    [(JPEG, "jpeg"), (PNG, "png"), (WEBP, "webp"), (HEIC, "heic"), (PDF, None), (b"RIFF", None)],
)
def test_detect_image_type(data, expected):
    assert detect_image_type(data) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, "ko"), ("en-US,en;q=0.9", "en"), ("ko-KR", "ko"), ("ja", "ko"), ("EN", "en")],
)
def test_resolve_language(header, expected):
    assert resolve_language(header) == expected


def test_matched():
    res = upload()
    assert res.status_code == 200
    assert res.json() == {"status": "matched", "place_id": 1, "confidence": 0.9}


def test_not_matched_when_low_confidence(monkeypatch):
    monkeypatch.setattr(service, "predict", lambda image, lat, lng: service.Prediction(3, 0.2))
    res = upload()
    assert res.status_code == 200
    assert res.json() == {"status": "not_matched", "place_id": None, "confidence": 0.2}


def test_threshold_is_configurable(monkeypatch):
    monkeypatch.setattr(config, "CONFIDENCE_THRESHOLD", 0.95)
    res = upload()
    assert res.json()["status"] == "not_matched"


def test_location_is_passed_to_predict(monkeypatch):
    received = {}

    def fake_predict(image, lat, lng):
        received.update(lat=lat, lng=lng)
        return service.Prediction(1, 0.9)

    monkeypatch.setattr(service, "predict", fake_predict)
    res = upload(data={"lat": "37.5658", "lng": "126.9751"})
    assert res.status_code == 200
    assert received == {"lat": 37.5658, "lng": 126.9751}


def test_rejects_only_one_coordinate():
    res = upload(data={"lat": "37.5"})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INVALID_LOCATION"


def test_rejects_out_of_range_coordinate():
    res = upload(data={"lat": "91", "lng": "126.9"})
    assert res.status_code == 422


def test_accepts_image_with_generic_content_type():
    # 일부 클라이언트는 application/octet-stream으로 보낸다. 실제 바이트가 이미지면 통과.
    res = upload(content=PNG, content_type="application/octet-stream")
    assert res.status_code == 200


def test_rejects_non_image_disguised_as_jpeg():
    res = upload(content=PDF, content_type="image/jpeg")
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "UNSUPPORTED_IMAGE_TYPE"


def test_rejects_too_large(monkeypatch):
    monkeypatch.setattr(config, "MAX_IMAGE_BYTES", 10)
    res = upload(content=JPEG)
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "IMAGE_TOO_LARGE"


def test_rejects_empty_file():
    res = upload(content=b"")
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "EMPTY_FILE"


def test_error_message_follows_accept_language():
    ko = upload(content=b"").json()["detail"]["message"]
    en = upload(content=b"", headers={"Accept-Language": "en"}).json()["detail"]["message"]
    assert ko == "빈 파일입니다."
    assert en == "The file is empty."


def test_requires_image():
    res = client.post(URL)
    assert res.status_code == 422
