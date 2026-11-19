from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.db.models import Organisation, User
from app.main import create_app


PREFIX = "/api/v1"


def build_client(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="test-secret-unique-long-enough-for-workflow-tests",
        signing_master_key="test-signing-key-unique-long-enough-for-workflow-tests",
        database_url=f"sqlite:///{tmp_path / 'care.db'}",
        auto_create_schema=True,
        self_registration_enabled=True,
        seed_demo_admin=False,
    )
    app = create_app(settings)
    client_ctx = TestClient(app)
    client = client_ctx.__enter__()
    factory = app.state.session_factory
    with factory() as db:
        admin = User(
            id=str(uuid.uuid4()), email="admin@onecare.example", email_normalized="admin@onecare.example",
            password_hash=hash_password("this-is-a-long-admin-test-password"), role="admin", is_active=True,
        )
        db.add(admin)
        db.commit()
    token = create_access_token(admin.id, settings.secret_key, settings.access_token_ttl_seconds)
    headers = {"Authorization": f"Bearer {token}"}
    return app, client_ctx, client, headers


def make_org_and_user(client, admin_headers, role: str, name: str):
    org_type = "hospital" if role == "clinician" else role
    response = client.post(f"{PREFIX}/organisations", headers=admin_headers, json={"name": name, "type": org_type})
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    email = f"{role}-{uuid.uuid4().hex[:8]}@onecare.example"
    provisioned = client.post(f"{PREFIX}/auth/provision", headers=admin_headers, json={
        "email": email, "password": "this-is-a-long-password-123", "role": role, "organisation_id": org_id,
    })
    assert provisioned.status_code == 201, provisioned.text
    login = client.post(f"{PREFIX}/auth/login", json={"email": email, "password": "this-is-a-long-password-123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return org_id, {"Authorization": f"Bearer {token}"}, provisioned.json()["id"]


def setup_world(tmp_path):
    app, ctx, client, admin_headers = build_client(tmp_path)
    pharm_org, pharmacy_headers, pharmacy_id = make_org_and_user(client, admin_headers, "pharmacy", "Greenlife Pharmacy")
    hosp_org, hospital_headers, hospital_id = make_org_and_user(client, admin_headers, "hospital", "Lagos Care Hospital")
    _clinician_org, clinician_headers, clinician_id = make_org_and_user(client, admin_headers, "clinician", "Lagos Care Clinicians")
    # Provisioning a clinician must attach them to the same hospital, so create an assigned clinician separately.
    email = f"assigned-clinician-{uuid.uuid4().hex[:8]}@onecare.example"
    provisioned = client.post(f"{PREFIX}/auth/provision", headers=admin_headers, json={
        "email": email, "password": "this-is-a-long-password-123", "role": "clinician", "organisation_id": hosp_org,
    })
    assert provisioned.status_code == 201, provisioned.text
    login = client.post(f"{PREFIX}/auth/login", json={"email": email, "password": "this-is-a-long-password-123"})
    clinician_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    clinician_id = provisioned.json()["id"]
    return app, ctx, client, admin_headers, pharmacy_headers, hospital_headers, clinician_headers, pharmacy_id, hospital_id, clinician_id, hosp_org


def close(ctx):
    ctx.__exit__(None, None, None)


def start_case(client, pharmacy_headers, hospital_org, phone="+2348012345678", bp=(182, 122), symptoms=None):
    screening = client.post(f"{PREFIX}/screenings", headers=pharmacy_headers, json={
        "patient": {"display_name": "Test Patient", "age_band": "40-49", "insurance_type": "nhia", "phone": phone},
        "consent": {"version": "1.0", "scopes": ["screening", "referral", "follow_up", "notifications"]},
        "screening": {"systolic": bp[0], "diastolic": bp[1], "symptoms": symptoms or [], "protocol_version": "HTN-PROTOCOL-v1"},
    })
    assert screening.status_code == 201, screening.text
    data = screening.json()
    referral = client.post(f"{PREFIX}/referrals", headers=pharmacy_headers, json={
        "screening_id": data["screening_id"], "facility_id": hospital_org,
    })
    assert referral.status_code == 201, referral.text
    return data, referral.json()


def test_complete_care_journey_patient_otp_receipt_fhir_and_followup(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org)
        patient_id, referral_id = screen["patient_id"], referral["referral_id"]
        assert screen["result"] == "positive"
        assert referral["urgency"] == "emergency"
        assert referral["eligibility"]["decision"] == "unknown"
        assert referral["eligibility"]["simulated"] is True

        # A consultation event is part of the ledger but must not become the workflow state.
        message = client.post(f"{PREFIX}/referrals/{referral_id}/messages", headers=pharmacy,
                              json={"body": "Please confirm the next available review slot."})
        assert message.status_code == 201, message.text
        accepted = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=hospital)
        assert accepted.status_code == 200, accepted.text
        booked = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "slot_end": (datetime.now(timezone.utc) + timedelta(days=1, minutes=30)).isoformat(),
        })
        assert booked.status_code == 200, booked.text
        attended = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/attendance", headers=hospital, json={
            "clinician_id": clinician_id, "notes": "Patient attended; assessment completed.",
        })
        assert attended.status_code == 200, attended.text
        clinician_queue = client.get(f"{PREFIX}/hospital/queue", headers=clinician)
        assert clinician_queue.status_code == 200, clinician_queue.text
        assert any(item["id"] == referral_id and item["status"] == "CLINICAL_ENCOUNTER_COMPLETED"
                   for item in clinician_queue.json()["queue"])
        assigned_staff = client.get(f"{PREFIX}/organisations/{hosp_org}/staff", headers=hospital)
        assert assigned_staff.status_code == 200, assigned_staff.text
        assert any(item["id"] == clinician_id and item["role"] == "clinician"
                   for item in assigned_staff.json()["staff"])
        blocked_disposition = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/disposition", headers=clinician, json={
            "outcome": "clinical_review_completed", "next_step": "Review blood pressure in 30 days.",
        })
        assert blocked_disposition.status_code == 409
        assert blocked_disposition.json()["detail"]["code"] == "confirmatory_assessment_required"
        confirmed = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/confirmatory-assessment", headers=clinician, json={
            "method": "repeat_office", "systolic": 160, "diastolic": 100,
            "note": "Repeat office reading recorded by the assigned clinician.",
        })
        assert confirmed.status_code == 200, confirmed.text
        disposition = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/disposition", headers=clinician, json={
            "outcome": "clinical_review_completed", "next_step": "Review blood pressure in 30 days.",
        })
        assert disposition.status_code == 200, disposition.text

        due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        scheduled = client.post(f"{PREFIX}/patients/{patient_id}/followups", headers=clinician, json={
            "due_date": due, "plan_type": "30_day",
        })
        assert scheduled.status_code == 201, scheduled.text
        assessment = client.post(f"{PREFIX}/patients/{patient_id}/followups/assessment", headers=pharmacy, json={
            "systolic": 136, "diastolic": 86,
        })
        assert assessment.status_code == 200, assessment.text
        control = client.post(f"{PREFIX}/patients/{patient_id}/followups/bp-control", headers=pharmacy, json={
            "systolic": 136, "diastolic": 86, "bp_controlled": True,
        })
        assert control.status_code == 200, control.text

        otp_req = client.post(f"{PREFIX}/patients/otp/request", json={"phone": "+2348012345678"})
        assert otp_req.status_code == 200, otp_req.text
        code = otp_req.json().get("development_code")
        assert code and otp_req.json()["development_only"] is True
        otp_verify = client.post(f"{PREFIX}/patients/otp/verify", json={"phone": "+2348012345678", "code": code})
        assert otp_verify.status_code == 200, otp_verify.text
        patient_headers = {"Authorization": f"Bearer {otp_verify.json()['access_token']}"}
        receipt = client.get(f"{PREFIX}/patients/me/receipt", headers=patient_headers)
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["verified"] is True
        assert any(e["event_type"] == "CLINICAL_DISPOSITION_RETURNED" for e in receipt.json()["events"])
        assert any(e["event_type"] == "FOLLOWUP_DUE" for e in receipt.json()["events"])

        acknowledged = client.post(f"{PREFIX}/patients/me/receipt/acknowledge", headers=patient_headers)
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["event"]["event_type"] == "PATIENT_ACKNOWLEDGED"
        after_ack = client.get(f"{PREFIX}/patients/{patient_id}/followups", headers=clinician)
        assert after_ack.status_code == 200
        assert after_ack.json()["current_state"] == "BP_CONTROL_RECORDED"

        bundle = client.get(f"{PREFIX}/fhir/patients/{patient_id}/bundle", headers=patient_headers)
        assert bundle.status_code == 200, bundle.text
        assert bundle.json()["resourceType"] == "Bundle"
        resource_types = {entry["resource"]["resourceType"] for entry in bundle.json()["entry"]}
        assert {"Patient", "Observation", "ServiceRequest", "Task", "Appointment", "Encounter", "ClinicalImpression"}.issubset(resource_types)
        observations = [entry["resource"] for entry in bundle.json()["entry"] if entry["resource"]["resourceType"] == "Observation"]
        assert any("Confirmatory blood pressure assessment" in observation.get("code", {}).get("text", "") for observation in observations)
        patient_resource = next(e["resource"] for e in bundle.json()["entry"] if e["resource"]["resourceType"] == "Patient")
        assert "name" not in patient_resource and "telecom" not in patient_resource

        # Patient may revoke their own consent. The contact lookup is severed and the wrapped key is destroyed.
        revoked = client.post(f"{PREFIX}/patients/{patient_id}/consent/revoke", headers=patient_headers, json={"reason": "patient_request"})
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["contact_key_shredded"] is True
        verify = client.get(f"{PREFIX}/audit/patients/{patient_id}/verify", headers=admin)
        assert verify.status_code == 200 and verify.json()["ok"] is True
    finally:
        close(ctx)


