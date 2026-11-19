from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.db.models import (
    AccessLog, Appointment, CaseMessage, ClinicalDisposition, Consent, Encounter,
    EligibilityCheck, FollowUpPlan, LedgerEvent, LoopException, Notification, Organisation,
    Patient, PatientContact, PatientDataKey, PatientOTP, Referral, Screening,
    User, utc_now,
)
from app.domain.ledger import append_event, latest_workflow_state, record_transition, verify_patient_chain
from app.domain.states import TransitionError


RED_FLAG_SYMPTOMS = {
    "chest_pain", "one_sided_weakness", "vision_loss", "severe_headache",
    "shortness_of_breath", "confusion", "fainting",
}
SUPPORTED_LANGUAGES = {"en", "pcm", "ig", "ha", "yo"}
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


class CareError(ValueError):
    def __init__(self, reason: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status_code = status_code


def _phone_normalize(phone: str) -> str:
    value = re.sub(r"[\s()\-]", "", phone or "")
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", value):
        raise CareError("invalid_phone", "Phone must be a valid international number")
    return value if value.startswith("+") else "+" + value


def _phone_hash(phone: str, settings: Settings) -> str:
    lookup_key = settings.pii_encryption_key or settings.signing_master_key or settings.secret_key
    return hmac.new(lookup_key.encode(), phone.encode(), hashlib.sha256).hexdigest()


def _encrypt_phone(phone: str, patient_id: str, data_key: bytes) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, phone.encode(), patient_id.encode())
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _store_contact(db: Session, patient_id: str, phone: str, language: str, settings: Settings) -> None:
    from app.services.privacy import get_patient_data_key
    normalized = _phone_normalize(phone)
    lookup = _phone_hash(normalized, settings)
    existing = db.scalar(select(PatientContact).where(PatientContact.phone_lookup_hash == lookup))
    if existing:
        if existing.patient_id != patient_id:
            raise CareError("phone_already_registered", "This phone number is already associated with another patient", 409)
        return
    data_key = get_patient_data_key(db, patient_id, settings, create=True)
    assert data_key is not None
    db.add(PatientContact(
        patient_id=patient_id,
        phone_lookup_hash=lookup,
        phone_ciphertext=_encrypt_phone(normalized, patient_id, data_key),
        preferred_language=language if language in SUPPORTED_LANGUAGES else "en",
    ))
    db.flush()


def _require_org_actor(actor: User, allowed_roles: set[str], org_type: str | None = None) -> Organisation:
    if actor.role not in allowed_roles:
        raise CareError("wrong_role", "Your account role cannot perform this action", 403)
    if not actor.organisation_id:
        raise CareError("organisation_required", "Your account is not assigned to an organisation", 403)
    organisation = None
    # The caller's session has already loaded the actor; get via relationship to avoid accepting a caller id.
    organisation = actor.organisation
    if organisation is None:
        raise CareError("organisation_not_found", "Your assigned organisation no longer exists", 403)
    if org_type and organisation.type != org_type:
        raise CareError("wrong_organisation_type", f"This action requires a {org_type} organisation", 403)
    if org_type is None and organisation.type not in allowed_roles:
        raise CareError("wrong_organisation_type", "Your organisation does not match your account role", 403)
    return organisation


def _active_consent(db: Session, patient_id: str) -> Consent | None:
    return db.scalar(
        select(Consent).where(Consent.patient_id == patient_id, Consent.revoked_at.is_(None))
        .order_by(Consent.granted_at.desc())
    )


