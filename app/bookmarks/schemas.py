"""찜 API의 요청·응답 모양 (명세서 20, 21, 22번)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.places.schemas import PlaceCard


# --- 20. 찜 목록 ---
class BookmarkListResponse(BaseModel):
    items: list[PlaceCard]  # 관광지 목록(11번)과 같은 장소 카드. 최근에 찜한 것부터
    page: int
    size: int
    total: int


# --- 21. 찜하기 ---
class BookmarkCreateRequest(BaseModel):
    place_id: int = Field(description="찜할 장소 ID", examples=[2])


class BookmarkResponse(BaseModel):
    place_id: int
    bookmark_count: int  # 바뀐 찜 수 (화면의 숫자를 바로 고칠 수 있게)
    created_at: datetime  # 처음 찜한 시각