def test_role_and_facility_boundaries_and_redirect(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        other_org, _other_hospital_headers, _ = make_org_and_user(client, admin, "hospital", "Other Hospital")
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345680", bp=(168, 104))
        referral_id = referral["referral_id"]
        # A hospital account from another facility cannot accept this referral.
        _, foreign_headers, _ = make_org_and_user(client, admin, "hospital", "Foreign Facility")
        forbidden = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=foreign_headers)
        assert forbidden.status_code == 403
        # Valid hospital declines and redirects; all three events remain in the same transaction.
        declined = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/decline", headers=hospital, json={
            "reason_code": "no_capacity", "redirect_facility_id": other_org,
        })
        assert declined.status_code == 200, declined.text
        assert declined.json()["redirected_to"]["id"] == other_org
        history = client.get(f"{PREFIX}/referrals/{referral_id}/history", headers=admin)
        assert history.status_code == 200, history.text
        types = [e["event_type"] for e in history.json()["events"]]
        assert "REFERRAL_DECLINED" in types and "REFERRAL_REDIRECTED" in types and "REFERRAL_CREATED" in types
    finally:
        close(ctx)


def test_operational_endpoints_require_auth_and_patient_scope(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345681")
        pid = screen["patient_id"]
        # Unauthenticated APIs cannot create or move care events.
        denied = client.post(f"{PREFIX}/hospital/referrals/{referral['referral_id']}/accept")
        assert denied.status_code == 401
        denied_metrics = client.get(f"{PREFIX}/metrics")
        assert denied_metrics.status_code == 401
        # A patient OTP token cannot access another patient's receipt.
        otp = client.post(f"{PREFIX}/patients/otp/request", json={"phone": "+2348012345681"}).json()
        verified = client.post(f"{PREFIX}/patients/otp/verify", json={"phone": "+2348012345681", "code": otp["development_code"]}).json()
        patient_headers = {"Authorization": f"Bearer {verified['access_token']}"}
        forbidden = client.get(f"{PREFIX}/patients/{str(uuid.uuid4())}/receipt", headers=patient_headers)
        assert forbidden.status_code == 403 or forbidden.status_code == 404
    finally:
        close(ctx)


def test_red_flag_acknowledgement_and_message_are_audited(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345682", symptoms=["chest_pain"])
        referral_id, pid = referral["referral_id"], screen["patient_id"]
        alerts = client.get(f"{PREFIX}/red-flags", headers=hospital)
        assert alerts.status_code == 200, alerts.text
        assert alerts.json()["simulated"] is True and alerts.json()["dispatch_enabled"] is False
        alert_id = alerts.json()["alerts"][0]["id"]
        ack = client.post(f"{PREFIX}/red-flags/{alert_id}/acknowledge", headers=hospital, json={"note": "On-call coordinator notified internally"})
        assert ack.status_code == 200, ack.text
        message = client.post(f"{PREFIX}/referrals/{referral_id}/messages", headers=pharmacy, json={"body": "Please confirm referral receipt."})
        assert message.status_code == 201, message.text
        thread = client.get(f"{PREFIX}/referrals/{referral_id}/messages", headers=hospital)
        assert thread.status_code == 200 and len(thread.json()["messages"]) == 1
        verification = client.get(f"{PREFIX}/audit/patients/{pid}/verify", headers=admin)
        assert verification.status_code == 200 and verification.json()["ok"] is True
    finally:
        close(ctx)


def test_patient_reschedule_is_audited_and_hospital_rebooks(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345683", bp=(168, 104))
        patient_id, referral_id = screen["patient_id"], referral["referral_id"]
        assert client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=hospital).status_code == 200

        first_start = datetime.now(timezone.utc) + timedelta(days=1)
        first_booking = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": first_start.isoformat(), "slot_end": (first_start + timedelta(minutes=30)).isoformat(),
        })
        assert first_booking.status_code == 200, first_booking.text

        otp = client.post(f"{PREFIX}/patients/otp/request", json={"phone": "+2348012345683"}).json()
        verified = client.post(f"{PREFIX}/patients/otp/verify", json={
            "phone": "+2348012345683", "code": otp["development_code"],
        })
        assert verified.status_code == 200, verified.text
        patient_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}

        requested = client.post(f"{PREFIX}/patients/me/referrals/{referral_id}/reschedule-request",
            headers=patient_headers, json={"reason_code": "appointment_time_conflict"})
        assert requested.status_code == 200, requested.text

        second_start = datetime.now(timezone.utc) + timedelta(days=3)
        second_booking = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": second_start.isoformat(), "slot_end": (second_start + timedelta(minutes=30)).isoformat(),
        })
        assert second_booking.status_code == 200, second_booking.text

        from sqlalchemy import select
        from app.db.models import Appointment
        with app.state.session_factory() as db:
            appointments = db.scalars(select(Appointment).where(Appointment.referral_id == referral_id).order_by(Appointment.created_at.asc())).all()
            assert len(appointments) == 2
            assert appointments[0].status == "cancelled"
            assert appointments[1].status == "booked"

        receipt = client.get(f"{PREFIX}/patients/me/receipt", headers=patient_headers)
        types = [item["event_type"] for item in receipt.json()["events"]]
        assert "PATIENT_REQUESTED_RESCHEDULE" in types
        assert types.count("APPOINTMENT_BOOKED") == 2
        assert client.get(f"{PREFIX}/audit/patients/{patient_id}/verify", headers=admin).json()["ok"] is True
    finally:
        close(ctx)


