"""사진 인식 외부 연동 (client 층).

여기는 "사진을 주면 어느 장소인지 예측해 주는" 바깥 서비스와 이야기하는 곳이다.
확정안(Q-27 A안): Azure AI Vision으로 사진을 벡터(임베딩)로 바꾸고,
DB(pgvector)에 저장해 둔 장소 사진 벡터와 비교해 가장 비슷한 장소를 고른다.

지금은 키가 없어서 고정된 결과를 돌려주는 임시 구현이다.
Azure 키가 오면 이 파일의 predict만 채우면 되고, service와 router는 그대로 둔다.
"""

from dataclasses import dataclass


@dataclass
class Prediction:
    place_id: int
    confidence: float  # 0~1


def predict(image: bytes, lat: float | None = None, lng: float | None = None) -> Prediction:
    """이미지에서 장소를 예측한다. 위치가 있으면 주변 장소로 후보를 좁히는 데 쓴다.

    TODO(Azure AI Vision): 1) 사진 → 벡터  2) pgvector로 가장 가까운 장소 사진 찾기
                           3) 거리 → 확신도로 바꾸기
    """
    return Prediction(place_id=1, confidence=0.9)
