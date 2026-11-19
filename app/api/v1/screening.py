from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.api.errors import raise_api_error
from app.db.models import User
from app.schemas.care import ScreeningCreate
from app.services.care import create_screening

router = APIRouter(prefix="/screenings", tags=["screening"])


@router.post("", status_code=201)
def post_screening(body: ScreeningCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("pharmacy", "pmv"))):
    try:
        return create_screening(db, actor=actor, body=body.model_dump(), settings=request.app.state.settings)
    except Exception as exc:
        raise_api_error(exc)
