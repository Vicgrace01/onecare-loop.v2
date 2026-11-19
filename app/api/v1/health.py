from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness(request: Request) -> dict:
    return {"ok": True, "service": "onecare-loop", "version": request.app.state.settings.app_version}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"ok": True, "database": "available"}
