"""Hunar webhook endpoint (Phase 3).

Lightweight handler: verify signature (when a signing key is configured), then process the
event idempotently via WebhookService. In production the processing would be enqueued to
Celery; here it runs inline for the assignment.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.schemas import WebhookAck
from app.config import settings
from app.db.session import get_session
from app.integrations.hunar import verify_webhook_signature
from app.modules.webhooks.service import WebhookService

logger = logging.getLogger("hunar.webhook")
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/hunar", response_model=WebhookAck)
async def hunar_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_hunar_signature: str | None = Header(default=None),
    x_hunar_timestamp: str | None = Header(default=None),
):
    raw = await request.body()
    signature_valid = True
    if settings.hunar_webhook_signing_key:
        signature_valid = verify_webhook_signature(
            signing_key=settings.hunar_webhook_signing_key,
            timestamp=x_hunar_timestamp or "",
            raw_body=raw,
            signature_header=x_hunar_signature or "",
        )
    payload = json.loads(raw or b"{}")
    logger.info(
        "hunar webhook event=%s id=%s request_id=%s status=%s keys=%s sig_valid=%s",
        payload.get("event"), payload.get("id"), payload.get("request_id"),
        payload.get("status"), list(payload.keys()), signature_valid,
    )
    svc = WebhookService(session, None)
    duplicate = svc.find_existing(payload) is not None
    svc.handle_hunar_event(payload, signature_valid=signature_valid)
    return WebhookAck(status="received", duplicate=duplicate)