def test_hospital_can_mark_missed_and_patient_can_decline_own_referral(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345684", bp=(168, 104))
        patient_id, referral_id = screen["patient_id"], referral["referral_id"]
        assert client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=hospital).status_code == 200
        slot_start = datetime.now(timezone.utc) + timedelta(days=1)
        booked = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": slot_start.isoformat(), "slot_end": (slot_start + timedelta(minutes=30)).isoformat(),
        })
        assert booked.status_code == 200, booked.text
        missed = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments/missed", headers=hospital,
            json={"reason_code": "patient_did_not_attend"})
        assert missed.status_code == 200, missed.text
        rebook_start = datetime.now(timezone.utc) + timedelta(days=4)
        rebooked = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": rebook_start.isoformat(), "slot_end": (rebook_start + timedelta(minutes=30)).isoformat(),
        })
        assert rebooked.status_code == 200, rebooked.text
        assert rebooked.json()["event"]["event_type"] == "APPOINTMENT_BOOKED"

        # A second patient exercises the patient-decline path before hospital acceptance.
        screen2, referral2 = start_case(client, pharmacy, hosp_org, phone="+2348012345685", bp=(168, 104))
        otp = client.post(f"{PREFIX}/patients/otp/request", json={"phone": "+2348012345685"}).json()
        verified = client.post(f"{PREFIX}/patients/otp/verify", json={
            "phone": "+2348012345685", "code": otp["development_code"],
        })
        patient_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
        declined = client.post(f"{PREFIX}/patients/me/referrals/{referral2['referral_id']}/decline",
            headers=patient_headers, json={"reason_code": "patient_choice"})
        assert declined.status_code == 200, declined.text
        assert client.post(f"{PREFIX}/hospital/referrals/{referral2['referral_id']}/accept", headers=hospital).status_code == 409
        assert client.get(f"{PREFIX}/audit/patients/{patient_id}/verify", headers=admin).json()["ok"] is True
    finally:
        close(ctx)


