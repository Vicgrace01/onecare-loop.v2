from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TransitionRequest(BaseModel):
    patient_id: str
    target_state: str
    payload: dict[str, Any] = Field(default_factory=dict)
    referral_id: str | None = None


class LedgerEventView(BaseModel):
    id: str
    seq: int
    patient_id: str
    referral_id: str | None
    event_type: str
    actor_id: str
    actor_role: str
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str
    occurred_at: datetime
    recorded_at: datetime
    actor_signature: str
    actor_public_key: str
