from fastapi import FastAPI

from app.recognitions.router import router as recognitions_router

app = FastAPI(title="서울 스토리워크 API")
app.include_router(recognitions_router)


@app.get("/health")
def health():
    return {"status": "ok"}
