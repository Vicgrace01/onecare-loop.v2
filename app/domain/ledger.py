from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ActorSigningKey, LedgerEvent, LedgerHead, Patient, User, utc_now
from app.domain.states import ALL_STATES, GENESIS_HASH, TransitionError, validate_transition


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp(value: datetime) -> str:
    # SQLite may return timezone-naive datetime objects; persisted values are UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def event_material(event: dict[str, Any]) -> dict[str, Any]:
    """Fields committed by the event digest; signatures are deliberately excluded."""
    return {
        "id": event["id"],
        "seq": event["seq"],
        "patient_id": event["patient_id"],
        "referral_id": event.get("referral_id"),
        "event_type": event["event_type"],
        "actor_id": event["actor_id"],
        "actor_role": event["actor_role"],
        "actor_public_key": event["actor_public_key"],
        "payload": event["payload"],
        "prev_hash": event["prev_hash"],
        "occurred_at": event["occurred_at"],
        "recorded_at": event["recorded_at"],
    }


def compute_event_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event_material(event)).encode("utf-8")).hexdigest()


def _encryption_key(settings: Settings) -> bytes:
    source = settings.signing_master_key or settings.secret_key
    return hashlib.sha256(("onecare-actor-key-encryption::" + source).encode("utf-8")).digest()


def _encrypt_private_key(private_pem: str, settings: Settings) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_encryption_key(settings)).encrypt(nonce, private_pem.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_private_key(ciphertext_b64: str, settings: Settings) -> str:
    raw = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
    plaintext = AESGCM(_encryption_key(settings)).decrypt(raw[:12], raw[12:], None)
    return plaintext.decode("utf-8")


def _get_or_create_actor_key(db: Session, actor: User, settings: Settings) -> ActorSigningKey:
    key = db.get(ActorSigningKey, actor.id)
    if key:
        return key
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    key = ActorSigningKey(
        actor_id=actor.id,
        private_key_ciphertext=_encrypt_private_key(private_pem, settings),
        public_key=public_pem,
    )
    db.add(key)
    db.flush()
    return key


def append_event(
    db: Session,
    *,
    patient_id: str,
    event_type: str,
    actor: User,
    payload: dict[str, Any] | None = None,
    referral_id: str | None = None,
    settings: Settings,
    occurred_at: datetime | None = None,
) -> LedgerEvent:
    """Append an event inside the caller's transaction; never commits on its own."""
    # Lock the patient row before the ledger head. This also serialises the first
    # append, when no LedgerHead row exists yet (SELECT FOR UPDATE cannot lock
    # a row that has not been created).
    patient = db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update())
    if patient is None:
        raise ValueError("Patient does not exist")
    if not actor.is_active:
        raise PermissionError("Inactive actors cannot append events")

    head = db.scalar(select(LedgerHead).where(LedgerHead.patient_id == patient_id).with_for_update())
    if head is None:
        head = LedgerHead(patient_id=patient_id, head_seq=0, head_hash=GENESIS_HASH)
        db.add(head)
        db.flush()

    now = utc_now()
    occurred_value = occurred_at or now
    from app.services.privacy import encrypt_ledger_payload
    stored_payload = encrypt_ledger_payload(db, patient_id, payload or {}, settings)
    key = _get_or_create_actor_key(db, actor, settings)
    event_dict: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "seq": head.head_seq + 1,
        "patient_id": patient_id,
        "referral_id": referral_id,
        "event_type": event_type,
        "actor_id": actor.id,
        "actor_role": actor.role,
        "actor_public_key": key.public_key,
        "payload": stored_payload,
        "prev_hash": head.head_hash,
        "occurred_at": _timestamp(occurred_value),
        "recorded_at": _timestamp(now),
    }
    digest = compute_event_hash(event_dict)
    private_pem = _decrypt_private_key(key.private_key_ciphertext, settings)
    private = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    signature = base64.b64encode(private.sign(digest.encode("ascii"))).decode("ascii")

    row = LedgerEvent(
        id=event_dict["id"],
        seq=event_dict["seq"],
        patient_id=event_dict["patient_id"],
        referral_id=event_dict["referral_id"],
        event_type=event_dict["event_type"],
        actor_id=event_dict["actor_id"],
        actor_role=event_dict["actor_role"],
        payload=event_dict["payload"],
        prev_hash=event_dict["prev_hash"],
        event_hash=digest,
        occurred_at=occurred_value,
        recorded_at=now,
        actor_signature=signature,
        actor_public_key=key.public_key,
    )
    db.add(row)
    head.head_seq = event_dict["seq"]
    head.head_hash = digest
    head.updated_at = now
    db.flush()
    return row



