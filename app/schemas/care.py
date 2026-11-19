from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PatientCapture(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    age_band: Literal["18-29", "30-39", "40-49", "50-59", "60+"] | None = None
    insurance_type: Literal["nhia", "private", "self_pay", "donor", "unknown"] = "unknown"
    phone: str | None = Field(default=None, max_length=24)
    preferred_language: Literal["en", "pcm", "ig", "ha", "yo"] = "en"


class ConsentCapture(BaseModel):
    version: str = Field(default="1.0", min_length=1, max_length=40)
    scopes: list[Literal["screening", "referral", "follow_up", "notifications", "outcome_review"]] = Field(default_factory=lambda: ["screening", "referral", "follow_up", "notifications"], min_length=1)


class ScreeningValues(BaseModel):
    systolic: int = Field(ge=40, le=300)
    diastolic: int = Field(ge=20, le=200)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    protocol_version: str = Field(default="HTN-PROTOCOL-v1", min_length=1, max_length=50)

    @model_validator(mode="after")
    def check_pressure(self):
        if self.systolic <= self.diastolic:
            raise ValueError("Systolic must exceed diastolic")
        return self


class ScreeningCreate(BaseModel):
    patient: PatientCapture
    consent: ConsentCapture
    screening: ScreeningValues


class ReferralCreate(BaseModel):
    screening_id: str = Field(min_length=1, max_length=36)
    facility_id: str = Field(min_length=1, max_length=36)


class ReferralDecline(BaseModel):
    reason_code: str = Field(min_length=2, max_length=80)
    owner_user_id: str | None = None
    redirect_facility_id: str | None = None


class FailureAction(BaseModel):
    reason_code: str = Field(min_length=2, max_length=80)


class AppointmentCreate(BaseModel):
    slot_start: datetime
    slot_end: datetime

    @model_validator(mode="after")
    def check_slot(self):
        if self.slot_start.tzinfo is None or self.slot_end.tzinfo is None:
            raise ValueError("Appointment timestamps must include a timezone")
        if self.slot_end <= self.slot_start:
            raise ValueError("Appointment end must be after start")
        return self


class AttendanceAttest(BaseModel):
    clinician_id: str = Field(min_length=1, max_length=36)
    notes: str = Field(default="", max_length=4000)


class DispositionCreate(BaseModel):
    outcome: str = Field(min_length=2, max_length=100)
    next_step: str = Field(min_length=2, max_length=2000)


class ConfirmatoryAssessmentCreate(BaseModel):
    method: Literal["repeat_office", "home_monitoring", "ambulatory_monitoring", "not_indicated"]
    systolic: int | None = Field(default=None, ge=40, le=300)
    diastolic: int | None = Field(default=None, ge=20, le=200)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_assessment(self):
        if self.method == "not_indicated":
            if self.systolic is not None or self.diastolic is not None or len(self.note.strip()) < 5:
                raise ValueError("For not_indicated, omit readings and document a reason of at least five characters")
        else:
            if self.systolic is None or self.diastolic is None or self.systolic <= self.diastolic:
                raise ValueError("A valid systolic and diastolic reading is required")
        return self


class ReferralOwnerAssignment(BaseModel):
    owner_user_id: str = Field(min_length=1, max_length=36)


class ReferralRedirect(BaseModel):
    facility_id: str = Field(min_length=1, max_length=36)


class OTPRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=24)


class OTPVerify(BaseModel):
    phone: str = Field(min_length=8, max_length=24)
    code: str = Field(pattern=r"^\d{6}$")


class ConsentRevoke(BaseModel):
    reason: str = Field(default="patient_request", min_length=2, max_length=80)


class FollowUpCreate(BaseModel):
    due_date: datetime
    plan_type: Literal["7_day", "30_day", "repeat_assessment", "bp_control_check"] = "30_day"

    @field_validator("due_date")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Due date must include a timezone")
        return value


class FollowUpAssessment(BaseModel):
    systolic: int = Field(ge=40, le=300)
    diastolic: int = Field(ge=20, le=200)

    @model_validator(mode="after")
    def check_pressure(self):
        if self.systolic <= self.diastolic:
            raise ValueError("Systolic must exceed diastolic")
        return self


class BPControlCreate(FollowUpAssessment):
    bp_controlled: bool


class CaseMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class AlertAcknowledge(BaseModel):
    note: str = Field(default="", max_length=1000)


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    type: Literal["pharmacy", "pmv", "hospital", "hmo", "donor", "chw"]
    lga: str | None = Field(default=None, max_length=100)
