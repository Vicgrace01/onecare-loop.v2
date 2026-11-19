from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Organisation, User, UserRole


def test_registration_always_creates_patient_role(app):
    application, client = app
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new.patient@example.com",
            "password": "a-long-unique-password-123",
            "display_name": "Test Patient",
            "role": "admin",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["user"]["role"] == "patient"
    assert data["user"]["patient_id"]
    assert data["user"]["email"] == "new.patient@example.com"
    assert data["access_token"]

    with application.state.session_factory() as db:
        stored = db.get(User, data["user"]["id"])
        assert stored is not None
        assert stored.role == UserRole.PATIENT.value
        assert stored.email == f"account-{stored.id}@onecare.invalid"
        assert stored.email_normalized != "new.patient@example.com"
        assert stored.email_ciphertext
        assert "new.patient@example.com" not in stored.email
        assert "new.patient@example.com" not in stored.email_normalized

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "NEW.PATIENT@example.com", "password": "a-long-unique-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "new.patient@example.com"


def test_patient_cannot_provision_staff(app):
    _, client = app
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "patient@example.com", "password": "a-long-unique-password-123", "display_name": "Patient One"},
    ).json()
    response = client.post(
        "/api/v1/auth/provision",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
        json={"email": "fake.admin@example.com", "password": "a-long-unique-password-123", "role": "hospital"},
    )
    assert response.status_code == 403


def test_only_admin_can_provision_staff(app):
    application, client = app
    with application.state.session_factory() as db:
        admin = User(
            email="root@example.com",
            email_normalized="root@example.com",
            password_hash=hash_password("a-long-unique-password-123"),
            role=UserRole.ADMIN.value,
        )
        db.add(admin)
        db.add(Organisation(id="org-hosp", name="General Hospital", type="hospital"))
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "root@example.com", "password": "a-long-unique-password-123"},
    )
    assert login.status_code == 200
    # Legacy plaintext account records are upgraded after a successful login.
    with application.state.session_factory() as db:
        upgraded = db.get(User, admin.id)
        assert upgraded.email_ciphertext
        assert upgraded.email != "root@example.com"
        assert upgraded.email_normalized != "root@example.com"
    token = login.json()["access_token"]
    created = client.post(
        "/api/v1/auth/provision",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "clinician@example.com", "password": "another-long-password-123", "role": "clinician", "organisation_id": "org-hosp"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "clinician"
    assert created.json()["email"] == "clinician@example.com"
    with application.state.session_factory() as db:
        clinician = db.get(User, created.json()["id"])
        assert clinician.email_ciphertext
        assert clinician.email_normalized != "clinician@example.com"


def test_login_and_me_reloads_database_role(app):
    application, client = app
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.com", "password": "a-long-unique-password-123", "display_name": "Person"},
    ).json()
    token = registered["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "patient"

    with application.state.session_factory() as db:
        user = db.get(User, registered["user"]["id"])
        user.role = "admin"
        db.commit()
    me_after_role_change = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after_role_change.status_code == 200
    assert me_after_role_change.json()["role"] == "admin"


def test_invalid_login_is_generic(client):
    response = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
