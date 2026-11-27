"""모든 기능이 함께 쓰는 오류 처리와 언어 고르기.

오류 응답 모양 (모든 API 공통):
    {"detail": {"code": "PLACE_NOT_FOUND", "message": "없는 장소입니다."}}
프론트는 code로 분기하고, message는 화면에 그대로 보여줘도 된다.

쓰는 방법
1. 기능 폴더의 errors.py에 오류 표를 만들고 register_errors()로 등록한다.
       register_errors({"PLACE_NOT_FOUND": (404, {"ko": "...", "en": "..."})})
2. service나 router에서 raise AppError("PLACE_NOT_FOUND").
3. main.py에 등록한 app_error_handler가 Accept-Language를 보고 그 언어의 메시지로 응답한다.

덕분에 service는 HTTP를 몰라도 되고, router마다 언어를 넘겨 줄 필요도 없다.
"""

from typing import Annotated

from fastapi import Header, Request, status
from fastapi.responses import JSONResponse

SUPPORTED_LANGUAGES = ("ko", "en")
DEFAULT_LANGUAGE = "ko"

# 오류 코드 → (HTTP 상태 코드, {언어: 메시지})
_REGISTRY: dict[str, tuple[int, dict[str, str]]] = {}


def register_errors(errors: dict[str, tuple[int, dict[str, str]]]) -> None:
    """기능별 오류 표를 등록한다. 같은 코드를 다른 뜻으로 두 번 등록하면 실수이므로 막는다."""
    for code, value in errors.items():
        if code in _REGISTRY and _REGISTRY[code] != value:
            raise ValueError(f"오류 코드 {code}가 서로 다르게 두 번 등록됐습니다.")
        _REGISTRY[code] = value


# 여러 기능에서 함께 쓰는 오류
register_errors(
    {
        "INVALID_LOCATION": (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"ko": "위치는 위도와 경도를 함께 보내야 합니다.", "en": "Latitude and longitude must be sent together."},
        ),
    }
)


class AppError(Exception):
    """우리 서비스의 오류. code는 register_errors로 등록한 코드여야 한다."""

    def __init__(self, code: str) -> None:
        if code not in _REGISTRY:
            raise KeyError(f"등록되지 않은 오류 코드: {code}")
        super().__init__(code)
        self.code = code

    @property
    def status_code(self) -> int:
        return _REGISTRY[self.code][0]

    def message(self, lang: str) -> str:
        messages = _REGISTRY[self.code][1]
        return messages.get(lang) or messages[DEFAULT_LANGUAGE]


def resolve_language(accept_language: str | None) -> str:
    """Accept-Language 헤더(예: "en-US,en;q=0.9")에서 지원하는 첫 언어를 고른다. 없으면 ko."""
    if accept_language:
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower().split("-")[0]
            if code in SUPPORTED_LANGUAGES:
                return code
    return DEFAULT_LANGUAGE


def get_language(accept_language: Annotated[str | None, Header()] = None) -> str:
    """라우터 인자로 받아 쓰는 의존성: 응답 언어 "ko" 또는 "en"."""
    return resolve_language(accept_language)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """AppError를 {"detail": {"code", "message"}} 응답으로 바꾼다 (main.py에서 등록)."""
    return error_response(exc, resolve_language(request.headers.get("accept-language")))


def error_response(exc: AppError, lang: str) -> JSONResponse:
    """오류 응답을 직접 만든다. 오류 응답에 쿠키를 더 붙여야 할 때처럼 handler를 거치지 않을 때 쓴다."""
    headers = None
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # 401에는 "어떤 방식으로 로그인해야 하는지"를 알려주는 헤더를 붙이는 것이 HTTP 규칙이다.
        headers = {"WWW-Authenticate": "Bearer"}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message(lang)}},
        headers=headers,
    )
