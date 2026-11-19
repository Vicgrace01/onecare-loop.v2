from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AccessLog, Appointment, ClinicalDisposition, Encounter, LedgerEvent, Patient, Referral, Screening, User, Organisation, utc_now
from app.services.care import CareError, _require_patient_access
from app.services.privacy import decrypt_ledger_payload, decrypt_patient_value

FHIR_BASE = "http://hl7.org/fhir"


def _bundle_ref(resource_id: str) -> str:
    return f"urn:uuid:{resource_id}"


def _resource_id(kind: str, source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"onecare:{kind}:{source_id}"))


def _tag(event: LedgerEvent) -> list[dict[str, str]]:
    return [{"system": "https://onecare.example.ng/fhir/ledger-event", "code": event.event_hash,
             "display": f"OneCare ledger event sequence {event.seq}"}]


def _observation(event: LedgerEvent, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "Observation", "id": _resource_id("observation", event.id),
        "meta": {"tag": _tag(event)}, "status": "final",
        "category": [{"coding": [{"system": f"{FHIR_BASE}/observation-category", "code": "vital-signs"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}]},
        "subject": {"reference": _bundle_ref(event.patient_id)},
        "effectiveDateTime": event.occurred_at.isoformat(),
        "performer": [{"reference": _bundle_ref(event.actor_id)}],
        "component": [
            {"code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
             "valueQuantity": {"value": payload.get("systolic"), "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}},
            {"code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]},
             "valueQuantity": {"value": payload.get("diastolic"), "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}},
        ],
    }


def build_patient_bundle(db: Session, *, actor: User, patient_id: str, settings: Settings) -> dict[str, Any]:
    patient = _require_patient_access(db, actor, patient_id)
    events = db.scalars(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.asc())).all()
    if not events:
        raise CareError("patient_history_empty", "No recorded care events exist for this patient", 404)
    resources: list[dict[str, Any]] = [{
        "resourceType": "Patient", "id": patient.id,
        "meta": {"profile": [f"{FHIR_BASE}/StructureDefinition/Patient"]},
        # PII is intentionally omitted from interoperability export.
        "active": True,
    }]
    referral_ids = {e.referral_id for e in events if e.referral_id}
    referrals = {r.id: r for r in db.scalars(select(Referral).where(Referral.id.in_(referral_ids))).all()} if referral_ids else {}
    appointment_by_referral: dict[str, Appointment] = {}
    encounter_by_appointment: dict[str, Encounter] = {}
    disposition_by_encounter: dict[str, ClinicalDisposition] = {}
    if referral_ids:
        appointments = db.scalars(select(Appointment).where(Appointment.referral_id.in_(referral_ids)).order_by(Appointment.created_at.asc())).all()
        for item in appointments:
            appointment_by_referral[item.referral_id] = item
        if appointments:
            encounter_rows = db.scalars(select(Encounter).where(Encounter.appointment_id.in_([a.id for a in appointments])).order_by(Encounter.created_at.asc())).all()
            for item in encounter_rows:
                encounter_by_appointment[item.appointment_id] = item
            if encounter_rows:
                disposition_rows = db.scalars(select(ClinicalDisposition).where(ClinicalDisposition.encounter_id.in_([e.id for e in encounter_rows]))).all()
                for item in disposition_rows:
                    disposition_by_encounter[item.encounter_id] = item

    practitioner_ids: set[str] = set()
    organisation_ids: set[str] = set()
    for event in events:
        payload = decrypt_ledger_payload(db, patient_id, event.payload or {}, settings)
        if payload is None:
            continue
        tags = _tag(event)
        practitioner_ids.add(event.actor_id)
        if payload.get("facility_id"):
            organisation_ids.add(payload["facility_id"])
        if event.event_type in {"SCREEN_POSITIVE", "SCREEN_NEGATIVE", "REPEAT_ASSESSMENT", "BP_CONTROL_RECORDED"}:
            resources.append(_observation(event, payload))
        elif event.event_type == "CONFIRMATORY_TEST_RECORDED" and payload.get("systolic") is not None:
            observation = _observation(event, payload)
            observation["id"] = _resource_id("confirmatory-observation", event.id)
            observation["category"][0]["coding"][0]["code"] = "vital-signs"
            observation["code"]["text"] = f"Confirmatory blood pressure assessment ({payload.get('method', 'unspecified')})"
            resources.append(observation)
        if event.event_type == "REFERRAL_CREATED" and event.referral_id:
            ref = referrals.get(event.referral_id)
            if ref:
                resources.append({
                    "resourceType": "ServiceRequest", "id": ref.id,
                    "meta": {"tag": tags}, "status": "active", "intent": "order",
                    "priority": ref.urgency,
                    "code": {"coding": [{"system": "https://onecare.example.ng/fhir/referral", "code": "hypertension-review"}]},
                    "subject": {"reference": _bundle_ref(patient_id)},
                    "requester": {"reference": _bundle_ref(event.actor_id)},
                    "performer": [{"reference": _bundle_ref(ref.facility_id)}],
                    "authoredOn": event.occurred_at.isoformat(),
                })
        elif event.event_type == "FACILITY_ACCEPTED" and event.referral_id:
            resources.append({
                "resourceType": "Task", "id": _resource_id("task", event.id), "meta": {"tag": tags},
                "status": "accepted", "intent": "order", "for": {"reference": _bundle_ref(patient_id)},
                "owner": {"reference": _bundle_ref(payload["facility_id"])},
            })
        elif event.event_type == "APPOINTMENT_BOOKED" and event.referral_id:
            appointment = appointment_by_referral.get(event.referral_id)
            if appointment:
                resources.append({
                    "resourceType": "Appointment", "id": appointment.id, "meta": {"tag": tags},
                    "status": "booked", "start": appointment.slot_start.isoformat(), "end": appointment.slot_end.isoformat(),
                    "participant": [
                        {"actor": {"reference": _bundle_ref(patient_id)}, "status": "accepted"},
                        {"actor": {"reference": _bundle_ref(payload["facility_id"])}, "status": "accepted"},
                    ],
                })
        elif event.event_type == "CLINICAL_ENCOUNTER_COMPLETED" and event.referral_id:
            appointment = appointment_by_referral.get(event.referral_id)
            encounter = encounter_by_appointment.get(appointment.id) if appointment else None
            if encounter:
                resources.append({
                    "resourceType": "Encounter", "id": encounter.id, "meta": {"tag": tags},
                    "status": "finished", "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
                    "subject": {"reference": _bundle_ref(patient_id)},
                    "participant": [{"individual": {"reference": _bundle_ref(encounter.clinician_id)}}],
                    "period": {"start": encounter.attended_at.isoformat()},
                })
        elif event.event_type == "CLINICAL_DISPOSITION_RETURNED" and event.referral_id:
            appointment = appointment_by_referral.get(event.referral_id)
            encounter = encounter_by_appointment.get(appointment.id) if appointment else None
            disposition = disposition_by_encounter.get(encounter.id) if encounter else None
            if disposition:
                resources.append({
                    "resourceType": "ClinicalImpression", "id": disposition.id, "meta": {"tag": tags},
                    "status": "completed", "subject": {"reference": _bundle_ref(patient_id)},
                    "date": disposition.signed_at.isoformat(),
                    "summary": payload.get("outcome", ""),
                    "note": [{"text": payload.get("next_step", "")}],
                })
    # Include reference targets so the FHIR resources do not point at missing actors/facilities.
    for practitioner_id in sorted(practitioner_ids):
        resources.append({"resourceType": "Practitioner", "id": practitioner_id, "active": True})
    if organisation_ids:
        organisations = db.scalars(select(Organisation).where(Organisation.id.in_(organisation_ids))).all()
        for org in organisations:
            resources.append({"resourceType": "Organization", "id": org.id, "active": True, "name": org.name})
    db.add(AccessLog(actor_id=actor.id, resource_type="fhir_bundle", resource_id=patient_id, purpose="care_coordination_export"))
    entries = [{"fullUrl": _bundle_ref(r["id"]), "resource": r} for r in resources]
    return {"resourceType": "Bundle", "id": str(uuid.uuid4()), "type": "collection",
            "timestamp": utc_now().isoformat(), "total": len(entries), "entry": entries}


def capability_statement() -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement", "id": "onecare-loop", "status": "active",
        "date": utc_now().isoformat(), "publisher": "OneCare Loop", "kind": "instance",
        "software": {"name": "OneCare Loop", "version": "2.0.0"}, "fhirVersion": "4.0.1",
        "format": ["json"], "implementation": {"description": "Read-only export of hypertension referral and care coordination records"},
        "rest": [{
            "mode": "server",
            "documentation": "The application exposes authenticated FHIR R4 collection Bundles at /api/v1/fhir/patients/{patient_id}/bundle. It does not expose individual FHIR resource read endpoints.",
            "resource": [],
        }],
    }
