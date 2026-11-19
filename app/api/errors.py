from fastapi import HTTPException

from app.services.care import CareError
from app.domain.states import TransitionError


def raise_api_error(exc: Exception) -> None:
    if isinstance(exc, CareError):
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.reason, "message": exc.message}) from exc
    if isinstance(exc, TransitionError):
        raise HTTPException(status_code=409, detail={"code": exc.reason, "message": exc.message}) from exc
    raise exc
