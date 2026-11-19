from app.db.models import Organisation, User
from app.core.security import create_access_token, hash_password


def test_web_app_and_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "OneCare Loop" in page.text
    assert page.headers.get("content-security-policy")
    assert page.headers.get("x-frame-options") == "DENY"

    css = client.get("/assets/css/app.css")
    js = client.get("/assets/js/app.js")
    heritage_css = client.get("/assets/css/heritage.css")
    motion_js = client.get("/assets/js/heritage-motion.js")
    assert css.status_code == 200 and "--deep" in css.text
    assert js.status_code == 200 and "screening-form" in js.text
    assert heritage_css.status_code == 200 and "oc-landing" in heritage_css.text
    assert motion_js.status_code == 200 and "OneCareMotion" in motion_js.text


def test_organisation_staff_list_is_scoped_and_admin_can_view(app):
    application, client = app
    with application.state.session_factory() as db:
        admin = User(
            email="root@web-test.invalid",
            email_normalized="root@web-test.invalid",
            password_hash=hash_password("long-enough-test-password-123"),
            role="admin",
        )
        hospital = Organisation(id="web-hospital", name="Web Test Hospital", type="hospital")
        db.add_all([admin, hospital])
        db.commit()
        admin_id = admin.id

    token = create_access_token(
        admin_id,
        application.state.settings.secret_key,
        application.state.settings.access_token_ttl_seconds,
    )
    response = client.get(
        "/api/v1/organisations/web-hospital/staff",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["organisation_id"] == "web-hospital"


def test_authenticated_patient_cannot_list_staff(client):
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "patient-ui@example.com", "password": "patient-ui-long-password-123", "display_name": "Patient UI"},
    ).json()
    response = client.get(
        "/api/v1/organisations/not-their-org/staff",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )
    assert response.status_code == 404 or response.status_code == 403
