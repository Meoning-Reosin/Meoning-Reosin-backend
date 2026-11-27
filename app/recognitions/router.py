"""사진 인식 API 주소 (router 층).

router가 하는 일: 사진 파일과 위치를 받아 검사(용량, 빈 파일, 실제 이미지 형식) → service에게 인식 맡기기.
오류는 AppError로 던지면 app/core/errors.py가 {"detail": {"code", "message"}} 응답으로 바꿔 준다.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.errors import AppError
from app.recognitions import config, service
from app.recognitions import errors as _errors  # noqa: F401  오류 코드 등록
from app.recognitions.image_type import detect_image_type
from app.recognitions.schemas import RecognitionResponse

router = APIRouter(prefix="/api/v1/recognitions", tags=["recognitions"])


@router.post("", response_model=RecognitionResponse)
async def recognize(
    image: Annotated[UploadFile, File(description="촬영하거나 갤러리에서 고른 사진 1장")],
    lat: Annotated[float | None, Form(ge=-90, le=90, description="현재 위치 위도 (선택)")] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180, description="현재 위치 경도 (선택)")] = None,
):
    """사진 한 장으로 장소를 인식한다 (API 3).

    로그인 없이 사용할 수 있다. 인식에 실패해도 200으로 응답하고 status로 구분한다.
    """
    if (lat is None) != (lng is None):
        raise AppError("INVALID_LOCATION")

    # 최대 용량보다 1바이트만 더 읽어 보면, 큰 파일을 끝까지 읽지 않고도 "너무 크다"를 알 수 있다.
    data = await image.read(config.MAX_IMAGE_BYTES + 1)
    if len(data) > config.MAX_IMAGE_BYTES:
        raise AppError("IMAGE_TOO_LARGE")
    if not data:
        raise AppError("EMPTY_FILE")
    # Content-Type은 보내는 쪽이 바꿀 수 있으므로 믿지 않고 파일 앞부분으로 형식을 판단한다.
    if detect_image_type(data) is None:
        raise AppError("UNSUPPORTED_IMAGE_TYPE")

    # 모델 추론은 CPU를 오래 쓰므로 이벤트 루프를 막지 않도록 별도 스레드에서 실행
    return await run_in_threadpool(service.recognize, data, lat, lng)
