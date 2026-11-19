from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import User
from app.services.fhir import build_patient_bundle, capability_statement

router = APIRouter(prefix="/fhir", tags=["FHIR R4"])


@router.get("/metadata")
def metadata(_actor: User = Depends(require_roles("admin", "hospital", "clinician", "pharmacy", "pmv"))):
    return capability_statement()


@router.get("/patients/{patient_id}/bundle")
def patient_bundle(patient_id: str, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "hospital", "clinician", "pharmacy", "pmv", "patient"))):
    try:
        return build_patient_bundle(db, actor=actor, patient_id=patient_id, settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)
