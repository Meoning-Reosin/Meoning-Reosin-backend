from typing import Annotated

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.recognitions import config, service
from app.recognitions.errors import recognition_error, resolve_language
from app.recognitions.image_type import detect_image_type
from app.recognitions.schemas import RecognitionResponse

router = APIRouter(prefix="/api/v1/recognitions", tags=["recognitions"])


@router.post("", response_model=RecognitionResponse)
async def recognize(
    image: Annotated[UploadFile, File(description="촬영하거나 갤러리에서 고른 사진 1장")],
    lat: Annotated[float | None, Form(ge=-90, le=90, description="현재 위치 위도 (선택)")] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180, description="현재 위치 경도 (선택)")] = None,
    accept_language: Annotated[str | None, Header()] = None,
):
    """사진 한 장으로 장소를 인식한다.

    로그인 없이 사용할 수 있다. 인식에 실패해도 200으로 응답하고 status로 구분한다.
    """
    lang = resolve_language(accept_language)

    if (lat is None) != (lng is None):
        raise recognition_error("INVALID_LOCATION", lang)

    data = await image.read(config.MAX_IMAGE_BYTES + 1)
    if len(data) > config.MAX_IMAGE_BYTES:
        raise recognition_error("IMAGE_TOO_LARGE", lang)
    if not data:
        raise recognition_error("EMPTY_FILE", lang)
    if detect_image_type(data) is None:
        raise recognition_error("UNSUPPORTED_IMAGE_TYPE", lang)

    # 모델 추론은 CPU를 오래 쓰므로 이벤트 루프를 막지 않도록 별도 스레드에서 실행
    return await run_in_threadpool(service.recognize, data, lat, lng)
