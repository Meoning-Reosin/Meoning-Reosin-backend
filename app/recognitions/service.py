"""사진 인식 업무 규칙 (service 층).

client가 돌려준 예측의 확신도가 기준(CONFIDENCE_THRESHOLD) 이상이면 "인식 성공",
아니면 "인식 실패"로 판단한다. 실패해도 오류가 아니라 200 응답이다 (명세서 3번).
TODO: 인식 기록(recognition_logs) 저장, 실패 시 후보(candidates) 3곳.
"""

from app.recognitions import client, config
from app.recognitions.schemas import RecognitionResponse, RecognitionStatus


def recognize(image: bytes, lat: float | None = None, lng: float | None = None) -> RecognitionResponse:
    prediction = client.predict(image, lat, lng)
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
