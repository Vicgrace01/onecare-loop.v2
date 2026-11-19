from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PatientDataKey, utc_now


def _master_key(settings: Settings) -> bytes:
    secret = settings.pii_encryption_key or settings.signing_master_key or settings.secret_key
    return hashlib.sha256(("onecare-patient-data-key-v1::" + secret).encode()).digest()


def email_lookup_token(email: str, settings: Settings) -> str:
    """Return a keyed, non-reversible lookup token for an account email."""
    normalized = email.strip().lower()
    return hmac.new(
        _master_key(settings),
        ("onecare-email-lookup-v1:" + normalized).encode(),
        hashlib.sha256,
    ).hexdigest()


def encrypt_account_email(email: str, settings: Settings) -> str:
    """Encrypt an account email with the dedicated PII key, not the signing key."""
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_master_key(settings)).encrypt(
        nonce,
        email.strip().encode(),
        b"onecare-account-email-v1",
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_account_email(ciphertext: str | None, settings: Settings) -> str | None:
    if not ciphertext:
        return None
    try:
        raw = base64.urlsafe_b64decode(ciphertext.encode())
        return AESGCM(_master_key(settings)).decrypt(
            raw[:12], raw[12:], b"onecare-account-email-v1"
        ).decode()
    except Exception:
        return None


def account_email_alias(user_id: str) -> str:
    """Stable opaque value for legacy non-null email columns."""
    return f"account-{user_id}@onecare.invalid"


def _wrap_key(key: bytes, settings: Settings) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_master_key(settings)).encrypt(nonce, key, b"onecare-wrapped-patient-key-v1")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _unwrap_key(wrapped: str, settings: Settings) -> bytes:
    raw = base64.urlsafe_b64decode(wrapped.encode())
    return AESGCM(_master_key(settings)).decrypt(raw[:12], raw[12:], b"onecare-wrapped-patient-key-v1")


def get_patient_data_key(db: Session, patient_id: str, settings: Settings, *, create: bool = False) -> bytes | None:
    row = db.get(PatientDataKey, patient_id)
    if row is None:
        if not create:
            return None
        key = secrets.token_bytes(32)
        db.add(PatientDataKey(patient_id=patient_id, wrapped_key=_wrap_key(key, settings)))
        db.flush()
        return key
    if row.shredded_at is not None or not row.wrapped_key:
        return None
    return _unwrap_key(row.wrapped_key, settings)


def encrypt_patient_value(db: Session, patient_id: str, value: str, field: str, settings: Settings) -> str:
    key = get_patient_data_key(db, patient_id, settings, create=True)
    assert key is not None
    nonce = secrets.token_bytes(12)
    aad = f"onecare:{patient_id}:{field}:v1".encode()
    ciphertext = AESGCM(key).encrypt(nonce, value.encode(), aad)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_patient_value(db: Session, patient_id: str, value: str, field: str, settings: Settings) -> str | None:
    key = get_patient_data_key(db, patient_id, settings)
    if key is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(value.encode())
        aad = f"onecare:{patient_id}:{field}:v1".encode()
        return AESGCM(key).decrypt(raw[:12], raw[12:], aad).decode()
    except Exception:
        return None


def encrypt_ledger_payload(db: Session, patient_id: str, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    key_row = db.get(PatientDataKey, patient_id)
    if key_row is None:
        # Backfill an encryption key for legacy patients on their first new event.
        key = get_patient_data_key(db, patient_id, settings, create=True)
    elif key_row.shredded_at is not None or not key_row.wrapped_key:
        # The revocation event carries only non-identifying metadata. Never recreate a key.
        return payload
    else:
        key = get_patient_data_key(db, patient_id, settings)
    if key is None:
        raise RuntimeError("Patient encryption key is unavailable")
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    nonce = secrets.token_bytes(12)
    aad = f"onecare:{patient_id}:ledger-payload:v1".encode()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {"_encrypted_payload_v1": base64.urlsafe_b64encode(nonce + ciphertext).decode()}


def decrypt_ledger_payload(db: Session, patient_id: str, payload: dict[str, Any], settings: Settings) -> dict[str, Any] | None:
    encoded = (payload or {}).get("_encrypted_payload_v1")
    if not encoded:
        return payload or {}
    key = get_patient_data_key(db, patient_id, settings)
    if key is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        aad = f"onecare:{patient_id}:ledger-payload:v1".encode()
        plaintext = AESGCM(key).decrypt(raw[:12], raw[12:], aad)
        value = json.loads(plaintext)
        return value if isinstance(value, dict) else None
    except Exception:
        return None
