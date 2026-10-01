"""Flow-Tracer: what a real run calls."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from wayfinder.api.dependencies import ServicesDep
from wayfinder.api.schemas import TraceRequest

router = APIRouter(tags=["trace"])


@router.post("/trace")
def trace(services: ServicesDep, body: TraceRequest) -> dict[str, Any]:
    """RUNS the repository's code (a file as a script, or one function with the given
    arguments) and reports which functions really called which, compared with the static
    graph. Refused with 403 unless the server was started with WAYFINDER_ALLOW_TRACE=1."""
    return asdict(services.tracing.trace(body.repo, body.file, body.function, body.args, body.kwargs))
