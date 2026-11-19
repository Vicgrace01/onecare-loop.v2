from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.core.security import create_access_token
from app.db.models import Organisation, User
from app.schemas.auth import AuthResponse, LoginRequest, ProvisionUserRequest, RegisterRequest, UserView
from app.services.auth import AuthenticationError, authenticate, provision_staff_user, register_patient
from app.services.privacy import decrypt_account_email

router = APIRouter(prefix="/auth", tags=["authentication"])


def _auth_response(user: User, request: Request) -> AuthResponse:
    settings = request.app.state.settings
    token = create_access_token(user.id, settings.secret_key, settings.access_token_ttl_seconds)
    view = _user_view(user, settings)
    return AuthResponse(access_token=token, expires_in=settings.access_token_ttl_seconds, user=view)


def _user_view(user: User, settings) -> UserView:
    return UserView(
        id=user.id,
        email=decrypt_account_email(user.email_ciphertext, settings),
        role=user.role,
        organisation_id=user.organisation_id,
        patient_id=user.patient_id,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    settings = request.app.state.settings
    if not settings.self_registration_enabled:
        raise HTTPException(status_code=403, detail="Self-registration is disabled")
    try:
        user = register_patient(db, email=str(body.email), password=body.password, display_name=body.display_name, settings=settings)
    except AuthenticationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
    return _auth_response(user, request)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate(db, email=str(body.email), password=body.password, settings=request.app.state.settings)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login_at = datetime.now(timezone.utc)
    return _auth_response(user, request)


@router.get("/me", response_model=UserView)
def me(request: Request, user: User = Depends(get_current_user)) -> UserView:
    return _user_view(user, request.app.state.settings)


@router.post("/provision", response_model=UserView, status_code=status.HTTP_201_CREATED)
def provision_staff(
    body: ProvisionUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> UserView:
    try:
        if not body.organisation_id:
            raise HTTPException(status_code=422, detail="Staff accounts must be assigned to an organisation")
        organisation = db.get(Organisation, body.organisation_id)
        expected_type = "hospital" if body.role == "clinician" else body.role
        if organisation is None or organisation.type != expected_type:
            raise HTTPException(status_code=422, detail="Staff role must match the assigned organisation type")
        user = provision_staff_user(
            db,
            email=str(body.email),
            password=body.password,
            role=body.role,
            organisation_id=body.organisation_id,
            settings=request.app.state.settings,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invalid organisation or duplicate email") from exc
    return _user_view(user, request.app.state.settings)
