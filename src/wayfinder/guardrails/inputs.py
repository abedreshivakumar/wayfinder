"""Checks on what a caller sends us, before any work is done.

These run before pyright is started or a model is called, so a bad request is cheap to
refuse - and the same rules apply whether it arrived over HTTP or MCP.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.core.config import Limits
from wayfinder.core.errors import BadRequest


def check_target(symbol: str | None, line: int | None, col: int | None) -> None:
    """A function is named either by `symbol`, or by an exact `line` + `col`; never both."""
    if symbol is None and (line is None or col is None):
        raise BadRequest("give either `symbol`, or both `line` and `col`")
    if symbol is not None and (line is not None or col is not None):
        raise BadRequest("give either `symbol` or `line`/`col`, not both")


def check_hops(hops: int, limits: Limits) -> None:
    if not 1 <= hops <= limits.max_hops:
        raise BadRequest(f"hops must be between 1 and {limits.max_hops}")


def resolve_file(repo: str, file: str) -> tuple[Path, Path]:
    """(repo root, file) as real paths, refusing anything that isn't a Python file inside
    the repo. This is the sandbox: `../../etc/passwd` or an absolute path elsewhere
    never reaches pyright."""
    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.is_dir():
        raise BadRequest(f"repo is not a directory: {repo}")
    file_path = (repo_root / file).resolve()
    if not file_path.is_relative_to(repo_root):
        raise BadRequest("file must be inside the repo")
    if file_path.suffix != ".py" or not file_path.is_file():
        raise BadRequest(f"not a Python file inside the repo: {file}")
    return repo_root, file_path