def test_patient_data_is_encrypted_in_storage_and_redacted_after_revocation(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        phone = "+2348012345686"
        screen, referral = start_case(client, pharmacy, hosp_org, phone=phone, bp=(182, 122), symptoms=["chest_pain"])
        patient_id = screen["patient_id"]

        from sqlalchemy import select
        from app.core.security import hash_password
        from app.db.models import LedgerEvent, Patient, PatientContact, PatientDataKey, Screening, User
        from app.services.privacy import (
            account_email_alias, decrypt_patient_value, email_lookup_token, encrypt_account_email,
        )
        with app.state.session_factory() as db:
            patient = db.get(Patient, patient_id)
            contact = db.scalar(select(PatientContact).where(PatientContact.patient_id == patient_id))
            screening_row = db.get(Screening, screen["screening_id"])
            first_event = db.scalar(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.asc()))
            assert patient.display_name is None and patient.age_band is None and patient.insurance_type is None
            assert patient.display_name_ciphertext and patient.demographic_data_ciphertext
            assert phone not in contact.phone_ciphertext and phone not in contact.phone_lookup_hash
            assert screening_row.systolic is None and screening_row.diastolic is None and screening_row.symptoms == []
            assert screening_row.clinical_data_ciphertext
            assert first_event.payload.keys() == {"_encrypted_payload_v1"}
            demographics = decrypt_patient_value(db, patient_id, patient.demographic_data_ciphertext,
                "demographic_data", app.state.settings)
            assert '"age_band":"40-49"' in demographics
            clinical = decrypt_patient_value(db, patient_id, screening_row.clinical_data_ciphertext,
                "screening_clinical_data", app.state.settings)
            assert '"systolic":182' in clinical and "chest_pain" in clinical
            email = "private.patient@example.com"
            account = User(
                email=account_email_alias(str(uuid.uuid4())),
                email_normalized=email_lookup_token(email, app.state.settings),
                email_ciphertext=encrypt_account_email(email, app.state.settings),
                password_hash=hash_password("patient-account-password-123"),
                role="patient", patient_id=patient_id,
            )
            db.add(account)
            db.commit()
            account_id = account.id
            assert email not in account.email and email not in account.email_normalized

        # The hospital queue survives consent erasure but returns no measurements.
        otp = client.post(f"{PREFIX}/patients/otp/request", json={"phone": phone}).json()
        verified = client.post(f"{PREFIX}/patients/otp/verify", json={"phone": phone, "code": otp["development_code"]})
        patient_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
        revoked = client.post(f"{PREFIX}/patients/{patient_id}/consent/revoke", headers=patient_headers, json={"reason": "patient_request"})
        assert revoked.status_code == 200, revoked.text

        queue = client.get(f"{PREFIX}/hospital/queue", headers=hospital).json()["queue"]
        row = next(item for item in queue if item["id"] == referral["referral_id"])
        assert row["details_redacted"] is True
        assert row["systolic"] is None and row["diastolic"] is None

        admin_receipt = client.get(f"{PREFIX}/patients/{patient_id}/receipt", headers=admin)
        assert admin_receipt.status_code == 200, admin_receipt.text
        past_events = [e for e in admin_receipt.json()["events"] if e["event_type"] != "CONSENT_REVOKED"]
        assert past_events and all(e["details_redacted"] for e in past_events)
        with app.state.session_factory() as db:
            data_key = db.get(PatientDataKey, patient_id)
            assert data_key.shredded_at is not None and data_key.wrapped_key == ""
            erased_account = db.get(User, account_id)
            assert erased_account.email_ciphertext is None and erased_account.is_active is False
        assert client.get(f"{PREFIX}/audit/patients/{patient_id}/verify", headers=admin).json()["ok"] is True
    finally:
        close(ctx)


