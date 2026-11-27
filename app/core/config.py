"""앱 전체 설정. 값은 환경변수나 프로젝트 폴더의 .env 파일에서 읽는다.

비밀값(Client Secret, JWT 비밀키)은 .env에만 두고 깃에 올리지 않는다.
어떤 값이 필요한지는 .env.example을 본다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google OAuth (Google Cloud Console의 웹 애플리케이션 클라이언트)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback"

    # JWT. 비어 있으면 서버를 켤 때마다 임시 비밀키를 만든다(재시작하면 로그인이 풀림).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    signup_token_minutes: int = 10

    # 로그인이 끝난 뒤 돌아갈 프론트 주소. 비어 있으면 콜백이 결과를 JSON으로 보여준다(개발용).
    frontend_url: str = ""
    # 처음 로그인한 사람이 갈 약관 동의 화면 주소. 비어 있으면 frontend_url을 쓴다.
    frontend_signup_url: str = ""

    # 쿠키에 Secure를 붙일지. HTTPS로 배포할 때 true로 바꾼다.
    cookie_secure: bool = False

    # 이 서버를 부를 수 있는 프론트 주소들. 쉼표로 구분 (예: http://127.0.0.1:5500)
    cors_origins: str = ""

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
