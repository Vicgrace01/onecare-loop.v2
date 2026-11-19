
def test_health_endpoints(client):
    live = client.get("/api/v1/health/live")
    ready = client.get("/api/v1/health/ready")
    assert live.status_code == 200 and live.json()["ok"] is True
    assert ready.status_code == 200 and ready.json()["database"] == "available"


def test_audit_api_requires_authentication(client):
    response = client.get("/api/v1/audit/patients/not-a-patient/verify")
    assert response.status_code == 401


def test_audit_patient_scope_is_enforced(app):
    _, client = app
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "a-long-unique-password-123", "display_name": "Record Owner"},
    ).json()
    token = registered["access_token"]
    own = client.get(
        f"/api/v1/audit/patients/{registered['user']['patient_id']}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    other = client.get(
        "/api/v1/audit/patients/a-different-patient/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own.status_code == 200
    assert own.json()["events"] == 0
    assert other.status_code == 403
