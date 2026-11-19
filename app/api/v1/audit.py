from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import LedgerEvent, Patient, User
from app.domain.ledger import verify_patient_chain

router = APIRouter(prefix="/audit", tags=["audit"])


def _can_view_patient(user: User, patient_id: str) -> bool:
    return user.role == "admin" or (user.role == "patient" and user.patient_id == patient_id)


@router.get("/patients/{patient_id}/verify")
def verify_patient(patient_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    if not _can_view_patient(user, patient_id):
        raise HTTPException(status_code=403, detail="You cannot access this patient's audit record")
    if db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return verify_patient_chain(db, patient_id)


@router.get("/patients/{patient_id}/events")
def list_patient_events(patient_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    if not _can_view_patient(user, patient_id):
        raise HTTPException(status_code=403, detail="You cannot access this patient's events")
    if db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    rows = db.scalars(
        select(LedgerEvent).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.asc())
    ).all()
    return {
        "patient_id": patient_id,
        "events": [
            {
                "id": row.id,
                "seq": row.seq,
                "event_type": row.event_type,
                "actor_role": row.actor_role,
                "occurred_at": row.occurred_at,
                "event_hash": row.event_hash,
                "prev_hash": row.prev_hash,
                "payload": row.payload,
            }
            for row in rows
        ],
    }
