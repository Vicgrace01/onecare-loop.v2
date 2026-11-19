from __future__ import annotations

from contextlib import asynccontextmanager
from collections import defaultdict, deque
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Organisation, User, UserRole
from app.db.session import build_engine, build_session_factory
from app.services.auth import set_encrypted_email
from app.services.privacy import email_lookup_token
from sqlalchemy import select


def _seed_demo_admin(session_factory, settings: Settings) -> None:
    if not settings.seed_demo_admin:
        return
    if not settings.demo_admin_password or len(settings.demo_admin_password) < 12:
        raise RuntimeError("SEED_DEMO_ADMIN requires DEMO_ADMIN_PASSWORD with at least 12 characters")
    with session_factory() as db:
        normalized_email = settings.demo_admin_email.strip().lower()
        lookup = email_lookup_token(normalized_email, settings)
        existing = db.query(User).filter(User.email_normalized.in_([lookup, normalized_email])).first()
        if existing:
            return
        admin = User(
            email="pending@onecare.invalid",
            email_normalized="pending:demo-admin",
            password_hash=hash_password(settings.demo_admin_password),
            role=UserRole.ADMIN.value,
        )
        db.add(admin)
        db.flush()
        set_encrypted_email(admin, normalized_email, settings)
        db.commit()



def _seed_demo_environment(session_factory, settings: Settings) -> None:
    """Provision isolated synthetic-only personas for the public judge workspace."""
    if not settings.demo_mode_enabled:
        return

    def ensure_org(db, name: str, org_type: str, lga: str) -> Organisation:
        row = db.scalar(select(Organisation).where(Organisation.name == name, Organisation.type == org_type))
        if row is None:
            row = Organisation(name=name, type=org_type, lga=lga)
            db.add(row)
            db.flush()
        return row

    def ensure_user(db, email: str, password: str, role: str, org: Organisation) -> User:
        lookup = email_lookup_token(email.strip().lower(), settings)
        user = db.scalar(select(User).where(User.email_normalized == lookup))
        if user is not None:
            if user.role != role or user.organisation_id != org.id:
                raise RuntimeError(f"Configured demo account {email} conflicts with an existing account")
            # Keep the configured challenge credentials authoritative on each boot.
            user.password_hash = hash_password(password)
            user.is_active = True
            return user
        from app.services.auth import provision_staff_user
        return provision_staff_user(db, email=email, password=password, role=role,
                                    organisation_id=org.id, settings=settings)

    with session_factory() as db:
        pharmacy_org = ensure_org(db, "OneCare Demo Community Pharmacy", "pharmacy", "Yaba")
        hospital_org = ensure_org(db, "OneCare Demo Hospital", "hospital", "Lagos Mainland")
        hmo_org = ensure_org(db, "OneCare Demo Health Plan", "hmo", "Lagos")
        ensure_user(db, settings.demo_pharmacy_email, settings.demo_pharmacy_password, "pharmacy", pharmacy_org)
        ensure_user(db, settings.demo_hospital_email, settings.demo_hospital_password, "hospital", hospital_org)
        ensure_user(db, settings.demo_clinician_email, settings.demo_clinician_password, "clinician", hospital_org)
        ensure_user(db, settings.demo_hmo_email, settings.demo_hmo_password, "hmo", hmo_org)
        db.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    engine = build_engine(runtime_settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.auto_create_schema:
            Base.metadata.create_all(bind=engine)
        _seed_demo_admin(session_factory, runtime_settings)
        _seed_demo_environment(session_factory, runtime_settings)
        yield
        engine.dispose()

    application = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        description="A verifiable referral-closure platform for hypertension care pathways.",
        docs_url=None if runtime_settings.app_env.lower() == "production" else "/docs",
        redoc_url=None if runtime_settings.app_env.lower() == "production" else "/redoc",
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.demo_rate_limiter = defaultdict(deque)

    if runtime_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

    application.include_router(api_router, prefix=runtime_settings.api_v1_prefix)

    web_dir = Path(__file__).resolve().parent / "web"
    application.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        return response

    @application.get("/", include_in_schema=False)
    def root():
        return FileResponse(web_dir / "index.html", media_type="text/html")

    @application.get("/demo", include_in_schema=False)
    def judge_demo():
        # Always serve the shell: it can explain when the live demo is disabled.
        # The API endpoint remains fail-closed until DEMO_MODE_ENABLED=true.
        return FileResponse(web_dir / "demo.html", media_type="text/html")

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(web_dir / "assets" / "mark.svg", media_type="image/svg+xml")

    return application


app = create_app()
