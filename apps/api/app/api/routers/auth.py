"""Authentication endpoints: login (set cookie), logout (revoke), and whoami."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import LoginIn, MeOut
from app.config import settings
from app.db.session import get_session
from app.modules.organizations.auth import authenticate, create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)) -> MeOut:
    user = authenticate(session, email=body.email, password=body.password)
    if user is None:
        raise DomainError("Invalid email or password.", code="unauthorized", status_code=401)
    token = create_session(session, user=user, ttl=timedelta(hours=settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return MeOut(org_id=user.org_id, user_id=user.id, role=user.role)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Response:
    revoke_session(session, session_cookie)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_principal)) -> MeOut:
    return MeOut(org_id=principal.org_id, user_id=principal.user_id, role=principal.role)
