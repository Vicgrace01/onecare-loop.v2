from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import AccessLog, Referral, User, utc_now
from app.domain.ledger import verify_patient_chain
from app.schemas.care import ReferralCreate
from app.services.care import create_referral, event_view
from app.services.privacy import decrypt_ledger_payload

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.post("", status_code=201)
def post_referral(body: ReferralCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("pharmacy", "pmv"))):
    try:
        return create_referral(db, actor=actor, screening_id=body.screening_id, facility_id=body.facility_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.get("/{referral_id}/history")
def referral_history(referral_id: str, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "pharmacy", "pmv", "hospital", "clinician"))):
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(404, "Referral not found")
    screening = referral.screening
    allowed_orgs = {referral.facility_id, screening.organisation_id}
    if actor.role != "admin" and actor.organisation_id not in allowed_orgs:
        raise HTTPException(403, "You are not part of this referral's care organisations")
    result = verify_patient_chain(db, screening.patient_id)
    from app.db.models import LedgerEvent
    rows = db.scalars(select(LedgerEvent).where(
        LedgerEvent.patient_id == screening.patient_id,
    ).order_by(LedgerEvent.seq.asc())).all()
    events = []
    for row in rows:
        payload = decrypt_ledger_payload(db, screening.patient_id, row.payload or {}, request.app.state.settings)
        belongs_to_referral = row.referral_id == referral_id
        belongs_to_screening = (
            row.event_type in {"SCREEN_POSITIVE", "SCREEN_NEGATIVE", "SCREENING_INCONCLUSIVE"}
            and payload is not None
            and payload.get("screening_id") == screening.id
        )
        if not (belongs_to_referral or belongs_to_screening):
            continue
        events.append(event_view(row) | {
            "payload": payload,
            "details_redacted": payload is None,
        })
    db.add(AccessLog(
        actor_id=actor.id, resource_type="referral_history", resource_id=referral_id,
        purpose="care_coordination_history", occurred_at=utc_now(),
    ))
    return {"referral_id": referral_id, "chain_verified": result["ok"], "events": events}
