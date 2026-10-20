from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "gcs"
    jwt_audience: str = "gcs-dashboard"
    token_minutes: int = Field(default=15, ge=1, le=60)
    opa_url: str = "http://opa:8181"
    allowed_origins: str = "http://localhost:8080"

    @field_validator("jwt_secret")
    @classmethod
    def reject_placeholder(cls, value):
        if "CHANGE_ME" in value:
            raise ValueError("Generate a real JWT secret")
        return value


settings = Settings()