def _consent_hash(patient_id: str, version: str, scopes: list[str], granted_at: datetime) -> str:
    material = json.dumps({
        "patient_id": patient_id, "version": version, "scopes": sorted(scopes),
        "granted_at": granted_at.astimezone(timezone.utc).isoformat(),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _classify_bp(systolic: int, diastolic: int, symptoms: list[str]) -> dict[str, Any]:
    red_triggers: list[str] = []
    if systolic >= 180:
        red_triggers.append("systolic_180_plus")
    if diastolic >= 120:
        red_triggers.append("diastolic_120_plus")
    red_triggers.extend(f"symptom_{item}" for item in sorted(set(symptoms) & RED_FLAG_SYMPTOMS))
    positive = systolic >= 140 or diastolic >= 90
    if red_triggers:
        urgency = "emergency"
    elif positive and (systolic >= 160 or diastolic >= 100):
        urgency = "urgent"
    elif positive:
        urgency = "routine"
    else:
        urgency = None
    return {
        "result": "positive" if positive else "negative",
        "red_flag": bool(red_triggers),
        "urgency": urgency,
        "red_flag_triggers": red_triggers,
    }


def _bp_valid(systolic: int, diastolic: int) -> None:
    if isinstance(systolic, bool) or isinstance(diastolic, bool):
        raise CareError("invalid_measurement", "Blood pressure values must be whole numbers")
    if not (40 <= systolic <= 300 and 20 <= diastolic <= 200 and systolic > diastolic):
        raise CareError("invalid_measurement", "Blood pressure values are outside valid recording ranges")


def _create_patient(db: Session, data: dict, settings: Settings) -> Patient:
    from app.services.privacy import (
        decrypt_patient_value,
        encrypt_patient_value,
        get_patient_data_key,
    )

    phone = data.get("phone")
    patient = None
    if phone:
        normalized = _phone_normalize(phone)
        existing_contact = db.scalar(select(PatientContact).where(
            PatientContact.phone_lookup_hash == _phone_hash(normalized, settings)
        ))
        if existing_contact:
            patient = db.get(Patient, existing_contact.patient_id)

    if patient is None:
        patient = Patient(display_name=None, age_band=None, insurance_type=None)
        db.add(patient)
        db.flush()
    else:
        # Demographic metadata is kept in the same patient-key envelope as other PII.
        existing_raw = None
        if patient.demographic_data_ciphertext:
            existing_raw = decrypt_patient_value(
                db, patient.id, patient.demographic_data_ciphertext, "demographic_data", settings
            )
        existing = json.loads(existing_raw) if existing_raw else {}
        if data.get("age_band") is not None:
            existing["age_band"] = data["age_band"]
        if data.get("insurance_type") is not None:
            existing["insurance_type"] = data["insurance_type"]
        get_patient_data_key(db, patient.id, settings, create=True)
        patient.demographic_data_ciphertext = encrypt_patient_value(
            db, patient.id, json.dumps(existing, sort_keys=True, separators=(",", ":")),
            "demographic_data", settings,
        )

    # The legacy plaintext columns are retained only for migration compatibility.
    patient.display_name = None
    patient.age_band = None
    patient.insurance_type = None
    if data.get("display_name") and not patient.display_name_ciphertext:
        get_patient_data_key(db, patient.id, settings, create=True)
        patient.display_name_ciphertext = encrypt_patient_value(
            db, patient.id, data["display_name"].strip(), "display_name", settings
        )
    if patient.demographic_data_ciphertext is None:
        demographics = {
            "age_band": data.get("age_band"),
            "insurance_type": data.get("insurance_type", "unknown"),
        }
        get_patient_data_key(db, patient.id, settings, create=True)
        patient.demographic_data_ciphertext = encrypt_patient_value(
            db, patient.id, json.dumps(demographics, sort_keys=True, separators=(",", ":")),
            "demographic_data", settings,
        )
    if phone:
        _store_contact(db, patient.id, phone, data.get("preferred_language", "en"), settings)
    db.flush()
    return patient

def create_screening(
    db: Session, *, actor: User, body: dict, settings: Settings,
) -> dict[str, Any]:
    organisation = _require_org_actor(actor, {"pharmacy", "pmv"})
    patient_input = body["patient"]
    consent_input = body["consent"]
    screening_input = body["screening"]
    systolic, diastolic = int(screening_input["systolic"]), int(screening_input["diastolic"])
    _bp_valid(systolic, diastolic)
    symptoms = sorted(set(screening_input.get("symptoms", [])))
    classification = _classify_bp(systolic, diastolic, symptoms)
    scopes = sorted(set(consent_input.get("scopes", ["screening", "referral", "follow_up", "notifications"])))
    permitted_scopes = {"screening", "referral", "follow_up", "notifications", "outcome_review"}
    if not scopes or not set(scopes).issubset(permitted_scopes) or "screening" not in scopes:
        raise CareError("invalid_consent_scope", "Consent must include screening and only recognised scopes")
    if classification["result"] == "positive" and "referral" not in scopes:
        raise CareError("referral_consent_required", "The patient must consent to referrals before a positive screening can be referred")

    patient = _create_patient(db, patient_input, settings)
    now = utc_now()
    # A fresh consent version supersedes older active grants for this patient.
    prior_consents = db.scalars(select(Consent).where(
        Consent.patient_id == patient.id, Consent.revoked_at.is_(None)
    )).all()
    for prior in prior_consents:
        prior.revoked_at = now
    consent_version = str(consent_input.get("version") or "1.0")
    consent_digest = _consent_hash(patient.id, consent_version, scopes, now)
    consent = Consent(
        patient_id=patient.id, version=consent_version, scopes=scopes,
        payload_hash=consent_digest, granted_at=now,
    )
    db.add(consent)
    from app.services.privacy import encrypt_patient_value
    clinical_data = json.dumps({"systolic": systolic, "diastolic": diastolic, "symptoms": symptoms}, separators=(",", ":"))
    screening = Screening(
        id=str(uuid.uuid4()), patient_id=patient.id, organisation_id=organisation.id,
        systolic=None, diastolic=None, symptoms=[],
        clinical_data_ciphertext=encrypt_patient_value(db, patient.id, clinical_data, "screening_clinical_data", settings),
        protocol_version=screening_input.get("protocol_version", "HTN-PROTOCOL-v1"),
        result=classification["result"], red_flag=classification["red_flag"],
    )
    db.add(screening)
    event_type = "SCREEN_POSITIVE" if classification["result"] == "positive" else "SCREEN_NEGATIVE"
    event = record_transition(
        db, patient_id=patient.id, target_state=event_type, actor=actor,
        payload={
            "screening_id": screening.id,
            "systolic": systolic, "diastolic": diastolic, "symptoms": symptoms,
            "protocol_version": screening.protocol_version, "result": screening.result,
            "red_flag": screening.red_flag, "consent_version": consent_version,
            "consent_hash": consent_digest,
        }, settings=settings,
    )
    db.flush()
    return {
        "patient_id": patient.id, "screening_id": screening.id, "result": screening.result,
        "systolic": systolic, "diastolic": diastolic, "urgency": classification["urgency"],
        "red_flag": classification["red_flag"], "red_flag_triggers": classification["red_flag_triggers"],
        "event": event_view(event),
    }


def event_view(event) -> dict[str, Any]:
    return {
        "id": event.id, "seq": event.seq, "event_type": event.event_type,
        "event_hash": event.event_hash, "occurred_at": event.occurred_at,
        "actor_role": event.actor_role,
    }


def _get_screening(db: Session, screening_id: str) -> Screening:
    screening = db.scalar(select(Screening).where(Screening.id == screening_id))
    if screening is None:
        raise CareError("screening_not_found", "Screening was not found", 404)
    return screening


def _get_referral(db: Session, referral_id: str) -> Referral:
    referral = db.scalar(
        select(Referral).options(joinedload(Referral.screening)).where(Referral.id == referral_id)
    )
    if referral is None:
        raise CareError("referral_not_found", "Referral was not found", 404)
    return referral


def _assert_facility(actor: User, referral: Referral) -> None:
    if actor.role == "admin":
        return
    if not actor.organisation_id or actor.organisation_id != referral.facility_id:
        raise CareError("facility_scope_denied", "This referral belongs to a different facility", 403)


def _current_consent(db: Session, patient_id: str, scope: str) -> Consent:
    consent = _active_consent(db, patient_id)
    if consent is None or scope not in (consent.scopes or []):
        raise CareError("active_consent_required", f"Active consent for {scope} is required", 409)
    return consent


def _send_simulated(db: Session, patient_id: str, template_id: str, context: dict, settings: Settings) -> dict:
    consent = _active_consent(db, patient_id)
    if consent is None or "notifications" not in (consent.scopes or []):
        return {"status": "skipped", "reason": "notification_consent_not_granted", "simulated": True}
    contact = db.scalar(select(PatientContact).where(PatientContact.patient_id == patient_id))
    language = contact.preferred_language if contact else "en"
    if language != "en":
        return {
            "status": "skipped", "reason": "localised_template_not_approved",
            "language": language, "simulated": True, "provider_called": False,
        }
    templates = {
        "referral_created": "Your referral to {facility} has been recorded. Urgency: {urgency}. This message is a prototype notification.",
        "appointment_booked": "Your appointment at {facility} is scheduled for {slot_start}. Please contact the facility if you cannot attend.",
        "disposition_returned": "Your clinical visit has been recorded. Next step: {next_step}",
        "followup_due": "A follow-up blood pressure check is due on {due_date}.",
    }
    template = templates.get(template_id)
    if template is None:
        return {"status": "skipped", "reason": "unknown_template", "simulated": True}
    rendered = template.format(**{k: str(v) for k, v in context.items()})
    from app.services.privacy import encrypt_patient_value
    notification_id = str(uuid.uuid4())
    encrypted_rendered = encrypt_patient_value(db, patient_id, rendered, f"notification:{notification_id}", settings)
    notification = Notification(
        id=notification_id, patient_id=patient_id, channel="sms", template_id=template_id, language=language,
        rendered_body=encrypted_rendered, status="simulated",
    )
    db.add(notification)
    db.flush()
    return {"status": "simulated", "notification_id": notification.id, "simulated": True, "provider_called": False}



def _screening_clinical_data(db: Session, screening: Screening, settings: Settings) -> dict[str, Any]:
    if screening.clinical_data_ciphertext:
        from app.services.privacy import decrypt_patient_value
        raw = decrypt_patient_value(db, screening.patient_id, screening.clinical_data_ciphertext, "screening_clinical_data", settings)
        if raw is None:
            raise CareError("screening_data_unavailable", "Clinical screening details are unavailable after key destruction", 410)
        return json.loads(raw)
    # Backward compatibility for early test fixtures/migrated records.
    return {"systolic": screening.systolic, "diastolic": screening.diastolic, "symptoms": screening.symptoms or []}

def _add_unknown_eligibility_record(db: Session, referral: Referral, facility: Organisation) -> EligibilityCheck:
    """Record an honest placeholder for a referral; never imply a live payer check."""
    record = EligibilityCheck(
        referral_id=referral.id,
        decision="unknown",
        adapter="local_mock",
        simulated=True,
        request_summary={
            "resourceType": "CoverageEligibilityRequest",
            "purpose": ["benefits"],
            "facility_id": facility.id,
        },
        response_summary={
            "resourceType": "CoverageEligibilityResponse",
            "outcome": "complete",
            "decision": "unknown",
            "note": "No live NHIA/DHIN integration is configured; no coverage assertion was made.",
        },
    )
    db.add(record)
    return record


def create_referral(db: Session, *, actor: User, screening_id: str, facility_id: str, settings: Settings) -> dict:
    source_org = _require_org_actor(actor, {"pharmacy", "pmv"})
    screening = _get_screening(db, screening_id)
    if screening.organisation_id != source_org.id:
        raise CareError("screening_scope_denied", "You cannot refer a screening created by another organisation", 403)
    if screening.result != "positive":
        raise CareError("screening_not_positive", "Only positive screenings can create a referral", 409)
    consent = _current_consent(db, screening.patient_id, "referral")
    facility = db.get(Organisation, facility_id)
    if facility is None or facility.type != "hospital":
        raise CareError("facility_not_found", "Receiving facility does not exist or is not a hospital", 404)
    # Measurements are decrypted only for this authorised workflow operation.
    screening_values = _screening_clinical_data(db, screening, settings)
    urgency = "emergency" if screening.red_flag else ("urgent" if screening_values["systolic"] >= 160 or screening_values["diastolic"] >= 100 else "routine")
    sla_hours = {"routine": 72, "urgent": 24, "emergency": 4}[urgency]
    referral = Referral(
        id=str(uuid.uuid4()), screening_id=screening.id, facility_id=facility.id,
        urgency=urgency, sla_deadline=utc_now() + timedelta(hours=sla_hours),
        status="REFERRAL_CREATED",
    )
    db.add(referral)
    db.flush()
    _add_unknown_eligibility_record(db, referral, facility)
    event = record_transition(
        db, patient_id=screening.patient_id, target_state="REFERRAL_CREATED", actor=actor,
        payload={
            "facility_id": facility.id, "urgency": urgency, "sla_deadline": referral.sla_deadline.isoformat(),
            "consent_version": consent.version, "consent_hash": consent.payload_hash,
            "eligibility_decision": "unknown", "eligibility_simulated": True,
        }, referral_id=referral.id, settings=settings,
    )
    if screening.red_flag:
        db.add(LoopException(referral_id=referral.id, event_type="RED_FLAG_EMERGENCY", reason_code="screening_red_flag"))
    notification = _send_simulated(db, screening.patient_id, "referral_created", {"facility": facility.name, "urgency": urgency}, settings)
    db.flush()
    return {
        "referral_id": referral.id, "patient_id": screening.patient_id,
        "facility": {"id": facility.id, "name": facility.name}, "urgency": urgency,
        "sla_deadline": referral.sla_deadline, "eligibility": {"decision": "unknown", "simulated": True},
        "notification": notification, "event": event_view(event),
    }


def list_hospital_queue(db: Session, actor: User, settings: Settings) -> list[dict[str, Any]]:
    # Clinicians receive only encounters awaiting a clinician disposition.
    # Hospital operations receive referrals requiring acceptance, booking or attendance.
    if actor.role == "admin":
        visible_statuses = [
            "REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED",
            "APPOINTMENT_MISSED", "PATIENT_REQUESTED_RESCHEDULE", "PATIENT_UNREACHABLE",
            "REFERRAL_DECLINED", "FACILITY_UNAVAILABLE", "CLINICAL_ENCOUNTER_COMPLETED",
        ]
        stmt = select(Referral).options(joinedload(Referral.screening)).where(
            Referral.status.in_(visible_statuses)
        )
    else:
        if actor.role not in {"hospital", "clinician"} or not actor.organisation_id:
            raise CareError("wrong_role", "Hospital queue requires an assigned hospital staff account", 403)
        organisation = actor.organisation
        if organisation is None or organisation.type != "hospital":
            raise CareError("wrong_organisation_type", "Hospital queue requires a hospital organisation", 403)
        visible_statuses = (
            ["CLINICAL_ENCOUNTER_COMPLETED"] if actor.role == "clinician" else
            ["REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED", "APPOINTMENT_MISSED",
             "PATIENT_REQUESTED_RESCHEDULE", "PATIENT_UNREACHABLE", "REFERRAL_DECLINED", "FACILITY_UNAVAILABLE"]
        )
        stmt = select(Referral).options(joinedload(Referral.screening)).where(
            Referral.facility_id == organisation.id,
            Referral.status.in_(visible_statuses),
        )
        if actor.role == "clinician":
            # Clinicians see only encounters explicitly assigned to their account.
            stmt = stmt.where(Referral.owner_user_id == actor.id)
    referrals = db.scalars(stmt.order_by(Referral.sla_deadline.asc())).unique().all()
    now = utc_now()
    output = []
    for r in referrals:
        try:
            values = _screening_clinical_data(db, r.screening, settings)
            details_redacted = False
        except CareError as exc:
            if exc.reason != "screening_data_unavailable":
                raise
            values = {}
            details_redacted = True
        confirmatory_recorded = db.scalar(select(LedgerEvent.id).where(
            LedgerEvent.referral_id == r.id,
            LedgerEvent.event_type == "CONFIRMATORY_TEST_RECORDED",
        ).limit(1)) is not None
        owner = db.get(User, r.owner_user_id) if r.owner_user_id else None
        deadline = r.sla_deadline.replace(tzinfo=timezone.utc) if r.sla_deadline.tzinfo is None else r.sla_deadline
        output.append({
            "id": r.id, "patient_id": r.screening.patient_id, "screening_id": r.screening_id,
            "facility_id": r.facility_id, "systolic": values.get("systolic"),
            "diastolic": values.get("diastolic"), "urgency": r.urgency,
            "details_redacted": details_redacted,
            "status": r.status, "sla_deadline": r.sla_deadline,
            "sla_breached": deadline < now,
            "owner_user_id": r.owner_user_id,
            "owner_role": owner.role if owner else None,
            "unassigned": r.owner_user_id is None,
            "escalated_at": r.escalated_at,
            "confirmatory_test_recorded": confirmatory_recorded,
        })
    return output


def _ensure_hospital_actor(actor: User, referral: Referral) -> None:
    _assert_facility(actor, referral)
    if actor.role not in {"hospital", "admin"}:
        raise CareError("wrong_role", "Only assigned hospital staff can perform this action", 403)


def accept_referral(db: Session, *, actor: User, referral_id: str, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    _current_consent(db, referral.screening.patient_id, "referral")
    if referral.status != "REFERRAL_CREATED":
        raise CareError("invalid_referral_status", "Only newly created referrals can be accepted", 409)
    event = record_transition(db, patient_id=referral.screening.patient_id, target_state="FACILITY_ACCEPTED", actor=actor,
        payload={"facility_id": referral.facility_id, "accepted_at": utc_now().isoformat()},
        referral_id=referral.id, settings=settings)
    referral.status = "FACILITY_ACCEPTED"
    referral.owner_user_id = actor.id
    referral.assigned_at = utc_now()
    referral.escalated_at = None
    db.flush()
    return {"referral_id": referral.id, "event": event_view(event)}


def decline_referral(db: Session, *, actor: User, referral_id: str, reason_code: str, owner_user_id: str | None,
                     redirect_facility_id: str | None, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    if referral.status != "REFERRAL_CREATED":
        raise CareError("invalid_referral_status", "Only newly created referrals can be declined", 409)
    if not reason_code.strip():
        raise CareError("reason_required", "A decline reason is required")
    declined = record_transition(db, patient_id=referral.screening.patient_id, target_state="REFERRAL_DECLINED", actor=actor,
        payload={"reason_code": reason_code.strip(), "owner": owner_user_id or "care_navigator"},
        referral_id=referral.id, settings=settings)
    referral.status = "REFERRAL_DECLINED"
    result: dict[str, Any] = {"referral_id": referral.id, "decline_event": event_view(declined), "redirected_to": None}
    if not redirect_facility_id:
        db.flush()
        return result
    target = db.get(Organisation, redirect_facility_id)
    if target is None or target.type != "hospital" or target.id == referral.facility_id:
        raise CareError("invalid_redirect_facility", "Choose a different registered hospital facility")
    redirected = record_transition(db, patient_id=referral.screening.patient_id, target_state="REFERRAL_REDIRECTED", actor=actor,
        payload={"reason_code": reason_code.strip(), "previous_facility_id": referral.facility_id, "facility_id": target.id},
        referral_id=referral.id, settings=settings)
    sla_hours = {"routine": 72, "urgent": 24, "emergency": 4}[referral.urgency]
    new_referral = Referral(
        id=str(uuid.uuid4()), screening_id=referral.screening_id, facility_id=target.id,
        urgency=referral.urgency, sla_deadline=utc_now() + timedelta(hours=sla_hours), status="REFERRAL_CREATED",
    )
    db.add(new_referral)
    db.flush()
    _add_unknown_eligibility_record(db, new_referral, target)
    consent = _current_consent(db, referral.screening.patient_id, "referral")
    created = record_transition(db, patient_id=referral.screening.patient_id, target_state="REFERRAL_CREATED", actor=actor,
        payload={"facility_id": target.id, "urgency": referral.urgency,
                 "consent_version": consent.version, "consent_hash": consent.payload_hash,
                 "previous_facility_id": referral.facility_id},
        referral_id=new_referral.id, settings=settings)
    result.update({"redirected_to": {"id": target.id, "name": target.name},
                   "new_referral_id": new_referral.id,
                   "redirect_event": event_view(redirected), "new_referral_event": event_view(created)})
    db.flush()
    return result


def redirect_declined_referral(db: Session, *, actor: User, referral_id: str,
                                new_facility_id: str, settings: Settings) -> dict[str, Any]:
    """Recover a declined/unavailable referral by creating a new owned facility handoff."""
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    if referral.status not in {"REFERRAL_DECLINED", "FACILITY_UNAVAILABLE"}:
        raise CareError("invalid_referral_status", "Only declined or unavailable referrals can be redirected", 409)
    target = db.get(Organisation, new_facility_id)
    if target is None or target.type != "hospital" or target.id == referral.facility_id:
        raise CareError("invalid_redirect_facility", "Choose a different registered hospital facility")
    consent = _current_consent(db, referral.screening.patient_id, "referral")
    reason = "receiving_facility_declined"
    redirected = record_transition(
        db, patient_id=referral.screening.patient_id, target_state="REFERRAL_REDIRECTED", actor=actor,
        payload={"reason_code": reason, "previous_facility_id": referral.facility_id,
                 "facility_id": target.id}, referral_id=referral.id, settings=settings,
    )
    sla_hours = {"routine": 72, "urgent": 24, "emergency": 4}[referral.urgency]
    new_referral = Referral(
        id=str(uuid.uuid4()), screening_id=referral.screening_id, facility_id=target.id,
        urgency=referral.urgency, sla_deadline=utc_now() + timedelta(hours=sla_hours),
        status="REFERRAL_CREATED",
    )
    db.add(new_referral)
    db.flush()
    _add_unknown_eligibility_record(db, new_referral, target)
    created = record_transition(
        db, patient_id=referral.screening.patient_id, target_state="REFERRAL_CREATED", actor=actor,
        payload={"facility_id": target.id, "urgency": referral.urgency,
                 "consent_version": consent.version, "consent_hash": consent.payload_hash,
                 "previous_facility_id": referral.facility_id},
        referral_id=new_referral.id, settings=settings,
    )
    notification = _send_simulated(db, referral.screening.patient_id, "referral_created",
                                   {"facility": target.name, "urgency": referral.urgency}, settings)
    db.flush()
    return {"previous_referral_id": referral.id, "new_referral_id": new_referral.id,
            "facility": {"id": target.id, "name": target.name},
            "redirect_event": event_view(redirected), "new_referral_event": event_view(created),
            "notification": notification}


def book_appointment(db: Session, *, actor: User, referral_id: str, slot_start: datetime, slot_end: datetime, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    _current_consent(db, referral.screening.patient_id, "referral")
    if referral.status not in {"FACILITY_ACCEPTED", "APPOINTMENT_MISSED", "PATIENT_REQUESTED_RESCHEDULE"}:
        raise CareError("invalid_referral_status", "Referral must be accepted or awaiting rebooking before an appointment is booked", 409)
    if slot_start.tzinfo is None or slot_end.tzinfo is None or slot_end <= slot_start:
        raise CareError("invalid_appointment_time", "Appointment times must be timezone-aware and end after start")
    appointment = Appointment(referral_id=referral.id, slot_start=slot_start, slot_end=slot_end, status="booked")
    db.add(appointment)
    db.flush()
    event = record_transition(db, patient_id=referral.screening.patient_id, target_state="APPOINTMENT_BOOKED", actor=actor,
        payload={"facility_id": referral.facility_id, "slot_start": slot_start.isoformat(),
                 "slot_end": slot_end.isoformat(), "appointment_id": appointment.id},
        referral_id=referral.id, settings=settings)
    referral.status = "APPOINTMENT_BOOKED"
    facility = db.get(Organisation, referral.facility_id)
    _send_simulated(db, referral.screening.patient_id, "appointment_booked",
                    {"facility": facility.name if facility else "the hospital", "slot_start": slot_start.isoformat()}, settings)
    db.flush()
    return {"referral_id": referral.id, "appointment_id": appointment.id, "event": event_view(event)}


def mark_appointment_missed(db: Session, *, actor: User, referral_id: str, reason_code: str, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    _current_consent(db, referral.screening.patient_id, "referral")
    if referral.status != "APPOINTMENT_BOOKED":
        raise CareError("invalid_referral_status", "Only a booked appointment can be marked missed", 409)
    appointment = db.scalar(select(Appointment).where(
        Appointment.referral_id == referral.id, Appointment.status == "booked"
    ).order_by(Appointment.created_at.desc()).with_for_update())
    if appointment is None:
        raise CareError("appointment_not_found", "No booked appointment exists", 409)
    event = record_transition(
        db, patient_id=referral.screening.patient_id, target_state="APPOINTMENT_MISSED", actor=actor,
        payload={"reason_code": reason_code.strip(), "owner": "care_navigator", "appointment_id": appointment.id},
        referral_id=referral.id, settings=settings,
    )
    appointment.status = "missed"
    referral.status = "APPOINTMENT_MISSED"
    db.flush()
    return {"referral_id": referral.id, "appointment_id": appointment.id, "event": event_view(event)}


def mark_patient_unreachable(db: Session, *, actor: User, referral_id: str, reason_code: str, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    if referral.status not in {"REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED"}:
        raise CareError("invalid_referral_status", "This referral cannot be marked unreachable in its current state", 409)
    event = record_transition(
        db, patient_id=referral.screening.patient_id, target_state="PATIENT_UNREACHABLE", actor=actor,
        payload={"reason_code": reason_code.strip(), "owner": "care_navigator"},
        referral_id=referral.id, settings=settings,
    )
    appointment = db.scalar(select(Appointment).where(
        Appointment.referral_id == referral.id, Appointment.status == "booked"
    ).order_by(Appointment.created_at.desc()))
    if appointment is not None:
        appointment.status = "cancelled"
    referral.status = "PATIENT_UNREACHABLE"
    db.flush()
    return {"referral_id": referral.id, "event": event_view(event)}


def patient_decline_referral(db: Session, *, actor: User, referral_id: str, reason_code: str, settings: Settings) -> dict:
    if actor.role != "patient" or not actor.patient_id:
        raise CareError("patient_account_required", "A patient account is required", 403)
    referral = _get_referral(db, referral_id)
    if referral.screening.patient_id != actor.patient_id:
        raise CareError("patient_scope_denied", "You can only decline your own referral", 403)
    if referral.status not in {"REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED"}:
        raise CareError("invalid_referral_status", "This referral can no longer be declined", 409)
    event = record_transition(
        db, patient_id=actor.patient_id, target_state="PATIENT_DECLINED", actor=actor,
        payload={"reason_code": reason_code.strip(), "owner": "patient"},
        referral_id=referral.id, settings=settings,
    )
    appointment = db.scalar(select(Appointment).where(
        Appointment.referral_id == referral.id, Appointment.status == "booked"
    ).order_by(Appointment.created_at.desc()))
    if appointment is not None:
        appointment.status = "cancelled"
    referral.status = "PATIENT_DECLINED"
    db.flush()
    return {"referral_id": referral.id, "event": event_view(event)}


def patient_request_reschedule(db: Session, *, actor: User, referral_id: str, reason_code: str, settings: Settings) -> dict:
    if actor.role != "patient" or not actor.patient_id:
        raise CareError("patient_account_required", "A patient account is required", 403)
    referral = _get_referral(db, referral_id)
    if referral.screening.patient_id != actor.patient_id:
        raise CareError("patient_scope_denied", "You can only reschedule your own referral", 403)
    if referral.status != "APPOINTMENT_BOOKED":
        raise CareError("invalid_referral_status", "Only a booked appointment can be rescheduled", 409)
    event = record_transition(
        db, patient_id=actor.patient_id, target_state="PATIENT_REQUESTED_RESCHEDULE", actor=actor,
        payload={"reason_code": reason_code.strip(), "owner": "care_navigator"},
        referral_id=referral.id, settings=settings,
    )
    appointment = db.scalar(select(Appointment).where(
        Appointment.referral_id == referral.id, Appointment.status == "booked"
    ).order_by(Appointment.created_at.desc()))
    if appointment is None:
        raise CareError("appointment_not_found", "No booked appointment exists", 409)
    appointment.status = "cancelled"
    referral.status = "PATIENT_REQUESTED_RESCHEDULE"
    db.flush()
    return {"referral_id": referral.id, "event": event_view(event)}


def attest_attendance(db: Session, *, actor: User, referral_id: str, clinician_id: str, notes: str, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _ensure_hospital_actor(actor, referral)
    _current_consent(db, referral.screening.patient_id, "referral")
    if referral.status != "APPOINTMENT_BOOKED":
        raise CareError("invalid_referral_status", "A booked appointment is required before attendance can be attested", 409)
    clinician = db.get(User, clinician_id)
    if clinician is None or not clinician.is_active or clinician.role != "clinician" or clinician.organisation_id != referral.facility_id:
        raise CareError("invalid_clinician", "Clinician must be active and assigned to the receiving hospital", 422)
    appointment = db.scalar(select(Appointment).where(Appointment.referral_id == referral.id, Appointment.status == "booked").order_by(Appointment.created_at.desc()))
    if appointment is None:
        raise CareError("appointment_not_found", "No booked appointment exists", 409)
    from app.services.privacy import encrypt_patient_value
    encrypted_notes = encrypt_patient_value(db, referral.screening.patient_id, notes.strip(), "encounter_notes", settings) if notes.strip() else None
    encounter = Encounter(appointment_id=appointment.id, clinician_id=clinician.id, attended_at=utc_now(), notes=encrypted_notes)
    db.add(encounter)
    db.flush()
    event = record_transition(db, patient_id=referral.screening.patient_id, target_state="CLINICAL_ENCOUNTER_COMPLETED", actor=actor,
        payload={"attended": True, "appointment_id": appointment.id, "encounter_id": encounter.id, "clinician_id": clinician.id},
        referral_id=referral.id, settings=settings)
    appointment.status = "attended"
    referral.status = "CLINICAL_ENCOUNTER_COMPLETED"
    referral.owner_user_id = clinician.id
    referral.assigned_at = utc_now()
    db.flush()
    return {"referral_id": referral.id, "encounter_id": encounter.id, "event": event_view(event)}


def return_disposition(db: Session, *, actor: User, referral_id: str, outcome: str, next_step: str, settings: Settings) -> dict:
    if actor.role != "clinician" or not actor.organisation_id:
        raise CareError("wrong_role", "Only an assigned clinician can submit a clinical disposition", 403)
    referral = _get_referral(db, referral_id)
    _current_consent(db, referral.screening.patient_id, "referral")
    if actor.organisation_id != referral.facility_id:
        raise CareError("facility_scope_denied", "You are not assigned to this referral's hospital", 403)
    if referral.status != "CLINICAL_ENCOUNTER_COMPLETED":
        raise CareError("invalid_referral_status", "Attendance must be attested before disposition", 409)
    encounter = db.scalar(select(Encounter).join(Appointment).where(Appointment.referral_id == referral.id).order_by(Encounter.created_at.desc()))
    if encounter is None or encounter.clinician_id != actor.id:
        raise CareError("encounter_assignment_mismatch", "Only the clinician recorded on the encounter may submit its disposition", 403)
    confirmation = db.scalar(select(LedgerEvent).where(
        LedgerEvent.referral_id == referral.id,
        LedgerEvent.event_type == "CONFIRMATORY_TEST_RECORDED",
    ).order_by(LedgerEvent.seq.desc()).limit(1))
    if confirmation is None:
        raise CareError("confirmatory_assessment_required", "Record the confirmatory assessment or document why it was not indicated before returning the disposition", 409)
    if not outcome.strip() or not next_step.strip():
        raise CareError("disposition_required", "Clinical outcome and next step are required")
    signed_at = utc_now()
    from app.services.privacy import encrypt_patient_value
    encrypted_outcome = encrypt_patient_value(db, referral.screening.patient_id, outcome.strip(), "disposition_outcome", settings)
    encrypted_next_step = encrypt_patient_value(db, referral.screening.patient_id, next_step.strip(), "disposition_next_step", settings)
    disposition = ClinicalDisposition(encounter_id=encounter.id, clinician_id=actor.id, outcome=encrypted_outcome, next_step=encrypted_next_step, signed_at=signed_at)
    db.add(disposition)
    db.flush()
    event = record_transition(db, patient_id=referral.screening.patient_id, target_state="CLINICAL_DISPOSITION_RETURNED", actor=actor,
        payload={"clinician_id": actor.id, "outcome": outcome.strip(), "next_step": next_step.strip(),
                 "disposition_id": disposition.id, "encounter_id": encounter.id},
        referral_id=referral.id, settings=settings)
    referral.status = "CLINICAL_DISPOSITION_RETURNED"
    _send_simulated(db, referral.screening.patient_id, "disposition_returned", {"next_step": next_step.strip()}, settings)
    db.flush()
    return {"referral_id": referral.id, "disposition_id": disposition.id, "event": event_view(event)}


def schedule_followup(db: Session, *, actor: User, patient_id: str, due_date: datetime, plan_type: str, settings: Settings) -> dict:
    if actor.role != "clinician":
        raise CareError("wrong_role", "Only clinicians may schedule a follow-up", 403)
    if due_date.tzinfo is None or due_date <= utc_now():
        raise CareError("invalid_due_date", "Follow-up due date must be a future timezone-aware timestamp")
    if plan_type not in {"7_day", "30_day", "repeat_assessment", "bp_control_check"}:
        raise CareError("invalid_plan_type", "Unsupported follow-up plan type")
    _require_patient_access(db, actor, patient_id)
    _current_consent(db, patient_id, "follow_up")
    plan = FollowUpPlan(patient_id=patient_id, due_date=due_date, plan_type=plan_type, status="pending")
    db.add(plan)
    db.flush()
    event = record_transition(db, patient_id=patient_id, target_state="FOLLOWUP_DUE", actor=actor,
        payload={"due_date": due_date.isoformat(), "followup_type": plan_type, "plan_id": plan.id}, settings=settings)
    _send_simulated(db, patient_id, "followup_due", {"due_date": due_date.date().isoformat()}, settings)
    db.flush()
    return {"plan_id": plan.id, "due_date": due_date, "event": event_view(event)}


def record_followup_assessment(db: Session, *, actor: User, patient_id: str, systolic: int, diastolic: int,
                               bp_controlled: bool | None, settings: Settings) -> dict:
    if actor.role not in {"pharmacy", "pmv"}:
        raise CareError("wrong_role", "A pharmacy or PMV staff member must record a repeat blood pressure assessment", 403)
    _require_org_actor(actor, {"pharmacy", "pmv"})
    _require_patient_access(db, actor, patient_id)
    _current_consent(db, patient_id, "follow_up")
    _bp_valid(systolic, diastolic)
    latest_plan = db.scalar(select(FollowUpPlan).where(FollowUpPlan.patient_id == patient_id, FollowUpPlan.status == "pending").order_by(FollowUpPlan.due_date.asc()))
    if latest_plan is None:
        raise CareError("followup_not_scheduled", "No pending follow-up plan exists", 409)
    latest_state = latest_workflow_state(db, patient_id)
    if latest_state is None:
        raise CareError("care_history_missing", "No care history exists", 409)
    target_state = "REPEAT_ASSESSMENT" if latest_state == "FOLLOWUP_DUE" else None
    if target_state is None:
        raise CareError("invalid_followup_state", "Patient is not currently due for a repeat assessment", 409)
    payload = {"systolic": systolic, "diastolic": diastolic, "followup_plan_id": latest_plan.id}
    event = record_transition(db, patient_id=patient_id, target_state=target_state, actor=actor, payload=payload, settings=settings)
    latest_plan.status = "met"
    db.flush()
    return {"patient_id": patient_id, "systolic": systolic, "diastolic": diastolic, "event": event_view(event)}


def record_bp_control(db: Session, *, actor: User, patient_id: str, systolic: int, diastolic: int,
                      controlled: bool, settings: Settings) -> dict:
    if actor.role not in {"pharmacy", "pmv"}:
        raise CareError("wrong_role", "A pharmacy or PMV staff member must record BP control", 403)
    _require_org_actor(actor, {"pharmacy", "pmv"})
    _bp_valid(systolic, diastolic)
    _require_patient_access(db, actor, patient_id)
    _current_consent(db, patient_id, "follow_up")
    latest_state = latest_workflow_state(db, patient_id)
    if latest_state != "REPEAT_ASSESSMENT":
        raise CareError("invalid_followup_state", "A repeat assessment must be recorded first", 409)
    event = record_transition(db, patient_id=patient_id, target_state="BP_CONTROL_RECORDED", actor=actor,
        payload={"systolic": systolic, "diastolic": diastolic, "bp_controlled": bool(controlled)}, settings=settings)
    db.flush()
    return {"patient_id": patient_id, "bp_controlled": controlled, "event": event_view(event)}



def record_confirmatory_assessment(
    db: Session, *, actor: User, referral_id: str, method: str,
    systolic: int | None, diastolic: int | None, note: str, settings: Settings,
) -> dict[str, Any]:
    """Record a clinician-governed confirmatory step without changing workflow state."""
    if actor.role != "clinician" or not actor.organisation_id:
        raise CareError("wrong_role", "Only the assigned clinician can record a confirmatory assessment", 403)
    referral = _get_referral(db, referral_id)
    _current_consent(db, referral.screening.patient_id, "referral")
    if referral.status != "CLINICAL_ENCOUNTER_COMPLETED":
        raise CareError("invalid_referral_status", "Confirmatory assessment follows an attended clinical encounter", 409)
    if actor.organisation_id != referral.facility_id:
        raise CareError("facility_scope_denied", "You are not assigned to this referral's hospital", 403)
    encounter = db.scalar(
        select(Encounter).join(Appointment).where(Appointment.referral_id == referral.id)
        .order_by(Encounter.created_at.desc()).limit(1)
    )
    if encounter is None or encounter.clinician_id != actor.id:
        raise CareError("encounter_assignment_mismatch", "Only the clinician assigned to this encounter may record the assessment", 403)
    if method not in {"repeat_office", "home_monitoring", "ambulatory_monitoring", "not_indicated"}:
        raise CareError("invalid_confirmatory_method", "Choose a recognised confirmatory assessment method")
    payload: dict[str, Any] = {"method": method, "encounter_id": encounter.id, "note": note.strip()[:1000]}
    if method == "not_indicated":
        if len(note.strip()) < 5:
            raise CareError("confirmatory_reason_required", "Document why confirmatory testing was not indicated")
    else:
        if systolic is None or diastolic is None:
            raise CareError("confirmatory_reading_required", "Enter systolic and diastolic values for the recorded assessment")
        _bp_valid(systolic, diastolic)
        payload.update({"systolic": systolic, "diastolic": diastolic})
    existing = db.scalar(select(LedgerEvent.id).where(
        LedgerEvent.referral_id == referral.id,
        LedgerEvent.event_type == "CONFIRMATORY_TEST_RECORDED",
    ).limit(1))
    if existing:
        raise CareError("confirmatory_assessment_exists", "A confirmatory assessment has already been recorded for this referral", 409)
    event = append_event(
        db, patient_id=referral.screening.patient_id, event_type="CONFIRMATORY_TEST_RECORDED",
        actor=actor, payload=payload, referral_id=referral.id, settings=settings,
    )
    db.flush()
    return {"referral_id": referral.id, "method": method, "event": event_view(event)}


def assign_referral_owner(db: Session, *, actor: User, referral_id: str, owner_user_id: str,
                          settings: Settings) -> dict[str, Any]:
    referral = _get_referral(db, referral_id)
    if actor.role != "admin":
        _ensure_hospital_actor(actor, referral)
    owner = db.get(User, owner_user_id)
    if owner is None or not owner.is_active or owner.organisation_id != referral.facility_id or owner.role not in {"hospital", "clinician"}:
        raise CareError("invalid_referral_owner", "Owner must be active hospital staff or a clinician in the receiving facility", 422)
    if referral.status in {"CLINICAL_DISPOSITION_RETURNED", "PATIENT_DECLINED"}:
        raise CareError("referral_closed", "A closed referral cannot be reassigned", 409)
    previous_owner = referral.owner_user_id
    referral.owner_user_id = owner.id
    referral.assigned_at = utc_now()
    event = append_event(
        db, patient_id=referral.screening.patient_id, event_type="REFERRAL_OWNER_ASSIGNED", actor=actor,
        payload={"referral_id": referral.id, "previous_owner_user_id": previous_owner,
                 "owner_user_id": owner.id}, referral_id=referral.id, settings=settings,
    )
    db.flush()
    return {"referral_id": referral.id, "owner_user_id": owner.id, "event": event_view(event)}


def process_overdue_referrals(db: Session, *, now: datetime | None = None, limit: int = 500) -> dict[str, Any]:
    """Idempotently create operator-owned SLA exceptions; invoke from a scheduler/CLI."""
    moment = now or utc_now()
    open_statuses = {
        "REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED",
        "APPOINTMENT_MISSED", "PATIENT_REQUESTED_RESCHEDULE", "PATIENT_UNREACHABLE",
        "REFERRAL_DECLINED", "FACILITY_UNAVAILABLE", "CLINICAL_ENCOUNTER_COMPLETED",
    }
    rows = db.scalars(select(Referral).where(
        Referral.status.in_(open_statuses), Referral.sla_deadline < moment,
        Referral.escalated_at.is_(None),
    ).order_by(Referral.sla_deadline.asc()).limit(limit).with_for_update(skip_locked=True)).all()
    escalated: list[str] = []
    for referral in rows:
        already = db.scalar(select(LoopException.id).where(
            LoopException.referral_id == referral.id,
            LoopException.event_type == "REFERRAL_SLA_BREACHED",
        ).limit(1))
        if already:
            referral.escalated_at = referral.escalated_at or moment
            continue
        db.add(LoopException(
            referral_id=referral.id, event_type="REFERRAL_SLA_BREACHED",
            reason_code="sla_deadline_exceeded", owner_user_id=referral.owner_user_id,
            note="SLA deadline exceeded; operator review required.", created_at=moment,
        ))
        referral.escalated_at = moment
        escalated.append(referral.id)
    db.flush()
    return {"checked": len(rows), "escalated": escalated, "escalated_count": len(escalated), "checked_at": moment}


def list_operational_attention(db: Session, *, actor: User) -> dict[str, Any]:
    if actor.role == "admin":
        stmt = select(LoopException).where(LoopException.event_type == "REFERRAL_SLA_BREACHED", LoopException.resolved_at.is_(None))
        unassigned_stmt = select(Referral).where(Referral.status.notin_(["CLINICAL_DISPOSITION_RETURNED", "PATIENT_DECLINED"]), Referral.owner_user_id.is_(None))
    elif actor.role == "hospital" and actor.organisation_id:
        stmt = select(LoopException).join(Referral).where(
            LoopException.event_type == "REFERRAL_SLA_BREACHED", LoopException.resolved_at.is_(None),
            Referral.facility_id == actor.organisation_id,
        )
        unassigned_stmt = select(Referral).where(Referral.facility_id == actor.organisation_id,
            Referral.status.notin_(["CLINICAL_DISPOSITION_RETURNED", "PATIENT_DECLINED"]), Referral.owner_user_id.is_(None))
    else:
        raise CareError("wrong_role", "Operational attention is available to administrators and hospital operators", 403)
    exceptions = db.scalars(stmt.order_by(LoopException.created_at.asc())).all()
    unassigned = db.scalars(unassigned_stmt.order_by(Referral.sla_deadline.asc())).all()
    return {
        "overdue": [{"id": x.id, "referral_id": x.referral_id, "reason_code": x.reason_code,
                     "owner_user_id": x.owner_user_id, "created_at": x.created_at} for x in exceptions],
        "unassigned": [{"id": x.id, "facility_id": x.facility_id, "status": x.status,
                        "sla_deadline": x.sla_deadline} for x in unassigned],
    }


def _require_patient_access(db: Session, actor: User, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise CareError("patient_not_found", "Patient was not found", 404)
    if actor.role == "admin":
        return patient
    if actor.role == "patient":
        if actor.patient_id != patient_id:
            raise CareError("patient_scope_denied", "You can only access your own care record", 403)
        return patient
    if actor.organisation_id is None:
        raise CareError("organisation_required", "Your account is not assigned to an organisation", 403)
    if actor.role in {"hospital", "clinician"}:
        allowed = db.scalar(select(Referral.id).join(Screening).where(
            Screening.patient_id == patient_id, Referral.facility_id == actor.organisation_id
        ).limit(1))
    else:
        allowed = db.scalar(select(Screening.id).where(
            Screening.patient_id == patient_id, Screening.organisation_id == actor.organisation_id
        ).limit(1))
    if allowed is None:
        raise CareError("patient_scope_denied", "You do not have an organisational relationship with this patient", 403)
    return patient


def patient_receipt(db: Session, *, actor: User, patient_id: str, settings: Settings) -> dict[str, Any]:
    _require_patient_access(db, actor, patient_id)
    verification = verify_patient_chain(db, patient_id)
    from app.db.models import LedgerEvent
    rows = db.scalars(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.asc())).all()
    headings = {
        "SCREEN_POSITIVE": "Your blood pressure screening was positive",
        "SCREEN_NEGATIVE": "Your blood pressure screening was recorded",
        "REFERRAL_CREATED": "A referral was created",
        "FACILITY_ACCEPTED": "The hospital accepted your referral",
        "APPOINTMENT_BOOKED": "Your appointment was booked",
        "CLINICAL_ENCOUNTER_COMPLETED": "Your hospital attendance was recorded",
        "CLINICAL_DISPOSITION_RETURNED": "Your clinician returned a disposition",
        "CONFIRMATORY_TEST_RECORDED": "Your confirmatory assessment was recorded",
        "REFERRAL_DECLINED": "A hospital declined the referral",
        "REFERRAL_REDIRECTED": "The referral was redirected",
        "FOLLOWUP_DUE": "A follow-up is scheduled",
        "REPEAT_ASSESSMENT": "A repeat blood pressure assessment was recorded",
        "BP_CONTROL_RECORDED": "Blood pressure control status was recorded",
        "PATIENT_ACKNOWLEDGED": "You acknowledged this receipt",
        "CONSENT_REVOKED": "Consent was revoked",
    }
    from app.services.privacy import decrypt_ledger_payload
    rendered_events = []
    for row in rows:
        payload = decrypt_ledger_payload(db, patient_id, row.payload or {}, settings)
        rendered_events.append({
            "seq": row.seq, "event_type": row.event_type,
            "headline": headings.get(row.event_type, "A care update was recorded"),
            "occurred_at": row.occurred_at, "actor_role": row.actor_role,
            "event_hash": row.event_hash,
            "payload": payload if payload is not None else None,
            "details_redacted": payload is None,
        })
    db.add(AccessLog(actor_id=actor.id, resource_type="patient_receipt", resource_id=patient_id, purpose="care_receipt_view"))
    return {
        "patient_id": patient_id,
        "verified": verification["ok"],
        "verification": verification,
        "events": rendered_events,
    }


def acknowledge_patient_receipt(db: Session, *, actor: User, settings: Settings) -> dict:
    if actor.role != "patient" or not actor.patient_id:
        raise CareError("patient_account_required", "A patient account is required", 403)
    _require_patient_access(db, actor, actor.patient_id)
    event = append_event(
        db, patient_id=actor.patient_id, event_type="PATIENT_ACKNOWLEDGED", actor=actor,
        payload={"acknowledged_at": utc_now().isoformat(), "receipt_version": "1"},
        settings=settings,
    )
    return {"patient_id": actor.patient_id, "event": event_view(event)}


def revoke_consent(db: Session, *, actor: User, patient_id: str, settings: Settings, reason: str) -> dict:
    if actor.role != "admin" and not (actor.role == "patient" and actor.patient_id == patient_id):
        raise CareError("consent_revocation_forbidden", "Only the patient or an administrator can revoke consent", 403)
    _require_patient_access(db, actor, patient_id)
    consent = _active_consent(db, patient_id)
    if consent is None:
        raise CareError("no_active_consent", "No active consent exists", 409)
    consent.revoked_at = utc_now()
    data_key = db.get(PatientDataKey, patient_id)
    shredded = False
    if data_key is None:
        data_key = PatientDataKey(patient_id=patient_id, wrapped_key="", shredded_at=utc_now())
        db.add(data_key)
        shredded = True
    elif data_key.shredded_at is None:
        data_key.wrapped_key = ""
        data_key.shredded_at = utc_now()
        shredded = True
    # Replace lookup value so the prior phone can no longer be correlated to this patient.
    contacts = db.scalars(select(PatientContact).where(PatientContact.patient_id == patient_id)).all()
    for contact in contacts:
        contact.phone_lookup_hash = secrets.token_hex(32)
    patient = db.get(Patient, patient_id)
    if patient is not None:
        patient.display_name = None
        patient.display_name_ciphertext = None
    event = append_event(db, patient_id=patient_id, event_type="CONSENT_REVOKED", actor=actor,
        payload={"consent_version": consent.version, "reason_code": reason[:80], "contact_key_shredded": shredded}, settings=settings)
    # Append the signed revocation event before disabling and pseudonymising the patient account.
    patient_users = db.scalars(select(User).where(User.patient_id == patient_id)).all()
    for patient_user in patient_users:
        erased_email = f"erased-{patient_user.id}@erased.invalid"
        patient_user.email = erased_email
        patient_user.email_normalized = erased_email
        patient_user.email_ciphertext = None
        patient_user.is_active = False
    db.flush()
    return {"patient_id": patient_id, "revoked": True, "contact_key_shredded": shredded, "event": event_view(event)}


def _otp_digest(code: str, patient_id: str, settings: Settings) -> str:
    return hmac.new(settings.secret_key.encode(), f"patient-otp:{patient_id}:{code}".encode(), hashlib.sha256).hexdigest()


def request_patient_otp(db: Session, *, phone: str, settings: Settings) -> dict[str, Any]:
    normalized = _phone_normalize(phone)
    contact = db.scalar(select(PatientContact).where(PatientContact.phone_lookup_hash == _phone_hash(normalized, settings)))
    # Avoid revealing whether a number is registered.
    if contact is None:
        return {"accepted": True, "message": "If the number is registered, a code will be issued."}
    data_key = db.get(PatientDataKey, contact.patient_id)
    if data_key is None or data_key.shredded_at:
        return {"accepted": True, "message": "If the number is registered, a code will be issued."}
    patient = db.get(Patient, contact.patient_id)
    if patient is None:
        return {"accepted": True, "message": "If the number is registered, a code will be issued."}
    recent = db.scalar(select(PatientOTP).where(
        PatientOTP.patient_id == patient.id,
        PatientOTP.created_at >= utc_now() - timedelta(seconds=60),
    ).order_by(PatientOTP.created_at.desc()))
    if recent is not None:
        return {"accepted": True, "message": "If the number is registered, a code will be issued."}
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.query(PatientOTP).filter(PatientOTP.patient_id == patient.id, PatientOTP.consumed_at.is_(None)).update(
        {"consumed_at": utc_now()}, synchronize_session=False
    )
    otp = PatientOTP(patient_id=patient.id, code_digest=_otp_digest(code, patient.id, settings),
                     expires_at=utc_now() + timedelta(minutes=OTP_TTL_MINUTES))
    db.add(otp)
    # Delivery is not wired. Development-only code return is explicitly non-production.
    result: dict[str, Any] = {"accepted": True, "message": "If the number is registered, a code will be issued."}
    if settings.app_env.lower() in {"development", "test"}:
        result["development_code"] = code
        result["development_only"] = True
    db.flush()
    return result


def verify_patient_otp(db: Session, *, phone: str, code: str, settings: Settings) -> Patient | None:
    normalized = _phone_normalize(phone)
    contact = db.scalar(select(PatientContact).where(PatientContact.phone_lookup_hash == _phone_hash(normalized, settings)))
    if contact is None:
        return None
    now = utc_now()
    otp = db.scalar(select(PatientOTP).where(PatientOTP.patient_id == contact.patient_id, PatientOTP.consumed_at.is_(None))
                    .order_by(PatientOTP.created_at.desc()).with_for_update())
    if otp is None:
        return None
    expires_at = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now or otp.attempts >= OTP_MAX_ATTEMPTS:
        return None
    if not hmac.compare_digest(otp.code_digest, _otp_digest(code, contact.patient_id, settings)):
        otp.attempts += 1
        return None
    otp.consumed_at = now
    patient = db.get(Patient, contact.patient_id)
    return patient


def create_case_message(db: Session, *, actor: User, referral_id: str, body: str, settings: Settings) -> dict:
    referral = _get_referral(db, referral_id)
    _current_consent(db, referral.screening.patient_id, "referral")
    if actor.role not in {"pharmacy", "pmv", "hospital", "clinician", "admin"}:
        raise CareError("wrong_role", "This account cannot access the clinical consultation thread", 403)
    if actor.role != "admin" and actor.organisation_id not in {referral.facility_id, referral.screening.organisation_id}:
        raise CareError("referral_scope_denied", "You are not part of this referral's care organisations", 403)
    clean = body.strip()
    if not clean or len(clean) > 2000:
        raise CareError("invalid_message", "Message must contain 1 to 2,000 characters")
    from app.services.privacy import encrypt_patient_value
    encrypted_body = encrypt_patient_value(db, referral.screening.patient_id, clean, "case_message", settings)
    message = CaseMessage(referral_id=referral.id, author_user_id=actor.id, body=encrypted_body)
    db.add(message)
    db.flush()
    event = append_event(db, patient_id=referral.screening.patient_id, event_type="CONSULT_MESSAGE", actor=actor,
        payload={"referral_id": referral.id, "message_id": message.id, "body_sha256": hashlib.sha256(clean.encode()).hexdigest()},
        referral_id=referral.id, settings=settings)
    db.flush()
    return {"message_id": message.id, "event": event_view(event)}


def list_case_messages(db: Session, *, actor: User, referral_id: str, settings: Settings) -> list[dict]:
    referral = _get_referral(db, referral_id)
    if actor.role != "admin" and actor.organisation_id not in {referral.facility_id, referral.screening.organisation_id}:
        raise CareError("referral_scope_denied", "You are not part of this referral's care organisations", 403)
    messages = db.scalars(select(CaseMessage).where(CaseMessage.referral_id == referral_id).order_by(CaseMessage.created_at.asc())).all()
    from app.services.privacy import decrypt_patient_value
    db.add(AccessLog(actor_id=actor.id, resource_type="referral_messages", resource_id=referral_id,
                     purpose="care_coordination_message_view", occurred_at=utc_now()))
    output = []
    for message in messages:
        body = decrypt_patient_value(db, referral.screening.patient_id, message.body, "case_message", settings)
        output.append({"id": message.id, "author_user_id": message.author_user_id,
                       "created_at": message.created_at,
                       "body": body if body is not None else "[message redacted after consent revocation]"})
    return output


def list_red_flags(db: Session, actor: User) -> list[dict]:
    if actor.role == "admin":
        stmt = select(LoopException).where(LoopException.event_type == "RED_FLAG_EMERGENCY", LoopException.resolved_at.is_(None))
    elif actor.role in {"hospital", "clinician"} and actor.organisation_id:
        stmt = select(LoopException).join(Referral).where(
            LoopException.event_type == "RED_FLAG_EMERGENCY", LoopException.resolved_at.is_(None),
            Referral.facility_id == actor.organisation_id,
        )
    else:
        raise CareError("wrong_role", "Only hospital staff can review emergency flags", 403)
    rows = db.scalars(stmt.order_by(LoopException.created_at.desc())).all()
    return [{"id": a.id, "referral_id": a.referral_id, "reason_code": a.reason_code,
             "acknowledged_at": a.acknowledged_at, "resolved_at": a.resolved_at, "created_at": a.created_at} for a in rows]


def acknowledge_red_flag(db: Session, *, actor: User, alert_id: str, note: str, settings: Settings) -> dict:
    alert = db.get(LoopException, alert_id)
    if alert is None or alert.event_type != "RED_FLAG_EMERGENCY" or alert.resolved_at is not None:
        raise CareError("alert_not_found", "Open emergency alert was not found", 404)
    referral = _get_referral(db, alert.referral_id)
    _ensure_hospital_actor(actor, referral)
    if alert.acknowledged_at is not None:
        raise CareError("already_acknowledged", "This alert has already been acknowledged", 409)
    alert.acknowledged_at = utc_now()
    alert.acknowledged_by = actor.id
    from app.services.privacy import encrypt_patient_value, get_patient_data_key
    patient_key = get_patient_data_key(db, referral.screening.patient_id, settings)
    alert.note = encrypt_patient_value(db, referral.screening.patient_id, note.strip()[:1000], "red_flag_note", settings) if note.strip() and patient_key else None
    note_digest = hashlib.sha256(alert.note.encode()).hexdigest() if alert.note else None
    event = append_event(db, patient_id=referral.screening.patient_id, event_type="RED_FLAG_ACKNOWLEDGED", actor=actor,
        payload={"alert_id": alert.id, "referral_id": referral.id, "note_sha256": note_digest},
        referral_id=referral.id, settings=settings)
    db.flush()
    return {"alert_id": alert.id, "acknowledged_at": alert.acknowledged_at, "event": event_view(event),
            "dispatch_status": "not_dispatched_simulated_alert_only"}


def followup_status(db: Session, *, actor: User, patient_id: str) -> dict:
    _require_patient_access(db, actor, patient_id)
    plans = db.scalars(select(FollowUpPlan).where(FollowUpPlan.patient_id == patient_id).order_by(FollowUpPlan.due_date.asc())).all()
    current_state = latest_workflow_state(db, patient_id)
    return {"patient_id": patient_id, "current_state": current_state,
            "plans": [{"id": p.id, "due_date": p.due_date, "plan_type": p.plan_type, "status": p.status} for p in plans]}