def test_patient_can_start_a_new_screening_episode_after_disposition(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        phone = "+2348012345687"
        first_screen, first_referral = start_case(client, pharmacy, hosp_org, phone=phone, bp=(168, 104))
        rid1 = first_referral["referral_id"]
        assert client.post(f"{PREFIX}/hospital/referrals/{rid1}/accept", headers=hospital).status_code == 200
        start = datetime.now(timezone.utc) + timedelta(days=1)
        assert client.post(f"{PREFIX}/hospital/referrals/{rid1}/appointments", headers=hospital, json={
            "slot_start": start.isoformat(), "slot_end": (start + timedelta(minutes=30)).isoformat(),
        }).status_code == 200
        assert client.post(f"{PREFIX}/hospital/referrals/{rid1}/attendance", headers=hospital, json={
            "clinician_id": clinician_id, "notes": "review complete",
        }).status_code == 200
        confirm = client.post(f"{PREFIX}/hospital/referrals/{rid1}/confirmatory-assessment", headers=clinician, json={
            "method": "home_monitoring", "systolic": 150, "diastolic": 96,
            "note": "Home readings reviewed by the assigned clinician.",
        })
        assert confirm.status_code == 200, confirm.text
        assert client.post(f"{PREFIX}/hospital/referrals/{rid1}/disposition", headers=clinician, json={
            "outcome": "review_complete", "next_step": "Continue scheduled follow-up",
        }).status_code == 200

        second_screen, second_referral = start_case(client, pharmacy, hosp_org, phone=phone, bp=(148, 94))
        assert second_screen["patient_id"] == first_screen["patient_id"]
        assert second_screen["screening_id"] != first_screen["screening_id"]
        assert second_referral["referral_id"] != rid1

        old_history = client.get(f"{PREFIX}/referrals/{rid1}/history", headers=admin)
        new_history = client.get(f"{PREFIX}/referrals/{second_referral['referral_id']}/history", headers=admin)
        assert old_history.status_code == 200, old_history.text
        assert new_history.status_code == 200, new_history.text
        assert any(e["event_type"] == "SCREEN_POSITIVE" and e["payload"]["screening_id"] == first_screen["screening_id"] for e in old_history.json()["events"])
        assert any(e["event_type"] == "SCREEN_POSITIVE" and e["payload"]["screening_id"] == second_screen["screening_id"] for e in new_history.json()["events"])

        from sqlalchemy import select
        from app.db.models import Consent
        with app.state.session_factory() as db:
            grants = db.scalars(select(Consent).where(Consent.patient_id == first_screen["patient_id"])).all()
            assert len(grants) == 2
            assert sum(1 for grant in grants if grant.revoked_at is None) == 1
        assert client.get(f"{PREFIX}/audit/patients/{first_screen['patient_id']}/verify", headers=admin).json()["ok"] is True
    finally:
        close(ctx)



def test_declined_referral_can_be_redirected_later(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        alternate_org, alternate_headers, alternate_hospital_id = make_org_and_user(client, admin, "hospital", "Alternative Hospital")
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345692", bp=(168, 104))
        referral_id = referral["referral_id"]
        # Make the first facility's SLA visibly expired; the replacement must get a fresh window.
        from app.db.models import Referral, EligibilityCheck
        with app.state.session_factory() as db:
            original = db.get(Referral, referral_id)
            original.sla_deadline = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
        declined = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/decline", headers=hospital,
                               json={"reason_code": "temporary_capacity_limit"})
        assert declined.status_code == 200, declined.text
        assert declined.json()["redirected_to"] is None
        redirected = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/redirect", headers=hospital,
                                 json={"facility_id": alternate_org})
        assert redirected.status_code == 200, redirected.text
        assert redirected.json()["facility"]["id"] == alternate_org
        new_id = redirected.json()["new_referral_id"]
        queue = client.get(f"{PREFIX}/hospital/queue", headers=alternate_headers).json()["queue"]
        new_item = next(item for item in queue if item["id"] == new_id)
        assert new_item["status"] == "REFERRAL_CREATED"
        assert new_item["unassigned"] is True
        assert new_item["sla_breached"] is False
        with app.state.session_factory() as db:
            original = db.get(Referral, referral_id)
            replacement = db.get(Referral, new_id)
            eligibility = db.query(EligibilityCheck).filter_by(referral_id=new_id).one()
            assert replacement.sla_deadline > original.sla_deadline
            assert eligibility.decision == "unknown" and eligibility.simulated is True
        assert client.get(f"{PREFIX}/audit/patients/{screen['patient_id']}/verify", headers=admin).json()["ok"] is True
    finally:
        close(ctx)



