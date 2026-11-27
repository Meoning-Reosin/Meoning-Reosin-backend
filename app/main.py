"""앱 시작점.

여기서 하는 일
1. 공통 오류 처리 등록: 어느 기능에서든 AppError를 던지면 {"detail": {"code", "message"}}로 응답
2. CORS 설정: 다른 주소(프론트)에서 쿠키를 함께 보내며 API를 부를 수 있게 허용
3. 기능별 라우터(주소 묶음) 등록
4. 관광지 사진 파일 내보내기 (/api/v1/media/places/1.jpg)

새 기능을 만들면 그 폴더의 router를 아래에 include_router로 추가한다.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.auth.router import users_router
from app.bookmarks.router import router as bookmarks_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.itineraries.router import router as itineraries_router
from app.places.router import categories_router, courses_router, places_router
from app.recognitions.router import router as recognitions_router

app = FastAPI(title="워크크 API")

app.add_exception_handler(AppError, app_error_handler)

# 허용할 프론트 주소는 .env의 CORS_ORIGINS.
_origins = get_settings().cors_origin_list
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- 기능별 라우터 ---
app.include_router(auth_router)  # 회원: 로그인·토큰
app.include_router(users_router)  # 회원: 내 정보
app.include_router(recognitions_router)  # 사진 인식
app.include_router(places_router)  # 관광지
app.include_router(categories_router)  # 카테고리
app.include_router(courses_router)  # 추천 코스
app.include_router(bookmarks_router)  # 찜
app.include_router(itineraries_router)  # 여행 일정

# --- 관광지 사진 (임시) ---
# app/places/data/images/{장소 번호}.jpg 를 /api/v1/media/places/{장소 번호}.jpg 로 내보낸다.
# /api 아래에 두어서 프론트 개발 프록시와 배포 리버스 프록시 설정을 그대로 쓴다.
# TODO(인프라): Azure Blob Storage 가 생기면 사진을 그쪽에 올리고 places.json 의 주소만 Blob 주소로 바꾼다.
_PLACE_IMAGES = Path(__file__).parent / "places" / "data" / "images"
app.mount("/api/v1/media/places", StaticFiles(directory=_PLACE_IMAGES), name="place-images")


@app.get("/health")
def health():
    return {"status": "ok"}
