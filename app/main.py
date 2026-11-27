from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.auth.router import users_router
from app.core.config import get_settings
from app.recognitions.router import router as recognitions_router

app = FastAPI(title="서울 스토리워크 API")

# 프론트(다른 포트)에서 쿠키를 함께 보내며 API를 부를 수 있게 허용한다. 허용할 주소는 .env의 CORS_ORIGINS.
_origins = get_settings().cors_origin_list
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(recognitions_router)


@app.get("/health")
def health():
    return {"status": "ok"}