def test_auxiliary_events_do_not_override_workflow_state_and_confirmatory_gate(tmp_path):
    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345690", bp=(168, 104))
        referral_id = referral["referral_id"]
        message = client.post(f"{PREFIX}/referrals/{referral_id}/messages", headers=pharmacy,
                              json={"body": "Please advise on availability."})
        assert message.status_code == 201
        accepted = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=hospital)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["event"]["event_type"] == "FACILITY_ACCEPTED"

        booked = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "slot_end": (datetime.now(timezone.utc) + timedelta(days=1, minutes=30)).isoformat(),
        })
        assert booked.status_code == 200
        attended = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/attendance", headers=hospital, json={
            "clinician_id": clinician_id, "notes": "Attended",
        })
        assert attended.status_code == 200

        # A not-indicated decision is acceptable only with a documented clinical reason.
        missing_reason = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/confirmatory-assessment", headers=clinician,
                                     json={"method": "not_indicated", "note": "no"})
        assert missing_reason.status_code == 422
        not_indicated = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/confirmatory-assessment", headers=clinician,
                                    json={"method": "not_indicated", "note": "Confirmatory testing not indicated after clinician review."})
        assert not_indicated.status_code == 200, not_indicated.text
        disposition = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/disposition", headers=clinician, json={
            "outcome": "clinical_review_completed", "next_step": "Follow up in 30 days.",
        })
        assert disposition.status_code == 200, disposition.text

        # The latest ledger entry is a clinical workflow state even after auxiliary events.
        receipt_otp = client.post(f"{PREFIX}/patients/otp/request", json={"phone": "+2348012345690"}).json()
        verify = client.post(f"{PREFIX}/patients/otp/verify", json={"phone": "+2348012345690", "code": receipt_otp["development_code"]}).json()
        patient_headers = {"Authorization": f"Bearer {verify['access_token']}"}
        client.post(f"{PREFIX}/patients/me/receipt/acknowledge", headers=patient_headers)
        status = client.get(f"{PREFIX}/patients/{screen['patient_id']}/followups", headers=clinician)
        assert status.status_code == 200
        assert status.json()["current_state"] == "CLINICAL_DISPOSITION_RETURNED"
    finally:
        close(ctx)


