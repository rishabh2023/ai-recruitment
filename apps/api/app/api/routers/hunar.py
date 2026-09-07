"""Hunar voice-AI health + key management.

- GET /hunar/health  → current health (cached ~60s; ?refresh=1 forces a live probe). Any
  authenticated user may read. Never returns the key.
- PUT /hunar/key     → admin-only; validates the key against Hunar before saving it durably.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import HunarHealthOut, HunarKeyUpdateIn
from app.db.session import get_session
from app.integrations.hunar import keystore
from app.integrations.hunar.client import HunarError
from app.modules.audit.log import write_audit

router = APIRouter(prefix="/hunar", tags=["hunar"])


@router.get("/health", response_model=HunarHealthOut)
def get_health(
    refresh: bool = False,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    return keystore.check_health(session, refresh=refresh)
