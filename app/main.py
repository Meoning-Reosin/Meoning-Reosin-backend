from fastapi import FastAPI

app = FastAPI(title="서울 스토리워크 API")

@app.get("/health")
def health():
    return {"status": "ok"}