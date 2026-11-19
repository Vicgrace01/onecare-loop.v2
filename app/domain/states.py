from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

GENESIS_HASH = "0" * 64

CANONICAL_STATES = frozenset({
    "SCREEN_POSITIVE",
    "REFERRAL_CREATED",
    "FACILITY_ACCEPTED",
    "APPOINTMENT_BOOKED",
    "CLINICAL_ENCOUNTER_COMPLETED",
    "CLINICAL_DISPOSITION_RETURNED",
})

FAILURE_STATES = frozenset({
    "REFERRAL_DECLINED",
    "FACILITY_UNAVAILABLE",
    "REFERRAL_REDIRECTED",
    "APPOINTMENT_MISSED",
    "PATIENT_UNREACHABLE",
    "PATIENT_DECLINED",
    "PATIENT_REQUESTED_RESCHEDULE",
    "FOLLOWUP_OVERDUE",
})

LONGITUDINAL_STATES = frozenset({"FOLLOWUP_DUE", "REPEAT_ASSESSMENT", "BP_CONTROL_RECORDED"})
SCREENING_TERMINAL_STATES = frozenset({"SCREEN_NEGATIVE", "SCREENING_INCONCLUSIVE"})
ALL_STATES = CANONICAL_STATES | FAILURE_STATES | LONGITUDINAL_STATES | SCREENING_TERMINAL_STATES


@dataclass(frozen=True)
class TransitionRule:
    roles: frozenset[str]
    required_fields: frozenset[str] = frozenset()


RULES: dict[tuple[str | None, str], TransitionRule] = {
    # A screening may conclude without a referral. Only a positive screen starts the care loop.
    (None, "SCREEN_POSITIVE"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "systolic", "diastolic"})
    ),
    (None, "SCREEN_NEGATIVE"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "systolic", "diastolic"})
    ),
    (None, "SCREENING_INCONCLUSIVE"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "reason_code"})
    ),

    # Canonical referral and clinical journey.
    ("SCREEN_POSITIVE", "REFERRAL_CREATED"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"consent_version", "consent_hash", "facility_id"})
    ),
    ("REFERRAL_CREATED", "FACILITY_ACCEPTED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"facility_id"})
    ),
    ("FACILITY_ACCEPTED", "APPOINTMENT_BOOKED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"facility_id", "slot_start", "slot_end"})
    ),
    ("APPOINTMENT_BOOKED", "CLINICAL_ENCOUNTER_COMPLETED"): TransitionRule(
        frozenset({"hospital", "clinician"}), frozenset({"attended", "clinician_id"})
    ),
    ("CLINICAL_ENCOUNTER_COMPLETED", "CLINICAL_DISPOSITION_RETURNED"): TransitionRule(
        frozenset({"clinician"}), frozenset({"clinician_id", "outcome", "next_step"})
    ),

    # Explicit failure states and recovery paths.
    ("REFERRAL_CREATED", "REFERRAL_DECLINED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("REFERRAL_CREATED", "FACILITY_UNAVAILABLE"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("REFERRAL_CREATED", "PATIENT_UNREACHABLE"): TransitionRule(
        frozenset({"pharmacy", "hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("REFERRAL_CREATED", "PATIENT_DECLINED"): TransitionRule(
        frozenset({"pharmacy", "hospital", "patient"}), frozenset({"reason_code", "owner"})
    ),
    ("FACILITY_ACCEPTED", "PATIENT_UNREACHABLE"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("FACILITY_ACCEPTED", "PATIENT_DECLINED"): TransitionRule(
        frozenset({"hospital", "patient"}), frozenset({"reason_code", "owner"})
    ),
    ("APPOINTMENT_BOOKED", "APPOINTMENT_MISSED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("APPOINTMENT_BOOKED", "PATIENT_UNREACHABLE"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("APPOINTMENT_BOOKED", "PATIENT_DECLINED"): TransitionRule(
        frozenset({"hospital", "patient"}), frozenset({"reason_code", "owner"})
    ),
    ("APPOINTMENT_BOOKED", "PATIENT_REQUESTED_RESCHEDULE"): TransitionRule(
        frozenset({"patient", "pharmacy", "hospital"}), frozenset({"reason_code", "owner"})
    ),
    ("REFERRAL_DECLINED", "REFERRAL_REDIRECTED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "previous_facility_id", "facility_id"})
    ),
    ("FACILITY_UNAVAILABLE", "REFERRAL_REDIRECTED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"reason_code", "previous_facility_id", "facility_id"})
    ),
    ("REFERRAL_REDIRECTED", "REFERRAL_CREATED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"facility_id", "consent_version", "consent_hash"})
    ),
    ("PATIENT_UNREACHABLE", "REFERRAL_CREATED"): TransitionRule(
        frozenset({"pharmacy", "hospital"}), frozenset({"facility_id", "consent_version", "consent_hash"})
    ),
    ("PATIENT_DECLINED", "REFERRAL_CREATED"): TransitionRule(
        frozenset({"pharmacy", "hospital"}), frozenset({"facility_id", "consent_version", "consent_hash"})
    ),
    ("APPOINTMENT_MISSED", "APPOINTMENT_BOOKED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"facility_id", "slot_start", "slot_end"})
    ),
    ("PATIENT_REQUESTED_RESCHEDULE", "APPOINTMENT_BOOKED"): TransitionRule(
        frozenset({"hospital"}), frozenset({"facility_id", "slot_start", "slot_end"})
    ),

    # Longitudinal follow-up after clinical disposition.
    ("CLINICAL_DISPOSITION_RETURNED", "FOLLOWUP_DUE"): TransitionRule(
        frozenset({"clinician"}), frozenset({"due_date", "followup_type"})
    ),
    ("FOLLOWUP_DUE", "REPEAT_ASSESSMENT"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"systolic", "diastolic"})
    ),
    ("REPEAT_ASSESSMENT", "BP_CONTROL_RECORDED"): TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"systolic", "diastolic", "bp_controlled"})
    ),
    ("BP_CONTROL_RECORDED", "FOLLOWUP_DUE"): TransitionRule(
        frozenset({"clinician"}), frozenset({"due_date", "followup_type"})
    ),
    ("CLINICAL_DISPOSITION_RETURNED", "FOLLOWUP_OVERDUE"): TransitionRule(
        frozenset({"system", "clinician"}), frozenset({"reason_code", "owner"})
    ),
    ("FOLLOWUP_OVERDUE", "FOLLOWUP_DUE"): TransitionRule(
        frozenset({"clinician"}), frozenset({"due_date", "followup_type"})
    ),
}

