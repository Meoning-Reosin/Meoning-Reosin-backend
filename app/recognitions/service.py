from dataclasses import dataclass

from app.recognitions import config
from app.recognitions.schemas import RecognitionResponse, RecognitionStatus


@dataclass
class Prediction:
    place_id: int
    confidence: float


def predict(image: bytes, lat: float | None = None, lng: float | None = None) -> Prediction:
    """이미지에서 장소를 예측한다. 위치가 있으면 주변 장소로 후보를 좁히는 데 쓴다.

    TODO: 실제 AI 모델 연동. 지금은 고정된 결과를 돌려주는 임시 구현.
    """
    return Prediction(place_id=1, confidence=0.9)


def recognize(image: bytes, lat: float | None = None, lng: float | None = None) -> RecognitionResponse:
    prediction = predict(image, lat, lng)
    if prediction.confidence < config.CONFIDENCE_THRESHOLD:
        return RecognitionResponse(
            status=RecognitionStatus.NOT_MATCHED,
            place_id=None,
            confidence=prediction.confidence,
        )
    return RecognitionResponse(
        status=RecognitionStatus.MATCHED,
        place_id=prediction.place_id,
        confidence=prediction.confidence,
    )
