from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.db.models import Organisation, User
from app.services.privacy import decrypt_account_email
from app.schemas.care import OrganisationCreate

router = APIRouter(prefix="/organisations", tags=["organisations"])


@router.post("", status_code=201)
def create_organisation(body: OrganisationCreate, db: Session = Depends(get_db), _admin: User = Depends(require_roles("admin"))):
    row = Organisation(name=body.name.strip(), type=body.type, lga=body.lga)
    db.add(row)
    db.flush()
    return {"id": row.id, "name": row.name, "type": row.type, "lga": row.lga}


@router.get("")
def list_organisations(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    rows = db.scalars(select(Organisation).order_by(Organisation.name.asc())).all()
    return {"organisations": [{"id": r.id, "name": r.name, "type": r.type, "lga": r.lga} for r in rows]}


@router.get("/{organisation_id}/staff")
def list_organisation_staff(
    organisation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    organisation = db.get(Organisation, organisation_id)
    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if actor.role != "admin" and not (
        actor.organisation_id == organisation_id and actor.role in {"hospital", "clinician"}
    ):
        raise HTTPException(status_code=403, detail="You cannot view this organisation's staff")
    users = db.scalars(
        select(User).where(
            User.organisation_id == organisation_id,
            User.is_active.is_(True),
            User.role.in_(["hospital", "clinician"]),
        ).order_by(User.role.asc(), User.created_at.asc())
    ).all()
    settings = request.app.state.settings
    return {
        "organisation_id": organisation_id,
        "staff": [
            {
                "id": user.id,
                "email": decrypt_account_email(user.email_ciphertext, settings),
                "role": user.role,
            }
            for user in users
        ],
    }