def test_referral_owner_assignment_and_overdue_escalation_are_visible_and_idempotent(tmp_path):
    from app.db.models import Referral, LoopException
    from app.services.care import process_overdue_referrals

    world = setup_world(tmp_path)
    app, ctx, client, admin, pharmacy, hospital, clinician, pharmacy_id, hospital_id, clinician_id, hosp_org = world
    try:
        screen, referral = start_case(client, pharmacy, hosp_org, phone="+2348012345691", bp=(168, 104))
        referral_id = referral["referral_id"]
        accepted = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/accept", headers=hospital)
        assert accepted.status_code == 200
        queue = client.get(f"{PREFIX}/hospital/queue", headers=hospital).json()["queue"]
        item = next(row for row in queue if row["id"] == referral_id)
        assert item["owner_user_id"] == hospital_id
        assert item["unassigned"] is False
        reassigned = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/assign", headers=hospital,
                                 json={"owner_user_id": clinician_id})
        assert reassigned.status_code == 200, reassigned.text
        item = next(row for row in client.get(f"{PREFIX}/hospital/queue", headers=hospital).json()["queue"] if row["id"] == referral_id)
        assert item["owner_user_id"] == clinician_id
        booking_start = datetime.now(timezone.utc) + timedelta(days=2)
        booking = client.post(f"{PREFIX}/hospital/referrals/{referral_id}/appointments", headers=hospital, json={
            "slot_start": booking_start.isoformat(),
            "slot_end": (booking_start + timedelta(minutes=30)).isoformat(),
        })
        assert booking.status_code == 200, booking.text

        with app.state.session_factory() as db:
            row = db.get(Referral, referral_id)
            row.sla_deadline = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
        with app.state.session_factory() as db:
            first = process_overdue_referrals(db)
            db.commit()
        with app.state.session_factory() as db:
            second = process_overdue_referrals(db)
            count = db.query(LoopException).filter_by(referral_id=referral_id, event_type="REFERRAL_SLA_BREACHED").count()
        assert first["escalated"] == [referral_id]
        assert second["escalated"] == []
        assert count == 1

        attention = client.get(f"{PREFIX}/hospital/attention", headers=hospital)
        assert attention.status_code == 200, attention.text
        assert any(entry["referral_id"] == referral_id for entry in attention.json()["overdue"])
        queue = client.get(f"{PREFIX}/hospital/queue", headers=hospital).json()["queue"]
        assert next(row for row in queue if row["id"] == referral_id)["escalated_at"] is not None
    finally:
        close(ctx)