# A new screening starts a new episode on the same patient chain only after the
# previous episode reached a terminal screening, completed disposition, or explicit
# failure state. An active referral/appointment cannot be bypassed by re-screening.
_NEW_EPISODE_PREDECESSORS = (
    "SCREEN_NEGATIVE", "SCREENING_INCONCLUSIVE", "CLINICAL_DISPOSITION_RETURNED",
    "BP_CONTROL_RECORDED", "PATIENT_DECLINED", "REFERRAL_DECLINED",
    "FACILITY_UNAVAILABLE",
)
for _previous in _NEW_EPISODE_PREDECESSORS:
    RULES[(_previous, "SCREEN_POSITIVE")] = TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "systolic", "diastolic"})
    )
    RULES[(_previous, "SCREEN_NEGATIVE")] = TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "systolic", "diastolic"})
    )
    RULES[(_previous, "SCREENING_INCONCLUSIVE")] = TransitionRule(
        frozenset({"pharmacy", "pmv"}), frozenset({"protocol_version", "reason_code"})
    )


class TransitionError(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _parse_aware_datetime(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise TransitionError("invalid_datetime", f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransitionError("timezone_required", f"{field} must include a timezone offset")
    return parsed


def _validate_bp(payload: dict) -> None:
    systolic = payload.get("systolic")
    diastolic = payload.get("diastolic")
    if (
        isinstance(systolic, bool)
        or isinstance(diastolic, bool)
        or not isinstance(systolic, int)
        or not isinstance(diastolic, int)
    ):
        raise TransitionError("invalid_measurement", "Blood pressure values must be integers")
    if not 40 <= systolic <= 300 or not 20 <= diastolic <= 200 or systolic <= diastolic:
        raise TransitionError("invalid_measurement", "Blood pressure values are outside valid recording ranges")


def validate_transition(current_state: str | None, target_state: str, actor_role: str, payload: dict) -> None:
    if target_state not in ALL_STATES:
        raise TransitionError("unknown_state", f"Unknown target state: {target_state}")
    rule = RULES.get((current_state, target_state))
    if rule is None:
        raise TransitionError("invalid_transition", f"Cannot move from {current_state!r} to {target_state!r}")
    if actor_role not in rule.roles:
        raise TransitionError("wrong_actor", f"Role {actor_role!r} cannot perform {target_state}")

    missing = sorted(key for key in rule.required_fields if payload.get(key) is None or payload.get(key) == "")
    if missing:
        raise TransitionError("missing_fields", "Missing required fields: " + ", ".join(missing))

    if target_state in {"SCREEN_POSITIVE", "SCREEN_NEGATIVE", "REPEAT_ASSESSMENT", "BP_CONTROL_RECORDED"}:
        _validate_bp(payload)

    if target_state == "CLINICAL_ENCOUNTER_COMPLETED" and payload.get("attended") is not True:
        raise TransitionError("attendance_not_attested", "Hospital attendance must be explicitly attested")

    if target_state == "APPOINTMENT_BOOKED":
        start = _parse_aware_datetime(payload["slot_start"], "slot_start")
        end = _parse_aware_datetime(payload["slot_end"], "slot_end")
        if end <= start:
            raise TransitionError("invalid_appointment_time", "Appointment end must be after start")

    if target_state == "REFERRAL_REDIRECTED":
        if payload["facility_id"] == payload["previous_facility_id"]:
            raise TransitionError("same_facility", "A referral cannot be redirected to the same facility")

    if target_state in {"FOLLOWUP_DUE"}:
        _parse_aware_datetime(payload["due_date"], "due_date")
