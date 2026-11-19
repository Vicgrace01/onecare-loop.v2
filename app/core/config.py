from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings. Production fails closed on unsafe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "OneCare Loop"
    app_version: str = "2.0.0"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "development-only-secret-change-before-deploy"
    signing_master_key: str | None = None
    pii_encryption_key: str | None = None
    database_url: str = "sqlite:///./onecare.db"
    access_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    self_registration_enabled: bool = True
    auto_create_schema: bool = True
    seed_demo_admin: bool = False
    demo_admin_email: str = "admin@onecareloop.com"
    demo_admin_password: str = ""
    demo_mode_enabled: bool = False
    demo_show_credentials: bool = False
    demo_pharmacy_email: str = "demo.pharmacy@onecareloop.com"
    demo_pharmacy_password: str = ""
    demo_hospital_email: str = "demo.hospital@onecareloop.com"
    demo_hospital_password: str = ""
    demo_clinician_email: str = "demo.clinician@onecareloop.com"
    demo_clinician_password: str = ""
    demo_hmo_email: str = "demo.hmo@onecareloop.com"
    demo_hmo_password: str = ""
    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if self.app_env.lower() == "production":
            if self.secret_key == "development-only-secret-change-before-deploy" or len(self.secret_key) < 32:
                raise ValueError("Production requires a unique SECRET_KEY of at least 32 characters")
            if not self.signing_master_key or len(self.signing_master_key) < 32:
                raise ValueError("Production requires a SIGNING_MASTER_KEY of at least 32 characters")
            if not self.pii_encryption_key or len(self.pii_encryption_key) < 32:
                raise ValueError("Production requires a separate PII_ENCRYPTION_KEY of at least 32 characters")
            if self.pii_encryption_key == self.signing_master_key:
                raise ValueError("PII_ENCRYPTION_KEY and SIGNING_MASTER_KEY must be different")
            if self.auto_create_schema:
                raise ValueError("AUTO_CREATE_SCHEMA must be false in production; use Alembic migrations")
            if self.seed_demo_admin:
                raise ValueError("SEED_DEMO_ADMIN must be false in production")
        if self.demo_show_credentials and not self.demo_mode_enabled:
            raise ValueError("DEMO_SHOW_CREDENTIALS requires DEMO_MODE_ENABLED=true")
        if self.demo_mode_enabled:
            demo_passwords = [
                self.demo_pharmacy_password, self.demo_hospital_password,
                self.demo_clinician_password, self.demo_hmo_password,
            ]
            if any(len(password) < 12 for password in demo_passwords):
                raise ValueError("Demo mode requires four unique demo passwords of at least 12 characters")
            if len(set(demo_passwords)) != len(demo_passwords):
                raise ValueError("Each demo role must have a different password")
        if self.access_token_ttl_seconds < 300:
            raise ValueError("Access token lifetime must be at least 300 seconds")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
