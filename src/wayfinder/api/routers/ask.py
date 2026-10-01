"""Plain-English questions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from wayfinder.api.dependencies import ServicesDep
from wayfinder.api.schemas import AskRequest

router = APIRouter(tags=["ask"])


@router.post("/ask")
def ask(services: ServicesDep, body: AskRequest) -> dict[str, Any]:
    """Answer a plain-English question about a repository, for example "who calls
    `fetch_user` and what do they pass it?". Claude chooses which analysis tools to call
    and answers from what they return.

    Everything the model sees is sent to a hosted service, so this is refused in offline
    mode and unless `repo` is on the allowlist. `tools_used` says which tools it chose."""
    return asdict(services.orchestration.ask(body.repo, body.question))
