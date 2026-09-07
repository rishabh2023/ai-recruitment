"""FastAPI application entrypoint (modular monolith).

Wires the Phase 2–3 service layer to HTTP. Run: `uvicorn app.main:app --reload`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routers import assistant, auth, candidates, dashboard, funnels, hunar, interviews, jobs, settings as settings_router, sourcing, system, webhooks
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="AI Recruitment Workflow API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # required for the browser to send the session cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(assistant.router)
    app.include_router(jobs.router)
    app.include_router(funnels.router)
    app.include_router(candidates.router)
    app.include_router(sourcing.router)
    app.include_router(settings_router.router)
    app.include_router(interviews.router)
    app.include_router(webhooks.router)
    app.include_router(hunar.router)
    return app


app = create_app()
