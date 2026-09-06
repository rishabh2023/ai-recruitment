"""Error-response conventions (docs/interfaces.md).

All errors return `{ "error": { code, message, request_id } }`. A `request_id` is attached to
every request for correlation with logs/traces.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Base for expected domain failures mapped to a 4xx code."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


def _payload(code: str, message: str, request_id: str, details=None) -> dict:
    err = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        err["details"] = details
    return {"error": err}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, _rid(request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload("http_error", str(exc.detail), _rid(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_payload("validation_error", "Request validation failed", _rid(request), exc.errors()),
        )
