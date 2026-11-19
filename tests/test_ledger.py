from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import LedgerEvent, Organisation, Patient, User
from app.domain.ledger import record_transition, verify_patient_chain
from app.domain.states import TransitionError


def _fixtures(application):
    with application.state.session_factory() as db:
        with db.begin():
            org = Organisation(name="Test Pharmacy", type="pharmacy")
            patient = Patient(display_name="Patient A")
            db.add_all([org, patient])
            db.flush()
            actor = User(
                email="pharm@example.com",
                email_normalized="pharm@example.com",
                password_hash=hash_password("a-long-unique-password-123"),
                role="pharmacy",
                organisation=org,
            )
            db.add(actor)
            db.flush()
            ids = patient.id, actor.id
        return ids


def test_event_chain_and_ed25519_signatures_verify(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    settings = application.state.settings
    with application.state.session_factory() as db:
        with db.begin():
            actor = db.get(User, actor_id)
            first = record_transition(
                db,
                patient_id=patient_id,
                target_state="SCREEN_POSITIVE",
                actor=actor,
                payload={"protocol_version": "HTN-PROTOCOL-v1", "systolic": 168, "diastolic": 104},
                settings=settings,
            )
            second = record_transition(
                db,
                patient_id=patient_id,
                target_state="REFERRAL_CREATED",
                actor=actor,
                payload={"facility_id": "FACILITY-A", "consent_version": "1.0", "consent_hash": "abc123"},
                referral_id="referral-1",
                settings=settings,
            )
            assert first.seq == 1
            assert second.seq == 2
        result = verify_patient_chain(db, patient_id)
        assert result["ok"] is True
        assert result["events"] == 2
        events = db.scalars(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id)).all()
        assert all(event.actor_signature and event.actor_public_key for event in events)
        assert events[1].prev_hash == events[0].event_hash


def test_tampering_with_event_payload_is_detected(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    settings = application.state.settings
    with application.state.session_factory() as db:
        with db.begin():
            actor = db.get(User, actor_id)
            record_transition(
                db, patient_id=patient_id, target_state="SCREEN_POSITIVE", actor=actor,
                payload={"protocol_version": "v1", "systolic": 150, "diastolic": 95}, settings=settings,
            )
        event = db.scalar(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id))
        event.payload = {"protocol_version": "v1", "systolic": 120, "diastolic": 80}
        db.commit()
        result = verify_patient_chain(db, patient_id)
        assert result["ok"] is False
        assert result["broken_at"]["reason"] == "hash_mismatch"
        assert result["broken_at"]["seq"] == 1


def test_invalid_transition_does_not_append_event(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    with application.state.session_factory() as db:
        with db.begin():
            actor = db.get(User, actor_id)
            record_transition(
                db, patient_id=patient_id, target_state="SCREEN_POSITIVE", actor=actor,
                payload={"protocol_version": "v1", "systolic": 150, "diastolic": 95}, settings=application.state.settings,
            )
        with db.begin():
            actor = db.get(User, actor_id)
            try:
                record_transition(
                    db, patient_id=patient_id, target_state="FACILITY_ACCEPTED", actor=actor,
                    payload={"facility_id": "FACILITY-A"}, settings=application.state.settings,
                )
            except TransitionError as exc:
                assert exc.reason == "invalid_transition"
            else:
                raise AssertionError("Invalid transition should have raised")
        count = db.scalar(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id))
        assert count is not None
        assert db.scalar(select(LedgerEvent.seq).where(LedgerEvent.patient_id == patient_id).order_by(LedgerEvent.seq.desc())) == 1


def test_transaction_rollback_also_rolls_back_ledger_and_head(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    with application.state.session_factory() as db:
        try:
            with db.begin():
                actor = db.get(User, actor_id)
                record_transition(
                    db, patient_id=patient_id, target_state="SCREEN_POSITIVE", actor=actor,
                    payload={"protocol_version": "v1", "systolic": 150, "diastolic": 95}, settings=application.state.settings,
                )
                raise RuntimeError("simulate downstream failure")
        except RuntimeError:
            pass
        assert db.scalar(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id)) is None
        assert verify_patient_chain(db, patient_id)["events"] == 0


