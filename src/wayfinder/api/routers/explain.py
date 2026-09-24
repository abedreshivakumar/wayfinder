"""Plain-language explanations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from wayfinder.api.dependencies import ServicesDep
from wayfinder.api.schemas import CheckDriftRequest, ExplainPathRequest, NarrateRequest

router = APIRouter(tags=["explain"])


@router.post("/narrate")
def narrate(services: ServicesDep, body: NarrateRequest) -> dict[str, Any]:
    """Plain-language explanation of a function that GET /graph has already analyzed.
    `node_id` is a node's `id` from that response. Repeat calls for unchanged code are
    served from the cache (`cached: true`) without calling the model."""
    return asdict(services.explanation.narrate(body.node_id))


@router.post("/explain-path")
def explain_path(services: ServicesDep, body: ExplainPathRequest) -> dict[str, Any]:
    """Plain-language walk through the chain of calls between two analyzed functions.
    `from_id` and `to_id` are node ids from GET /graph, in either order; the chain comes
    back in call order (`node_ids`, `names`). Both functions must already be analyzed
    deeply enough that the graph connects them."""
    return asdict(services.explanation.explain_path(body.from_id, body.to_id, body.max_hops))


@router.post("/check-drift")
def check_drift(services: ServicesDep, body: CheckDriftRequest) -> dict[str, Any]:
    """Does this function's documentation still match its code? Static findings (a
    docstring naming a parameter the function doesn't have, and the like) always come
    back; a model review of the fuzzier claims is added when a model can be used, and
    `model_review` says what happened to it (done, cached, or skipped/failed with why).
    `node_id` is a node's `id` from GET /graph."""
    return asdict(services.drift.check(body.node_id))
