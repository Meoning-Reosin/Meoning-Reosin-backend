from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["ko", "en"]


class UserResponse(BaseModel):
    id: int
    email: str
    nickname: str
    profile_image_url: str | None
    language: Language
    provider: str
    created_at: datetime


class ConsentsResponse(BaseModel):
    terms: bool = Field(description="이용약관 동의 (필수)")
    privacy: bool = Field(description="개인정보 수집·이용 동의 (필수)")
    location: bool = Field(description="위치 정보 이용 (선택)")
    camera: bool = Field(description="카메라·사진 접근 (선택)")
    photo_training: bool = Field(description="업로드 사진을 인식 개선에 활용 (선택)")
    terms_version: str | None
    updated_at: datetime | None


class GoogleCallbackResponse(BaseModel):
    """프론트 주소가 설정되지 않았을 때(개발용) 콜백이 돌려주는 결과."""

    status: Literal["logged_in", "signup_required"]
    email: str
    name: str
    user: UserResponse | None = None


class SignupRequest(BaseModel):
    agree_terms: bool = Field(description="이용약관 동의 (필수, true여야 함)")
    agree_privacy: bool = Field(description="개인정보 수집·이용 동의 (필수, true여야 함)")
    terms_version: str = Field("2026-11-27", max_length=20, description="동의한 약관 버전")
    agree_location: bool = False
    agree_camera: bool = False
    agree_photo_training: bool = False
    nickname: str | None = Field(None, min_length=2, max_length=20, description="비우면 Google 이름")
    language: Language = "ko"


class UpdateMeRequest(BaseModel):
    nickname: str | None = Field(None, min_length=2, max_length=20)
    language: Language | None = None


class UpdateConsentsRequest(BaseModel):
    location: bool | None = None
    camera: bool | None = None
    photo_training: bool | None = None


class RefreshResponse(BaseModel):
    expires_in: int = Field(description="새 액세스 토큰의 남은 시간(초)")
