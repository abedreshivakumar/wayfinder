"""Call graphs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from wayfinder.api.dependencies import ServicesDep
from wayfinder.domain.graph import Direction

router = APIRouter(tags=["graph"])


# Plain `def`, not `async def`: analysis blocks on pyright, and FastAPI runs plain
# functions in a thread pool so one slow request doesn't freeze the whole server.
@router.get("/graph")
def get_graph(
    services: ServicesDep,
    repo: str,
    file: str,
    symbol: str | None = None,
    line: int | None = None,
    col: int | None = None,
    hops: int = 1,
    direction: Direction | None = None,
) -> dict[str, Any]:
    """Call graph around one function, with argument/return types and data-flow links.

    `repo` is the repo root path; `file` is relative to it. Name the function with
    `symbol` ("fetch_user" or "UserService.fetch_user") or with
    `line` + `col` (both 1-indexed, pointing at the function's name)."""
    return services.analysis.analyze(
        repo, file, symbol=symbol, line=line, col=col, hops=hops, direction=direction
    ).to_dict()
