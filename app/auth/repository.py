"""회원 데이터 읽기·쓰기 (repository 층, 임시: 메모리).

DB가 준비되기 전까지 회원, 동의 기록, 리프레시 토큰을 메모리에 둔다.
서버를 다시 켜면 모두 사라진다. DB를 붙일 때는 이 파일의 UserRepository를 DB 버전으로 바꾸면 되고,
service와 router는 그대로 둔다 (users, user_consents, refresh_tokens 테이블).

이 층의 규칙: 저장하고 꺼내기만 한다. 가입 조건, 토큰 발급 같은 판단은 service.py가 한다.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

CONSENT_TYPES = ("terms", "privacy", "location", "camera", "photo_training")


@dataclass
class User:
    id: int  # 우리 서비스의 회원 번호
    provider: str  # 가입 경로. 지금은 "google"만 (네이버·이메일은 확장안)
    provider_user_id: str  # Google 계정 고유번호(sub). 이메일 대신 이 값으로 회원을 찾는다.
    email: str
    nickname: str  # 2~20자, 중복 허용
    profile_image_url: str | None  # 처음엔 Google 프로필 사진
    language: str  # "ko" 또는 "en"
    created_at: datetime
    consents: dict[str, bool] = field(default_factory=dict)  # CONSENT_TYPES별 동의 여부
    terms_version: str | None = None  # 동의한 약관 버전
    consents_updated_at: datetime | None = None


class UserRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[int, User] = {}
        self._next_id = 1
        # 리프레시 토큰 jti → (회원 번호, 만료 시각). 여기 없으면 폐기된 토큰이다.
        self._refresh_tokens: dict[str, tuple[int, datetime]] = {}

    def get(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def get_by_provider(self, provider: str, provider_user_id: str) -> User | None:
        for user in self._users.values():
            if user.provider == provider and user.provider_user_id == provider_user_id:
                return user
        return None

    def create(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str,
        nickname: str,
        profile_image_url: str | None,
        language: str,
        consents: dict[str, bool],
        terms_version: str,
    ) -> User:
        with self._lock:
            existing = self.get_by_provider(provider, provider_user_id)
            if existing:
                return existing
            now = datetime.now(UTC)
            user = User(
                id=self._next_id,
                provider=provider,
                provider_user_id=provider_user_id,
                email=email,
                nickname=nickname,
                profile_image_url=profile_image_url,
                language=language,
                created_at=now,
                consents=consents,
                terms_version=terms_version,
                consents_updated_at=now,
            )
            self._users[user.id] = user
            self._next_id += 1
            return user

    def update(self, user_id: int, **changes) -> User | None:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return None
            for key, value in changes.items():
                setattr(user, key, value)
            return user

    def update_consents(self, user_id: int, changes: dict[str, bool]) -> User | None:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return None
            user.consents = {**user.consents, **changes}
            user.consents_updated_at = datetime.now(UTC)
            return user

    def delete(self, user_id: int) -> None:
        """회원과 그 회원의 리프레시 토큰을 지운다.

        TODO: 일정, 찜, 공개 코스가 생기면 함께 지운다 (Q-33).
        """
        with self._lock:
            self._users.pop(user_id, None)
            for jti in [j for j, (uid, _) in self._refresh_tokens.items() if uid == user_id]:
                del self._refresh_tokens[jti]

    # --- 리프레시 토큰 ---
    def save_refresh_token(self, jti: str, user_id: int, expires_at: datetime) -> None:
        with self._lock:
            self._refresh_tokens[jti] = (user_id, expires_at)

    def is_refresh_token_active(self, jti: str, user_id: int) -> bool:
        record = self._refresh_tokens.get(jti)
        return record is not None and record[0] == user_id and record[1] > datetime.now(UTC)

    def revoke_refresh_token(self, jti: str) -> None:
        with self._lock:
            self._refresh_tokens.pop(jti, None)


_repository = UserRepository()


def get_user_repository() -> UserRepository:
    """서버 전체가 함께 쓰는 저장소 하나. 테스트에서는 dependency_overrides로 새것을 끼운다."""
    return _repository
