from enum import Enum

from pydantic import BaseModel, Field


class RecognitionStatus(str, Enum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"


class RecognitionResponse(BaseModel):
    status: RecognitionStatus
    place_id: int | None = Field(None, description="인식된 장소 ID (실패 시 null)")
    confidence: float = Field(..., ge=0, le=1, description="예측 확신도 (0~1)")
