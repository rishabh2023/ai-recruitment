"""Celery app + durable background tasks.

Celery owns durable async execution (architecture). In dev, `celery_task_always_eager` runs
tasks inline in-process (no broker/worker needed); in production set it false and run
`celery -A app.tasks worker` against `redis_url`.

The dispatch task always persists the call's outcome (success or FAILED) and never propagates
an exception back to the web request — the launch endpoint must not 500 because the vendor is
down; the call state carries the failure instead (never lose state silently).
"""

from __future__ import annotations

import logging
from uuid import UUID

from celery import Celery

from app.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

celery_app = Celery("recruitment", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.task_eager_propagates = False


@celery_app.task(name="dispatch_hunar_call")
def dispatch_hunar_call(call_id: str) -> None:
    """Place the outbound Hunar call for an already-persisted (QUEUED) Call."""
    from app.modules.interviews.dispatch import HunarDispatchService

    session = SessionLocal()
    try:
        HunarDispatchService(session).dispatch(UUID(call_id))
        session.commit()  # persist success (or the FAILED state set on a handled error)
    except Exception as exc:  # noqa: BLE001 - task must not crash the caller in eager mode
        # dispatch() already persisted a FAILED state via its own flush; commit that, then log.
        try:
            session.commit()
        except Exception:  # pragma: no cover - defensive
            session.rollback()
        logger.warning("dispatch_hunar_call(%s) failed: %s", call_id, exc)
    finally:
        session.close()
