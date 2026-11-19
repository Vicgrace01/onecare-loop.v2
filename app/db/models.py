from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PHARMACY = "pharmacy"
    PMV = "pmv"
    HOSPITAL = "hospital"
    CLINICIAN = "clinician"
    HMO = "hmo"
    PATIENT = "patient"


class Organisation(Base):
    __tablename__ = "organisations"
    __table_args__ = (CheckConstraint("type IN ('pharmacy', 'pmv', 'hospital', 'hmo', 'donor', 'chw')", name="ck_organisation_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    lga: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organisation")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str | None] = mapped_column(String(120))  # deprecated; new writes keep this NULL
    display_name_ciphertext: Mapped[str | None] = mapped_column(Text)
    demographic_data_ciphertext: Mapped[str | None] = mapped_column(Text)
    age_band: Mapped[str | None] = mapped_column(String(20))
    insurance_type: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    contacts: Mapped[list["PatientContact"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="patient")
    consents: Mapped[list["Consent"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    screenings: Mapped[list["Screening"]] = relationship(back_populates="patient")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        CheckConstraint("role IN ('admin', 'pharmacy', 'pmv', 'hospital', 'clinician', 'hmo', 'patient')", name="ck_user_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # email/email_normalized hold opaque aliases and keyed lookup tokens for new
    # accounts. The address itself is encrypted in email_ciphertext.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(254), nullable=False)
    email_ciphertext: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default=UserRole.PATIENT.value, nullable=False, index=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organisation: Mapped[Organisation | None] = relationship(back_populates="users")
    patient: Mapped[Patient | None] = relationship(back_populates="users")


class PatientContact(Base):
    __tablename__ = "patient_contacts"
    __table_args__ = (UniqueConstraint("phone_lookup_hash", name="uq_patient_phone_lookup"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_lookup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    patient: Mapped[Patient] = relationship(back_populates="contacts")


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_patient_granted", "patient_id", "granted_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient: Mapped[Patient] = relationship(back_populates="consents")


class Screening(Base):
    __tablename__ = "screenings"
    __table_args__ = (
        Index("ix_screenings_patient_created", "patient_id", "created_at"),
        CheckConstraint("systolic BETWEEN 40 AND 300", name="ck_screening_systolic_range"),
        CheckConstraint("diastolic BETWEEN 20 AND 200", name="ck_screening_diastolic_range"),
        CheckConstraint("systolic > diastolic", name="ck_screening_systolic_gt_diastolic"),
        CheckConstraint("result IN ('positive', 'negative', 'inconclusive')", name="ck_screening_result"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    # New measurements/symptoms are stored in patient-key encrypted clinical_data_ciphertext.
    # Nullable numeric columns remain only for migration compatibility with early test records.
    systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symptoms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    clinical_data_ciphertext: Mapped[str | None] = mapped_column(Text)
    protocol_version: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    red_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    patient: Mapped[Patient] = relationship(back_populates="screenings")
    referrals: Mapped[list["Referral"]] = relationship(back_populates="screening")


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        Index("ix_referrals_facility_status", "facility_id", "status"),
        CheckConstraint("urgency IN ('routine', 'urgent', 'emergency')", name="ck_referral_urgency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    screening_id: Mapped[str] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), nullable=False)
    facility_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="REFERRAL_CREATED", nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    screening: Mapped[Screening] = relationship(back_populates="referrals")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="referral")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'booked', 'attended', 'missed', 'cancelled')", name="ck_appointment_status"),
        CheckConstraint("slot_end > slot_start", name="ck_appointment_positive_duration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="RESTRICT"), nullable=False, index=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="booked", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    referral: Mapped[Referral] = relationship(back_populates="appointments")
    encounters: Mapped[list["Encounter"]] = relationship(back_populates="appointment")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False, index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    attended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    appointment: Mapped[Appointment] = relationship(back_populates="encounters")
    dispositions: Mapped[list["ClinicalDisposition"]] = relationship(back_populates="encounter")


class ClinicalDisposition(Base):
    __tablename__ = "clinical_dispositions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="RESTRICT"), nullable=False, index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    encounter: Mapped[Encounter] = relationship(back_populates="dispositions")


class FollowUpPlan(Base):
    __tablename__ = "follow_up_plans"
    __table_args__ = (
        Index("ix_followup_patient_due", "patient_id", "due_date"),
        CheckConstraint("status IN ('pending', 'met', 'missed', 'cancelled')", name="ck_followup_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LedgerHead(Base):
    __tablename__ = "ledger_heads"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), primary_key=True)
    head_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LedgerEvent(Base):
    __tablename__ = "ledger_events"
    __table_args__ = (
        UniqueConstraint("patient_id", "seq", name="uq_ledger_patient_seq"),
        Index("ix_ledger_patient_seq", "patient_id", "seq"),
        Index("ix_ledger_referral", "referral_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    referral_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    actor_signature: Mapped[str] = mapped_column(Text, nullable=False)
    actor_public_key: Mapped[str] = mapped_column(Text, nullable=False)


class ActorSigningKey(Base):
    __tablename__ = "actor_signing_keys"

    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    private_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PatientDataKey(Base):
    """Wrapped per-patient data key; destroying the wrapped key renders contact ciphertext unreadable."""
    __tablename__ = "patient_data_keys"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), primary_key=True)
    wrapped_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_id)
    shredded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PatientOTP(Base):
    __tablename__ = "patient_otps"
    __table_args__ = (Index("ix_patient_otps_patient_created", "patient_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("channel IN ('sms', 'whatsapp')", name="ck_notification_channel"),
        CheckConstraint("status IN ('simulated', 'queued', 'failed')", name="ck_notification_status"),
        Index("ix_notifications_patient_created", "patient_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_id: Mapped[str] = mapped_column(String(60), nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    rendered_body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    reply_text: Mapped[str | None] = mapped_column(Text)
    reply_class: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class EligibilityCheck(Base):
    __tablename__ = "eligibility_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    adapter: Mapped[str] = mapped_column(String(40), default="local_mock", nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    request_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LoopException(Base):
    __tablename__ = "loop_exceptions"
    __table_args__ = (
        Index("ix_loop_exceptions_open", "resolved_at", "created_at"),
        UniqueConstraint("referral_id", "event_type", name="uq_loop_exception_referral_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CaseMessage(Base):
    __tablename__ = "case_messages"
    __table_args__ = (Index("ix_case_messages_referral_created", "referral_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="RESTRICT"), nullable=False)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
