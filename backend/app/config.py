from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./pos.db"
    jwt_secret: str = "development-only-change-this-secret-before-deployment"
    jwt_issuer: str = "pos-app"
    jwt_audience: str = "pos-api"
    access_minutes: int = 15
    refresh_hours: int = 8
    environment: str = "development"

settings = Settings()
if settings.environment == "production" and (
    len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("development-only")
    or settings.jwt_secret.startswith("replace-with")
):
    raise RuntimeError("Set a random JWT_SECRET of at least 32 characters")
