from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import Patient, User, UserRole
from app.services.privacy import account_email_alias, email_lookup_token, encrypt_account_email


class AuthenticationError(ValueError):
    pass


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _email_exists(db: Session, normalized: str, settings) -> bool:
    token = email_lookup_token(normalized, settings)
    return db.scalar(
        select(User.id).where(User.email_normalized.in_([token, normalized]))
    ) is not None


def set_encrypted_email(user: User, normalized: str, settings) -> None:
    user.email = account_email_alias(user.id)
    user.email_normalized = email_lookup_token(normalized, settings)
    user.email_ciphertext = encrypt_account_email(normalized, settings)


def register_patient(db: Session, *, email: str, password: str, display_name: str, settings) -> User:
    normalized = _normalise_email(email)
    if _email_exists(db, normalized, settings):
        raise AuthenticationError("An account with this email already exists")

    patient = Patient(display_name=None)
    db.add(patient)
    db.flush()
    user = User(
        id=str(uuid.uuid4()),
        email="pending@onecare.invalid",
        email_normalized=f"pending:{uuid.uuid4()}",
        password_hash=hash_password(password),
        role=UserRole.PATIENT.value,
        patient=patient,
    )
    db.add(user)
    db.flush()
    set_encrypted_email(user, normalized, settings)

    from app.services.privacy import encrypt_patient_value
    patient.display_name_ciphertext = encrypt_patient_value(
        db, patient.id, display_name.strip(), "display_name", settings
    )
    db.flush()
    return user


def authenticate(db: Session, *, email: str, password: str, settings) -> User | None:
    normalized = _normalise_email(email)
    token = email_lookup_token(normalized, settings)
    user = db.scalar(select(User).where(User.email_normalized == token))
    legacy_record = False
    if user is None:
        # One-time migration path for accounts created before encrypted-email storage.
        user = db.scalar(select(User).where(User.email_normalized == normalized))
        legacy_record = user is not None
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if legacy_record:
        set_encrypted_email(user, normalized, settings)
        db.flush()
    return user


def provision_staff_user(
    db: Session, *, email: str, password: str, role: str, organisation_id: str | None, settings
) -> User:
    normalized = _normalise_email(email)
    if role not in {"pharmacy", "pmv", "hospital", "clinician", "hmo"}:
        raise AuthenticationError("This endpoint can only provision non-administrator staff roles")
    if _email_exists(db, normalized, settings):
        raise AuthenticationError("An account with this email already exists")
    user = User(
        id=str(uuid.uuid4()),
        email="pending@onecare.invalid",
        email_normalized=f"pending:{uuid.uuid4()}",
        password_hash=hash_password(password),
        role=role,
        organisation_id=organisation_id,
    )
    db.add(user)
    db.flush()
    set_encrypted_email(user, normalized, settings)
    db.flush()
    return user
