from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.errors import raise_api_error
from app.core.security import create_access_token, hash_password
from app.db.models import User
from app.schemas.auth import UserView
from app.schemas.care import ConsentRevoke, FailureAction, OTPRequest, OTPVerify
from app.services.care import (
    acknowledge_patient_receipt, patient_decline_referral, patient_receipt, patient_request_reschedule,
    request_patient_otp, revoke_consent, verify_patient_otp,
)

router = APIRouter(prefix="/patients", tags=["patient portal"])


@router.post("/otp/request")
def otp_request(body: OTPRequest, request: Request, db: Session = Depends(get_db)):
    try:
        return request_patient_otp(db, phone=body.phone, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/otp/verify")
def otp_verify(body: OTPVerify, request: Request, db: Session = Depends(get_db)):
    settings = request.app.state.settings
    try:
        patient = verify_patient_otp(db, phone=body.phone, code=body.code, settings=settings)
    except Exception as exc:
        raise_api_error(exc)
    if patient is None:
        # Commit the failed-attempt counter before returning an auth failure.
        db.commit()
        raise HTTPException(401, "Invalid or expired code")
    user = db.scalar(select(User).where(User.patient_id == patient.id))
    if user is None:
        internal_email = f"patient-{patient.id}@onecare.invalid"
        user = User(email=internal_email, email_normalized=internal_email, password_hash=hash_password(__import__("secrets").token_urlsafe(32)),
                    role="patient", patient_id=patient.id, is_active=True)
        db.add(user)
        db.flush()
    token = create_access_token(user.id, settings.secret_key, settings.access_token_ttl_seconds)
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.access_token_ttl_seconds,
            "user": UserView(id=user.id, email=None, role=user.role, organisation_id=user.organisation_id,
                patient_id=user.patient_id, is_active=user.is_active, created_at=user.created_at).model_dump()}


@router.get("/me/receipt")
def my_receipt(request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "patient" or not actor.patient_id:
        raise HTTPException(403, "Patient account required")
    try:
        return patient_receipt(db, actor=actor, patient_id=actor.patient_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/me/receipt/acknowledge")
def acknowledge_receipt(request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    try:
        return acknowledge_patient_receipt(db, actor=actor, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/me/referrals/{referral_id}/decline")
def decline_own_referral(referral_id: str, body: FailureAction, request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    try:
        return patient_decline_referral(db, actor=actor, referral_id=referral_id,
            reason_code=body.reason_code, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/me/referrals/{referral_id}/reschedule-request")
def request_own_reschedule(referral_id: str, body: FailureAction, request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    try:
        return patient_request_reschedule(db, actor=actor, referral_id=referral_id,
            reason_code=body.reason_code, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.get("/{patient_id}/receipt")
def patient_receipt_by_id(patient_id: str, request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    try:
        return patient_receipt(db, actor=actor, patient_id=patient_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/{patient_id}/consent/revoke")
def revoke(patient_id: str, body: ConsentRevoke, request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    try:
        return revoke_consent(db, actor=actor, patient_id=patient_id, reason=body.reason, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)
