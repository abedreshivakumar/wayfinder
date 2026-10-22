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
    """Every file in a repo whose extension a supported language claims, relative to its root."""
    return {"files": services.analysis.list_files(repo)}


@router.get("/symbols")
def list_symbols(services: ServicesDep, repo: str, file: str) -> dict[str, Any]:
    """The functions, methods and classes in one file, with the position of each name."""
    return {"symbols": [asdict(s) for s in services.analysis.list_symbols(repo, file)]}


@router.get("/overview")
def overview(services: ServicesDep, repo: str) -> dict[str, Any]:
    """The repo as a newcomer needs it: modules with their layer (entry / core / data),
    links between modules, every file with its functions, classes and schemas, a reading
    order, and how many test or boilerplate files are hidden. No pyright, no model: fast."""
    return services.overview.structure(repo)


@router.get("/purposes")
def purposes(services: ServicesDep, repo: str) -> dict[str, Any]:
    """A one-line purpose for every module and file. Written by the model when the repo may be
    sent to one (cached after the first time), otherwise taken from docstrings; `source` and
    `note` say which and why."""
    return services.purposes.purposes(repo)


@router.get("/repo-summary")
def repo_summary(services: ServicesDep, repo: str) -> dict[str, Any]:
    """2-3 plain-English sentences on what this repo is and what problem it solves - a
    newcomer's first orientation, shown above the modules. Written by the model when the
    repo may be sent to one (cached after the first time); `source`/`note` say which and why."""
    return services.purposes.repo_summary(repo)


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
    """A model-written walkthrough of one file: `summary`, ordered `steps`, and a one-line
    purpose per function in `functions`. Needs a model (403 offline)."""
    return asdict(services.explanation.explain_file(body.repo, body.file))
