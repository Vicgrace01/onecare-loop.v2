from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import User
from app.schemas.care import AppointmentCreate, AttendanceAttest, ConfirmatoryAssessmentCreate, DispositionCreate, FailureAction, ReferralDecline, ReferralOwnerAssignment, ReferralRedirect
from app.services.care import (
    accept_referral, book_appointment, decline_referral, attest_attendance,
    mark_appointment_missed, mark_patient_unreachable, return_disposition, list_hospital_queue,
    record_confirmatory_assessment, assign_referral_owner, list_operational_attention,
    redirect_declined_referral,
)

router = APIRouter(prefix="/hospital", tags=["hospital operations"])


@router.get("/queue")
def queue(request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital", "clinician"))):
    try:
        return {"queue": list_hospital_queue(db, actor, request.app.state.settings)}
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/accept")
def accept(referral_id: str, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return accept_referral(db, actor=actor, referral_id=referral_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/decline")
def decline(referral_id: str, body: ReferralDecline, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return decline_referral(db, actor=actor, referral_id=referral_id, reason_code=body.reason_code,
            owner_user_id=body.owner_user_id, redirect_facility_id=body.redirect_facility_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/appointments")
def book(referral_id: str, body: AppointmentCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return book_appointment(db, actor=actor, referral_id=referral_id, slot_start=body.slot_start,
            slot_end=body.slot_end, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/attendance")
def attendance(referral_id: str, body: AttendanceAttest, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return attest_attendance(db, actor=actor, referral_id=referral_id, clinician_id=body.clinician_id,
            notes=body.notes, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/appointments/missed")
def missed(referral_id: str, body: FailureAction, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return mark_appointment_missed(db, actor=actor, referral_id=referral_id,
            reason_code=body.reason_code, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/unreachable")
def unreachable(referral_id: str, body: FailureAction, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital"))):
    try:
        return mark_patient_unreachable(db, actor=actor, referral_id=referral_id,
            reason_code=body.reason_code, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.get("/attention")
def attention(db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital"))):
    try:
        return list_operational_attention(db, actor=actor)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/redirect")
def redirect(referral_id: str, body: ReferralRedirect, request: Request,
             db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital"))):
    try:
        return redirect_declined_referral(db, actor=actor, referral_id=referral_id,
            new_facility_id=body.facility_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/assign")
def assign(referral_id: str, body: ReferralOwnerAssignment, request: Request,
           db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital"))):
    try:
        return assign_referral_owner(db, actor=actor, referral_id=referral_id,
            owner_user_id=body.owner_user_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/confirmatory-assessment")
def confirmatory_assessment(referral_id: str, body: ConfirmatoryAssessmentCreate, request: Request,
                            db: Session = Depends(get_db), actor: User = Depends(require_roles("clinician"))):
    try:
        return record_confirmatory_assessment(db, actor=actor, referral_id=referral_id,
            method=body.method, systolic=body.systolic, diastolic=body.diastolic,
            note=body.note, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/disposition")
def disposition(referral_id: str, body: DispositionCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("clinician"))):
    try:
        return return_disposition(db, actor=actor, referral_id=referral_id, outcome=body.outcome,
            next_step=body.next_step, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)