def latest_workflow_event(db: Session, patient_id: str) -> LedgerEvent | None:
    """Return the newest actual care-state event, ignoring auxiliary ledger entries."""
    return db.scalar(
        select(LedgerEvent)
        .where(LedgerEvent.patient_id == patient_id, LedgerEvent.event_type.in_(ALL_STATES))
        .order_by(LedgerEvent.seq.desc())
        .limit(1)
    )


def latest_workflow_state(db: Session, patient_id: str) -> str | None:
    event = latest_workflow_event(db, patient_id)
    return event.event_type if event else None


def record_transition(
    db: Session,
    *,
    patient_id: str,
    target_state: str,
    actor: User,
    payload: dict[str, Any] | None = None,
    referral_id: str | None = None,
    settings: Settings,
) -> LedgerEvent:
    """Validate the state transition and append it in the same DB transaction."""
    # A patient's event history contains both workflow transitions and auxiliary
    # events (messages, acknowledgements, consent changes, red-flag acknowledgements).
    # Only domain states may determine the next legal transition.
    db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update())
    head = db.scalar(select(LedgerHead).where(LedgerHead.patient_id == patient_id).with_for_update())
    current = latest_workflow_state(db, patient_id)
    if head and head.head_seq:
        latest_any = db.scalar(
            select(LedgerEvent).where(
                LedgerEvent.patient_id == patient_id,
                LedgerEvent.seq == head.head_seq,
            )
        )
        if latest_any is None:
            raise TransitionError("ledger_head_inconsistent", "Ledger head points to a missing event")
    data = payload or {}
    validate_transition(current, target_state, actor.role, data)
    return append_event(
        db,
        patient_id=patient_id,
        event_type=target_state,
        actor=actor,
        payload=data,
        referral_id=referral_id,
        settings=settings,
    )


def verify_patient_chain(db: Session, patient_id: str) -> dict[str, Any]:
    rows = db.scalars(
        select(LedgerEvent).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.asc())
    ).all()
    expected_prev = GENESIS_HASH
    for expected_seq, row in enumerate(rows, start=1):
        as_dict = {
            "id": row.id,
            "seq": row.seq,
            "patient_id": row.patient_id,
            "referral_id": row.referral_id,
            "event_type": row.event_type,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "actor_public_key": row.actor_public_key,
            "payload": row.payload,
            "prev_hash": row.prev_hash,
            "occurred_at": _timestamp(row.occurred_at),
            "recorded_at": _timestamp(row.recorded_at),
        }
        if row.seq != expected_seq:
            return {"ok": False, "patient_id": patient_id, "events": len(rows), "broken_at": {"seq": row.seq, "reason": "sequence_gap"}}
        if row.prev_hash != expected_prev:
            return {"ok": False, "patient_id": patient_id, "events": len(rows), "broken_at": {"seq": row.seq, "reason": "previous_hash_mismatch"}}
        actual_hash = compute_event_hash(as_dict)
        if actual_hash != row.event_hash:
            return {"ok": False, "patient_id": patient_id, "events": len(rows), "broken_at": {"seq": row.seq, "reason": "hash_mismatch"}}
        try:
            public = serialization.load_pem_public_key(row.actor_public_key.encode("utf-8"))
            public.verify(base64.b64decode(row.actor_signature), row.event_hash.encode("ascii"))
        except Exception:
            return {"ok": False, "patient_id": patient_id, "events": len(rows), "broken_at": {"seq": row.seq, "reason": "invalid_signature"}}
        expected_prev = row.event_hash

    head = db.get(LedgerHead, patient_id)
    if not rows:
        if head and head.head_seq != 0:
            return {"ok": False, "patient_id": patient_id, "events": 0, "broken_at": {"seq": 0, "reason": "orphaned_head"}}
        return {"ok": True, "patient_id": patient_id, "events": 0, "head_seq": 0, "head_hash": GENESIS_HASH, "broken_at": None}
    if head is None or head.head_seq != len(rows) or head.head_hash != expected_prev:
        return {"ok": False, "patient_id": patient_id, "events": len(rows), "broken_at": {"seq": len(rows), "reason": "head_mismatch"}}
    return {"ok": True, "patient_id": patient_id, "events": len(rows), "head_seq": len(rows), "head_hash": expected_prev, "broken_at": None}
