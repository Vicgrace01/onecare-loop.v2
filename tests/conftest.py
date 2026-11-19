from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-key-with-more-than-thirty-two-characters",
        signing_master_key="test-signing-master-key-with-more-than-thirty-two-characters",
        database_url=f"sqlite:///{tmp_path / 'onecare-test.db'}",
        auto_create_schema=True,
        self_registration_enabled=True,
        seed_demo_admin=False,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        yield application, client


@pytest.fixture
def client(app):
    return app[1]
