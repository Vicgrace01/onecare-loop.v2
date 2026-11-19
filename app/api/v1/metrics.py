from collections import defaultdict
from statistics import median

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_roles
from app.db.models import LedgerEvent, Referral, User

router = APIRouter(prefix="/metrics", tags=["operations metrics"])
FAILURE_EVENTS = {
    "REFERRAL_DECLINED", "FACILITY_UNAVAILABLE", "APPOINTMENT_MISSED",
    "PATIENT_UNREACHABLE", "PATIENT_DECLINED", "PATIENT_REQUESTED_RESCHEDULE",
    "FOLLOWUP_OVERDUE",
}


@router.get("")
def metrics(db: Session = Depends(get_db), _actor: User = Depends(require_roles("admin", "hmo"))):
    referrals = db.scalars(select(Referral).options(joinedload(Referral.screening))).unique().all()
    referral_ids = [row.id for row in referrals]
    events = db.scalars(
        select(LedgerEvent).where(LedgerEvent.referral_id.in_(referral_ids)).order_by(LedgerEvent.seq.asc())
    ).all() if referral_ids else []
    events_by_referral = defaultdict(list)
    failures = defaultdict(int)
    for event in events:
        events_by_referral[event.referral_id].append(event)
        if event.event_type in FAILURE_EVENTS:
            failures[event.event_type] += 1

    durations = []
    closed = 0
    for referral in referrals:
        disposition = next(
            (event for event in reversed(events_by_referral[referral.id])
             if event.event_type == "CLINICAL_DISPOSITION_RETURNED"),
            None,
        )
        if disposition is None:
            continue
        closed += 1
        start = referral.screening.created_at
        end = disposition.occurred_at
        if start.tzinfo is None:
            from datetime import timezone
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            from datetime import timezone
            end = end.replace(tzinfo=timezone.utc)
        durations.append((end - start).total_seconds() / 3600)

    total_referrals = len(referrals)
    return {
        "total_patients": len({row.screening.patient_id for row in referrals}),
        "total_referrals": total_referrals,
        "closed_loops": closed,
        "closure_rate": round(closed / total_referrals, 4) if total_referrals else 0,
        "median_hours_to_disposition": round(median(durations), 2) if durations else None,
        "failure_breakdown": dict(failures),
        "financial_value": None,
        "financial_value_note": "No negotiated payer value is configured; no recovered-value estimate is fabricated.",
    }
