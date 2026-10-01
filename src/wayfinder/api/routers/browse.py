"""What the UI needs to show a repository and let someone move around in it."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from wayfinder.api.dependencies import ServicesDep
from wayfinder.api.schemas import ExplainFileRequest

router = APIRouter(tags=["browse"])


@router.get("/files")
def list_files(services: ServicesDep, repo: str) -> dict[str, Any]:
    """The Python files in a repo, relative to its root."""
    return {"files": services.analysis.list_files(repo)}


@router.get("/symbols")
def list_symbols(services: ServicesDep, repo: str, file: str) -> dict[str, Any]:
    """The functions, methods and classes in one file, with the position of each name."""
    return {"symbols": [asdict(s) for s in services.analysis.list_symbols(repo, file)]}


@router.get("/repo-map")
def repo_map(services: ServicesDep, repo: str) -> dict[str, Any]:
    """Every file with its size, and which files import which: the whole-repo picture.
    Built by reading import lines only, so it is fast and needs no pyright."""
    return services.overview.repo_map(repo)


@router.get("/file-graph")
def file_graph(services: ServicesDep, repo: str, file: str) -> dict[str, Any]:
    """One file from the inside: its functions, the calls between them and out to other
    files, the data passed along those calls, and a plain-language `summary` built from
    those facts (no model involved). Analyzes every function, so it takes a few seconds."""
    return services.overview.file_graph(repo, file)


@router.post("/explain-file")
def explain_file(services: ServicesDep, body: ExplainFileRequest) -> dict[str, Any]:
    """A model-written walkthrough of one file. Needs a model (403 offline)."""
    return asdict(services.explanation.explain_file(body.repo, body.file))
