from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _demo_settings(tmp_path, *, enabled=True, credentials=True):
    return Settings(
        app_env="test",
        secret_key="judge-demo-secret-key-that-is-more-than-thirty-two-characters",
        signing_master_key="judge-demo-signing-master-key-that-is-also-long-enough-123",
        pii_encryption_key="judge-demo-pii-encryption-key-distinct-and-long-enough-456",
        database_url=f"sqlite:///{tmp_path / 'judge-demo.db'}",
        auto_create_schema=True,
        self_registration_enabled=False,
        seed_demo_admin=False,
        demo_mode_enabled=enabled,
        demo_show_credentials=credentials,
        demo_pharmacy_email="demo.pharmacy@onecareloop.com",
        demo_pharmacy_password="Demo-Pharmacy-Pass-2026!",
        demo_hospital_email="demo.hospital@onecareloop.com",
        demo_hospital_password="Demo-Hospital-Pass-2026!",
        demo_clinician_email="demo.clinician@onecareloop.com",
        demo_clinician_password="Demo-Clinician-Pass-2026!",
        demo_hmo_email="demo.hmo@onecareloop.com",
        demo_hmo_password="Demo-HMO-Reviewer-Pass-2026!",
    )


def test_judge_demo_is_fail_closed_when_not_enabled(tmp_path):
    application = create_app(_demo_settings(tmp_path, enabled=False, credentials=False))
    with TestClient(application) as client:
        page = client.get("/demo")
        assert page.status_code == 200
        assert "Start full demo" in page.text
        info = client.get("/api/v1/demo/info")
        assert info.status_code == 200
        assert info.json()["enabled"] is False
        assert info.json()["roles"] == []
        assert client.post("/api/v1/demo/run", json={}).status_code == 404


def test_judge_demo_runs_full_synthetic_care_workflow_and_verifies_chain(tmp_path):
    application = create_app(_demo_settings(tmp_path))
    with TestClient(application) as client:
        info = client.get("/api/v1/demo/info")
        assert info.status_code == 200
        payload = info.json()
        assert payload["enabled"] is True
        assert payload["credentials_visible"] is True
        assert {role["role"] for role in payload["roles"]} == {"pharmacy", "hospital", "clinician", "hmo"}
        assert len({role["password"] for role in payload["roles"]}) == 4
        for account in payload["roles"]:
            login = client.post("/api/v1/auth/login", json={"email": account["email"], "password": account["password"]})
            assert login.status_code == 200, login.text
            assert login.json()["user"]["role"] == account["role"]

        response = client.post("/api/v1/demo/run", json={})
        assert response.status_code == 200, response.text
        result = response.json()
        event_types = [event["event_type"] for event in result["events"]]
        assert event_types == [
            "SCREEN_POSITIVE",
            "REFERRAL_CREATED",
            "FACILITY_ACCEPTED",
            "APPOINTMENT_BOOKED",
            "CLINICAL_ENCOUNTER_COMPLETED",
            "CONFIRMATORY_TEST_RECORDED",
            "CLINICAL_DISPOSITION_RETURNED",
            "FOLLOWUP_DUE",
        ]
        assert result["synthetic_only"] is True
        assert result["chain"]["verified"] is True
        assert result["chain"]["event_count"] == 8
        assert result["chain"]["signed_count"] == 8
        assert result["notification_provider_called"] is False
        assert result["transparency"]["eligibility"].startswith("unknown")
        assert result["transparency"]["financial_savings"] == "not estimated"
        assert result["confirmatory"] == {"method": "repeat_office", "systolic": 158, "diastolic": 98}
        assert result["follow_up_due"]

        # The API persists a real test workflow: the patient chain endpoint verifies it independently.
        verify = client.get(f"/api/v1/audit/patients/{result['patient_id']}/verify")
        assert verify.status_code == 401  # public demo does not make the patient audit endpoint public
        with application.state.session_factory() as db:
            from app.domain.ledger import verify_patient_chain
            assert verify_patient_chain(db, result["patient_id"])["ok"] is True


def test_judge_demo_hides_passwords_unless_explicitly_enabled(tmp_path):
    application = create_app(_demo_settings(tmp_path, credentials=False))
    with TestClient(application) as client:
        info = client.get("/api/v1/demo/info").json()
        assert info["enabled"] is True
        assert info["credentials_visible"] is False
        assert all("password" not in account for account in info["roles"])


def test_judge_demo_env_template_creates_the_displayed_login_credentials(tmp_path):
    from pathlib import Path

    env_file = Path(__file__).resolve().parents[1] / "deploy" / "judge-demo.env.example"
    settings = Settings(
        _env_file=env_file,
        database_url=f"sqlite:///{tmp_path / 'configured-judge-demo.db'}",
    )
    assert settings.demo_mode_enabled is True
    assert settings.demo_show_credentials is True

    application = create_app(settings)
    with TestClient(application) as client:
        info = client.get("/api/v1/demo/info").json()
        assert info["enabled"] is True
        assert info["credentials_visible"] is True
        assert len(info["roles"]) == 4
        for account in info["roles"]:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": account["email"], "password": account["password"]},
            )
            assert response.status_code == 200, response.text
            assert response.json()["user"]["role"] == account["role"]
