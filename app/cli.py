from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import build_engine, build_session_factory
from app.services.auth import set_encrypted_email
from app.services.privacy import email_lookup_token
from app.services.care import process_overdue_referrals


def create_first_admin(email: str, password: str) -> str:
    settings = get_settings()
    normalized = email.strip().lower()
    if len(password) < 12:
        raise ValueError("Administrator password must contain at least 12 characters")
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    try:
        with factory() as db:
            lookup = email_lookup_token(normalized, settings)
            existing = db.scalar(select(User).where(User.email_normalized == lookup))
            if existing is not None:
                raise ValueError("An account with this email already exists")
            user = User(
                email="pending@onecare.invalid",
                email_normalized="pending:first-admin-bootstrap",
                password_hash=hash_password(password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(user)
            db.flush()
            set_encrypted_email(user, normalized, settings)
            db.commit()
            return user.id
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="OneCare Loop administration commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin", help="Create the first or an additional administrator account")
    overdue = subparsers.add_parser("escalate-overdue", help="Create idempotent SLA exceptions for overdue referrals")
    overdue.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    if args.command == "escalate-overdue":
        if args.limit < 1 or args.limit > 5000:
            print("--limit must be between 1 and 5000", file=sys.stderr)
            return 2
        settings = get_settings()
        engine = build_engine(settings.database_url)
        factory = build_session_factory(engine)
        try:
            with factory() as db:
                result = process_overdue_referrals(db, limit=args.limit)
                db.commit()
            print(f"Checked {result['checked']} overdue candidates; created {result['escalated_count']} escalation(s).")
            for referral_id in result["escalated"]:
                print(referral_id)
            return 0
        except Exception as exc:
            print(f"Could not process overdue referrals: {exc}", file=sys.stderr)
            return 1
        finally:
            engine.dispose()

    if args.command == "create-admin":
        email = input("Administrator email: ").strip()
        password = getpass.getpass("Administrator password (12+ characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match", file=sys.stderr)
            return 2
        try:
            user_id = create_first_admin(email, password)
        except Exception as exc:
            print(f"Could not create administrator: {exc}", file=sys.stderr)
            return 1
        print("Administrator account created.")
        print(f"User ID: {user_id}")
        print("Sign in through the OneCare Loop web interface.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