def test_declined_referral_has_a_valid_redirect_recovery_path(app):
    application, _ = app
    patient_id, pharmacy_id = _fixtures(application)
    with application.state.session_factory() as db:
        with db.begin():
            hospital_org = Organisation(name="Receiving Hospital", type="hospital")
            db.add(hospital_org)
            db.flush()
            hospital = User(
                email="hospital@example.com",
                email_normalized="hospital@example.com",
                password_hash=hash_password("a-long-unique-password-123"),
                role="hospital",
                organisation=hospital_org,
            )
            db.add(hospital)
            db.flush()
            pharmacy = db.get(User, pharmacy_id)
            record_transition(
                db, patient_id=patient_id, target_state="SCREEN_POSITIVE", actor=pharmacy,
                payload={"protocol_version": "v1", "systolic": 168, "diastolic": 104},
                settings=application.state.settings,
            )
            record_transition(
                db, patient_id=patient_id, target_state="REFERRAL_CREATED", actor=pharmacy,
                payload={"facility_id": "FACILITY-A", "consent_version": "1.0", "consent_hash": "consent-hash"},
                referral_id="ref-a", settings=application.state.settings,
            )
            record_transition(
                db, patient_id=patient_id, target_state="REFERRAL_DECLINED", actor=hospital,
                payload={"reason_code": "no_slots", "owner": "care_navigator"},
                referral_id="ref-a", settings=application.state.settings,
            )
            record_transition(
                db, patient_id=patient_id, target_state="REFERRAL_REDIRECTED", actor=hospital,
                payload={"reason_code": "no_slots", "previous_facility_id": "FACILITY-A", "facility_id": "FACILITY-B"},
                referral_id="ref-a", settings=application.state.settings,
            )
            final = record_transition(
                db, patient_id=patient_id, target_state="REFERRAL_CREATED", actor=hospital,
                payload={"facility_id": "FACILITY-B", "consent_version": "1.0", "consent_hash": "consent-hash"},
                referral_id="ref-b", settings=application.state.settings,
            )
            assert final.seq == 5
        assert verify_patient_chain(db, patient_id)["ok"] is True


def test_negative_screening_does_not_start_a_referral_loop(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    with application.state.session_factory() as db:
        with db.begin():
            actor = db.get(User, actor_id)
            record_transition(
                db, patient_id=patient_id, target_state="SCREEN_NEGATIVE", actor=actor,
                payload={"protocol_version": "v1", "systolic": 120, "diastolic": 80},
                settings=application.state.settings,
            )
        with db.begin():
            actor = db.get(User, actor_id)
            try:
                record_transition(
                    db, patient_id=patient_id, target_state="REFERRAL_CREATED", actor=actor,
                    payload={"facility_id": "FACILITY-A", "consent_version": "1.0", "consent_hash": "hash"},
                    settings=application.state.settings,
                )
            except TransitionError as exc:
                assert exc.reason == "invalid_transition"
            else:
                raise AssertionError("A negative screen must not start a referral")



def test_public_key_is_committed_to_event_hash(app):
    application, _ = app
    patient_id, actor_id = _fixtures(application)
    with application.state.session_factory() as db:
        with db.begin():
            actor = db.get(User, actor_id)
            record_transition(
                db, patient_id=patient_id, target_state="SCREEN_POSITIVE", actor=actor,
                payload={"protocol_version": "v1", "systolic": 150, "diastolic": 95},
                settings=application.state.settings,
            )
        event = db.scalar(select(LedgerEvent).where(LedgerEvent.patient_id == patient_id))
        event.actor_public_key = event.actor_public_key + "\n "
        db.commit()
        result = verify_patient_chain(db, patient_id)
        assert result["ok"] is False
        assert result["broken_at"]["reason"] == "hash_mismatch"
