"""Health + dev bootstrap (development convenience, not production auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import BootstrapIn, BootstrapOut
from app.db.session import get_session
from app.modules.organizations.models import Organization, User

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/dev/bootstrap", response_model=BootstrapOut, status_code=201)
def bootstrap(body: BootstrapIn, session: Session = Depends(get_session)) -> BootstrapOut:
    """Create an org + recruiter and return the ids to use as X-Org-Id / X-User-Id.
    Development helper only — real onboarding/auth replaces this."""
    org = Organization(name=body.org_name)
    session.add(org)
    session.flush()
    user = User(org_id=org.id, email=body.user_email, role="recruiter")
    session.add(user)
    session.flush()
    return BootstrapOut(org_id=org.id, user_id=user.id, role=user.role)
