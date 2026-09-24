"""Turning the package's deliberate errors into HTTP responses - once, for every route.

Routes just let a WayfinderError propagate; the handler registered here decides the
status code and the body. Anything that is not a WayfinderError is a bug and becomes a
plain 500.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wayfinder.core.errors import (
    AmbiguousSymbol,
    BadRequest,
    WayfinderError,
    Forbidden,
    NotConfigured,
    NotFound,
    RateLimited,
    UpstreamError,
)

_STATUS = {
    BadRequest: 400,  # covers PromptTooLarge
    Forbidden: 403,  # a guardrail said no
    NotFound: 404,  # covers SymbolNotFound and NodeNotFound
    RateLimited: 429,
    AmbiguousSymbol: 409,
    UpstreamError: 502,  # the model provider failed, not this server (covers LLMError)
    NotConfigured: 503,  # e.g. no API key set up
}


def status_for(error: WayfinderError) -> int:
    """Status for the most specific class in the error's ancestry that has one."""
    for cls in type(error).__mro__:
        if cls in _STATUS:
            return _STATUS[cls]
    return 400


def register(app: FastAPI) -> None:
    @app.exception_handler(WayfinderError)
    async def handle(request: Request, error: WayfinderError) -> JSONResponse:
        detail: object = str(error)
        if isinstance(error, AmbiguousSymbol):  # the candidates let a client retry
            detail = {"message": str(error), "matches": [asdict(m) for m in error.matches]}
        headers = {"Retry-After": str(int(error.retry_after) + 1)} if isinstance(error, RateLimited) else None
        return JSONResponse(status_code=status_for(error), content={"detail": detail}, headers=headers)
