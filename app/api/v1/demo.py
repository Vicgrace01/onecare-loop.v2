from __future__ import annotations

import secrets
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import LedgerEvent, Notification, Organisation, User
from app.domain.ledger import verify_patient_chain
from app.services.care import (
    accept_referral, attest_attendance, book_appointment, create_referral,
    create_screening, record_confirmatory_assessment, return_disposition,
    schedule_followup,
)
from app.db.models import utc_now
from app.services.privacy import email_lookup_token

router = APIRouter(prefix="/demo", tags=["judge demonstration"])


def _demo_enabled(request: Request) -> None:
    if not request.app.state.settings.demo_mode_enabled:
        raise HTTPException(status_code=404, detail="The judge demo is not enabled")


def _account(db: Session, settings, email: str, role: str) -> User:
    lookup = email_lookup_token(email.strip().lower(), settings)
    user = db.scalar(select(User).where(User.email_normalized == lookup))
    if user is None or not user.is_active or user.role != role or not user.organisation_id:
        raise HTTPException(status_code=503, detail=f"Demo {role} account is not provisioned")
    return user


@router.get("/info")
def demo_info(request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.demo_mode_enabled:
        return {
            "enabled": False,
            "synthetic_only": True,
            "credentials_visible": False,
            "roles": [],
            "notice": "The judge demo is not enabled on this deployment. The page is available, but no accounts or synthetic cases are exposed. Set DEMO_MODE_ENABLED=true with unique demo credentials to activate it.",
        }
    roles = [
        {"label": "Community pharmacy", "role": "pharmacy", "email": settings.demo_pharmacy_email, "password": settings.demo_pharmacy_password},
        {"label": "Hospital coordinator", "role": "hospital", "email": settings.demo_hospital_email, "password": settings.demo_hospital_password},
        {"label": "Assigned clinician", "role": "clinician", "email": settings.demo_clinician_email, "password": settings.demo_clinician_password},
        {"label": "HMO reviewer", "role": "hmo", "email": settings.demo_hmo_email, "password": settings.demo_hmo_password},
    ]
    for item in roles:
        if not settings.demo_show_credentials:
            item.pop("password")
    return {
        "enabled": True,
        "synthetic_only": True,
        "credentials_visible": settings.demo_show_credentials,
        "roles": roles,
        "notice": "These accounts are restricted to the synthetic challenge environment. No live SMS, payer or emergency service is contacted.",
    }


@router.post("/run")
def run_judge_demo(request: Request, db: Session = Depends(get_db)) -> dict:
    """Create a complete synthetic case through the same care services as normal APIs."""
    _demo_enabled(request)
    # Simple per-process abuse guard; a multi-worker deployment should also add a shared edge limit.
    host = request.client.host if request.client else "unknown"
    now_mono = time.monotonic()
    bucket = request.app.state.demo_rate_limiter[host]
    while bucket and now_mono - bucket[0] > 3600:
        bucket.popleft()
    if len(bucket) >= 5:
        raise HTTPException(status_code=429, detail="Demo run limit reached. Please replay the current run instead.")
    bucket.append(now_mono)

    settings = request.app.state.settings
    pharmacy = _account(db, settings, settings.demo_pharmacy_email, "pharmacy")
    hospital = _account(db, settings, settings.demo_hospital_email, "hospital")
    clinician = _account(db, settings, settings.demo_clinician_email, "clinician")
    facility = db.get(Organisation, hospital.organisation_id)
    if facility is None or facility.type != "hospital":
        raise HTTPException(status_code=503, detail="Demo hospital organisation is unavailable")

    started = utc_now()
    # Unique synthetic phone avoids collisions between judge replays; data is encrypted at rest.
    phone = "+23480" + str(secrets.randbelow(10**8)).zfill(8)
    screen = create_screening(db, actor=pharmacy, settings=settings, body={
        "patient": {"display_name": "Adaeze Demo", "age_band": "40-49", "insurance_type": "unknown",
                    "phone": phone, "preferred_language": "en"},
        "consent": {"version": "DEMO-1.0", "scopes": ["screening", "referral", "follow_up", "notifications", "outcome_review"]},
        "screening": {"systolic": 168, "diastolic": 104, "symptoms": [], "protocol_version": "HTN-PROTOCOL-v1"},
    })
    referral = create_referral(db, actor=pharmacy, screening_id=screen["screening_id"],
                               facility_id=facility.id, settings=settings)
    accepted = accept_referral(db, actor=hospital, referral_id=referral["referral_id"], settings=settings)
    slot_start = utc_now() + timedelta(days=1)
    slot_end = slot_start + timedelta(minutes=30)
    booked = book_appointment(db, actor=hospital, referral_id=referral["referral_id"],
                              slot_start=slot_start, slot_end=slot_end, settings=settings)
    attended = attest_attendance(db, actor=hospital, referral_id=referral["referral_id"],
                                 clinician_id=clinician.id, notes="Synthetic demonstration attendance; no real patient visit.",
                                 settings=settings)
    confirmatory = record_confirmatory_assessment(
        db, actor=clinician, referral_id=referral["referral_id"], method="repeat_office",
        systolic=158, diastolic=98, note="Synthetic repeat office reading recorded by the assigned clinician.",
        settings=settings,
    )
    disposition = return_disposition(
        db, actor=clinician, referral_id=referral["referral_id"],
        outcome="clinical_review_completed",
        next_step="Repeat blood-pressure assessment in 30 days; clinician to review the result.",
        settings=settings,
    )
    followup = schedule_followup(
        db, actor=clinician, patient_id=screen["patient_id"],
        due_date=utc_now() + timedelta(days=30), plan_type="30_day", settings=settings,
    )
    db.flush()
    verification = verify_patient_chain(db, screen["patient_id"])
    events = db.scalars(
        select(LedgerEvent).where(LedgerEvent.patient_id == screen["patient_id"]).order_by(LedgerEvent.seq.asc())
    ).all()
    notifications = db.scalars(select(Notification).where(Notification.patient_id == screen["patient_id"])).all()
    if not verification.get("ok"):
        raise HTTPException(status_code=500, detail="The synthetic event chain did not verify")

    event_payload = [
        {"seq": event.seq, "event_type": event.event_type, "actor_role": event.actor_role,
         "occurred_at": event.occurred_at.isoformat(), "event_hash": event.event_hash}
        for event in events
    ]
    elapsed = max(0.0, (utc_now() - started).total_seconds())
    return {
        "run_id": secrets.token_urlsafe(9),
        "synthetic_only": True,
        "patient_reference": "DEMO-" + screen["patient_id"][:8].upper(),
        "patient_id": screen["patient_id"],
        "referral_id": referral["referral_id"],
        "facility": facility.name,
        "screening": {"systolic": screen["systolic"], "diastolic": screen["diastolic"],
                      "result": screen["result"], "urgency": referral["urgency"]},
        "appointment": {"start": slot_start.isoformat(), "end": slot_end.isoformat()},
        "confirmatory": {"method": "repeat_office", "systolic": 158, "diastolic": 98},
        "disposition": {"outcome": "clinical_review_completed", "next_step": "Repeat blood-pressure assessment in 30 days."},
        "follow_up_due": followup["due_date"].isoformat(),
        "notification_count": len(notifications),
        "notification_provider_called": False,
        "events": event_payload,
        "chain": {"verified": bool(verification.get("ok")), "event_count": verification.get("events", len(events)),
                  "signed_count": len(events) if verification.get("ok") else 0},
        "elapsed_seconds": round(elapsed, 2),
        "transparency": {"sms": "simulated; no message sent", "eligibility": "unknown; no live NHIA/DHIN query",
                         "clinical_decisions": "entered by synthetic clinician actor", "financial_savings": "not estimated"},
        "action_events": [screen["event"], referral["event"], accepted["event"], booked["event"],
                          attended["event"], confirmatory["event"], disposition["event"], followup["event"]],
    }
