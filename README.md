# Meoning-Reosion-backend

Python 3.12를 사용합니다. 저장소를 클론한 뒤 프로젝트 폴더에서 실행합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

- 서버 상태 확인은 http://127.0.0.1:8000/health 에서 합니다. `{"status":"ok"}`가 나오면 성공입니다.
- API 문서는 http://127.0.0.1:8000/docs 에서 확인할 수 있습니다.

## 테스트

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```
