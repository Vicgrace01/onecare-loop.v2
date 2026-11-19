import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Organisation, Patient, Screening


def test_screening_constraints_reject_impossible_measurements(app):
    application, _ = app
    with application.state.session_factory() as db:
        organisation = Organisation(name="Clinic", type="pharmacy")
        patient = Patient(display_name="Test Patient")
        db.add_all([organisation, patient])
        db.flush()
        db.add(
            Screening(
                patient_id=patient.id,
                organisation_id=organisation.id,
                systolic=80,
                diastolic=120,
                symptoms=[],
                protocol_version="v1",
                result="positive",
                red_flag=False,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_organisation_type_is_constrained(app):
    application, _ = app
    with application.state.session_factory() as db:
        db.add(Organisation(name="Unknown Provider", type="unknown_type"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
