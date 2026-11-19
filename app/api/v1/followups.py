from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import User
from app.schemas.care import BPControlCreate, FollowUpAssessment, FollowUpCreate
from app.services.care import followup_status, record_bp_control, record_followup_assessment, schedule_followup

router = APIRouter(prefix="/patients/{patient_id}/followups", tags=["longitudinal follow-up"])


@router.get("")
def status(patient_id: str, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "clinician", "pharmacy", "pmv", "patient"))):
    try:
        return followup_status(db, actor=actor, patient_id=patient_id)
    except Exception as exc:
        raise_api_error(exc)


@router.post("", status_code=201)
def schedule(patient_id: str, body: FollowUpCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("clinician"))):
    try:
        return schedule_followup(db, actor=actor, patient_id=patient_id, due_date=body.due_date,
            plan_type=body.plan_type, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/assessment")
def assess(patient_id: str, body: FollowUpAssessment, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("pharmacy", "pmv"))):
    try:
        return record_followup_assessment(db, actor=actor, patient_id=patient_id, systolic=body.systolic,
            diastolic=body.diastolic, bp_controlled=None, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/bp-control")
def bp_control(patient_id: str, body: BPControlCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("pharmacy", "pmv"))):
    try:
        return record_bp_control(db, actor=actor, patient_id=patient_id, systolic=body.systolic,
            diastolic=body.diastolic, controlled=body.bp_controlled, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)
