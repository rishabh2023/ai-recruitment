"""Authentication endpoints: login (set cookie), logout (revoke), and whoami."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import AcceptInviteIn, InvitePreviewOut, LoginIn, MeOut, SignupIn
from app.config import settings
from app.db.session import get_session
from app.modules.organizations import invites as invite_svc
from app.modules.organizations.auth import (
    EmailTakenError,
    authenticate,
    create_account,
    create_session,
    revoke_session,
)
from app.modules.organizations.models import Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    samesite = (settings.session_cookie_samesite or "lax").lower()
    # SameSite=None (needed when the frontend is on a different site than the API) is only
    # honored by browsers when the cookie is also Secure — force it so cross-site login works.
    secure = settings.session_cookie_secure or samesite == "none"
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )


def _me(user: User) -> MeOut:
    return MeOut(org_id=user.org_id, user_id=user.id, role=user.role, name=user.name, email=user.email)


@router.post("/signup", response_model=MeOut, status_code=201)
def signup(body: SignupIn, response: Response, session: Session = Depends(get_session)) -> MeOut:
    try:
        user = create_account(
            session, name=body.name, email=body.email, password=body.password, org_name=body.org_name
        )
    except EmailTakenError:
        raise DomainError("An account with this email already exists.", code="conflict", status_code=409)
    except ValueError as exc:
        raise DomainError(str(exc), code="validation_error", status_code=422)
    token = create_session(session, user=user, ttl=timedelta(hours=settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return _me(user)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)) -> MeOut:
    user = authenticate(session, email=body.email, password=body.password)
    if user is None:
        raise DomainError("Invalid email or password.", code="unauthorized", status_code=401)
    token = create_session(session, user=user, ttl=timedelta(hours=settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return _me(user)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Response:
    revoke_session(session, session_cookie)
    _samesite = (settings.session_cookie_samesite or "lax").lower()
    response.delete_cookie(
        key=settings.session_cookie_name, path="/",
        secure=settings.session_cookie_secure or _samesite == "none", samesite=_samesite,
    )
    response.status_code = 204
    return response


@router.get("/invite", response_model=InvitePreviewOut)
def preview_invite(token: str, session: Session = Depends(get_session)) -> InvitePreviewOut:
    """Preview a pending invite (public) so the accept screen can show org/email/role."""
    try:
        invite = invite_svc.peek_invite(session, token)
    except invite_svc.InviteError as exc:
        raise DomainError(str(exc), code="not_found", status_code=404)
    org = session.get(Organization, invite.org_id)
    return InvitePreviewOut(org_name=org.name if org else "", email=invite.email, role=invite.role)


@router.post("/accept-invite", response_model=MeOut, status_code=201)
def accept_invite(body: AcceptInviteIn, response: Response, session: Session = Depends(get_session)) -> MeOut:
    """Accept an invite by setting a password; creates the user and signs them in (public)."""
    try:
        accepted = invite_svc.accept_invite(session, token=body.token, password=body.password, name=body.name)
    except invite_svc.InviteError as exc:
        raise DomainError(str(exc), code="validation_error", status_code=422)
    token = create_session(session, user=accepted.user, ttl=timedelta(hours=settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return _me(accepted.user)


@router.get("/me", response_model=MeOut)
def me(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> MeOut:
    user = session.get(User, principal.user_id)
    if user is None:  # session valid but user gone
        raise DomainError("Not authenticated.", code="unauthorized", status_code=401)
    return _me(user)
