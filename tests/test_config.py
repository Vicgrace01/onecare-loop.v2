import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_development_secrets():
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_requires_external_migration_and_no_demo_seed():
    shared = {
        "app_env": "production",
        "secret_key": "production-secret-key-with-at-least-thirty-two-characters",
        "signing_master_key": "production-signing-key-with-at-least-thirty-two-characters",
        "pii_encryption_key": "production-pii-encryption-key-with-at-least-thirty-two-characters",
        "auto_create_schema": False,
        "seed_demo_admin": False,
    }
    safe = Settings(**shared)
    assert safe.app_env == "production"
    with pytest.raises(ValidationError):
        Settings(**{**shared, "auto_create_schema": True})
    with pytest.raises(ValidationError):
        Settings(**{**shared, "seed_demo_admin": True})


def test_production_rejects_missing_signing_master_key():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            secret_key="production-secret-key-with-at-least-thirty-two-characters",
            signing_master_key=None,
            auto_create_schema=False,
        )


def test_production_rejects_missing_or_reused_pii_encryption_key():
    shared = {
        "app_env": "production",
        "secret_key": "production-secret-key-with-at-least-thirty-two-characters",
        "signing_master_key": "production-signing-key-with-at-least-thirty-two-characters",
        "auto_create_schema": False,
        "seed_demo_admin": False,
    }
    with pytest.raises(ValidationError):
        Settings(**shared)
    with pytest.raises(ValidationError):
        Settings(**{**shared, "pii_encryption_key": shared["signing_master_key"]})
