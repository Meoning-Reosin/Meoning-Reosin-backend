"""찜 API 주소 (router 층). 모두 로그인 필수 (CurrentUser).

20. GET    /api/v1/bookmarks             내 찜 목록
21. POST   /api/v1/bookmarks             찜하기 (새로 찜하면 201, 이미 찜했으면 200)
22. DELETE /api/v1/bookmarks/{place_id}  찜 해제 (204)

나중에 공개 코스 찜 목록(57번 GET /api/v1/bookmarks/courses)을 이 파일에 추가한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse

from app.bookmarks import schemas
from app.bookmarks.repository import BookmarkRepository, get_bookmark_repository
from app.bookmarks.service import BookmarkService
from app.core.deps import CurrentUser
from app.core.errors import get_language
from app.places.router import get_place_service
from app.places.service import PlaceService

router = APIRouter(prefix="/api/v1/bookmarks", tags=["찜"])


def get_bookmark_service(
    repo: Annotated[BookmarkRepository, Depends(get_bookmark_repository)],
    places: Annotated[PlaceService, Depends(get_place_service)],
) -> BookmarkService:
    return BookmarkService(repo, places)


Service = Annotated[BookmarkService, Depends(get_bookmark_service)]
Lang = Annotated[str, Depends(get_language)]


@router.get("", response_model=schemas.BookmarkListResponse)
def list_bookmarks(
    user: CurrentUser,
    service: Service,
    lang: Lang,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """내 찜 목록 (API 20). 관광지 카드 모양, 최근에 찜한 것부터."""
    return service.list_bookmarks(user.id, lang=lang, page=page, size=size)


@router.post(
    "",
    response_model=schemas.BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": schemas.BookmarkResponse, "description": "이미 찜한 장소"}},
)
def add_bookmark(body: schemas.BookmarkCreateRequest, user: CurrentUser, service: Service):
    """찜하기 (API 21). 새로 찜하면 201, 이미 찜했으면 같은 내용을 200으로 돌려준다."""
    result, created = service.add(user.id, body.place_id)
    if created:
        return result  # 기본 상태 코드 201
    return JSONResponse(result.model_dump(mode="json"), status_code=status.HTTP_200_OK)


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bookmark(place_id: int, user: CurrentUser, service: Service):
    """찜 해제 (API 22). 찜하지 않았던 장소여도 204."""
    service.remove(user.id, place_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
