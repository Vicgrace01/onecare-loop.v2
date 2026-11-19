from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import Notification, User
from app.schemas.care import AlertAcknowledge, CaseMessageCreate
from app.services.care import (
    acknowledge_red_flag, create_case_message, list_case_messages, list_red_flags,
)

router = APIRouter(tags=["communications and alerts"])


@router.get("/red-flags")
def red_flags(db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital", "clinician"))):
    try:
        return {"alerts": list_red_flags(db, actor), "simulated": True, "dispatch_enabled": False}
    except Exception as exc:
        raise_api_error(exc)


@router.post("/red-flags/{alert_id}/acknowledge")
def acknowledge(alert_id: str, body: AlertAcknowledge, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("hospital", "admin"))):
    try:
        return acknowledge_red_flag(db, actor=actor, alert_id=alert_id, note=body.note, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.post("/referrals/{referral_id}/messages", status_code=201)
def post_message(referral_id: str, body: CaseMessageCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "pharmacy", "pmv", "hospital", "clinician"))):
    try:
        return create_case_message(db, actor=actor, referral_id=referral_id, body=body.body, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)


@router.get("/referrals/{referral_id}/messages")
def get_messages(referral_id: str, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "pharmacy", "pmv", "hospital", "clinician"))):
    try:
        return {"messages": list_case_messages(db, actor=actor, referral_id=referral_id, settings=request.app.state.settings)}
    except Exception as exc:
        raise_api_error(exc)


@router.get("/patients/me/notifications")
def my_notifications(request: Request, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "patient" or not actor.patient_id:
        raise HTTPException(403, "Patient account required")
    rows = db.scalars(select(Notification).where(Notification.patient_id == actor.patient_id).order_by(Notification.created_at.asc())).all()
    from app.db.models import AccessLog, utc_now
    db.add(AccessLog(actor_id=actor.id, resource_type="patient_notifications", resource_id=actor.patient_id, purpose="patient_notification_view", occurred_at=utc_now()))
    from app.services.privacy import decrypt_patient_value
    return {"notifications": [{"id": n.id, "channel": n.channel, "template_id": n.template_id,
        "language": n.language,
        "body": decrypt_patient_value(db, actor.patient_id, n.rendered_body, f"notification:{n.id}", request.app.state.settings) or "[message redacted after consent revocation]",
        "status": n.status, "created_at": n.created_at} for n in rows],
        "delivery_mode": "simulated_no_provider_call"}
