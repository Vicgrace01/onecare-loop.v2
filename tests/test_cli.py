from sqlalchemy import select

from app.cli import create_first_admin
from app.core.config import Settings
from app.db.base import Base
from app.db.models import User
from app.db.session import build_engine, build_session_factory
from app.services.privacy import decrypt_account_email


def test_create_first_admin_bootstrap_is_encrypted_and_duplicate_safe(tmp_path, monkeypatch):
    from app import cli

    settings = Settings(
        app_env="test",
        secret_key="cli-test-secret-key-long-enough-for-testing-123456",
        signing_master_key="cli-test-signing-key-long-enough-for-testing-123456",
        pii_encryption_key="cli-test-pii-key-long-enough-for-testing-123456789",
        database_url=f"sqlite:///{tmp_path / 'bootstrap.db'}",
        auto_create_schema=False,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    engine = build_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    user_id = create_first_admin("owner@example.test", "a-very-long-admin-password-123")
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    try:
        with factory() as db:
            user = db.scalar(select(User).where(User.id == user_id))
            assert user is not None
            assert user.role == "admin"
            assert user.email_ciphertext
            assert user.email != "owner@example.test"
            assert user.email_normalized != "owner@example.test"
            assert decrypt_account_email(user.email_ciphertext, settings) == "owner@example.test"
    finally:
        engine.dispose()

    try:
        create_first_admin("owner@example.test", "a-very-long-admin-password-123")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate administrator email was accepted")


def test_create_first_admin_rejects_short_password(tmp_path, monkeypatch):
    from app import cli

    settings = Settings(
        app_env="test",
        secret_key="cli-test-secret-key-long-enough-for-testing-123456",
        signing_master_key="cli-test-signing-key-long-enough-for-testing-123456",
        database_url=f"sqlite:///{tmp_path / 'short-password.db'}",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    try:
        create_first_admin("owner@example.test", "short")
    except ValueError as exc:
        assert "12 characters" in str(exc)
    else:
        raise AssertionError("short administrator password was accepted")
