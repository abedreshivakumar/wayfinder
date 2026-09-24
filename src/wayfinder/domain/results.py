"""What the services hand back to the API and MCP layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMatch:
    """One function, method or class found by name in a file."""

    qualified_name: str  # "UserService.fetch_user"
    kind: int
    line: int  # 1-indexed, position of the symbol's name
    col: int


@dataclass(frozen=True)
class PathExplanation:
    node_ids: list[str]  # the chain, in call order: each function calls the next
    names: list[str]  # the same functions by name, for reading
    text: str
    cached: bool  # True when an earlier explanation of the identical chain was reused


@dataclass(frozen=True)
class DriftFinding:
    """One place where a function's documentation disagrees with its code."""

    kind: str  # e.g. "param-not-in-signature"
    severity: str  # "high" | "medium" | "low"
    message: str
    source: str  # "static" (found by reading the code) | "model" (a model's judgment)
    line: int | None = None  # 1-indexed line in the file, when known


@dataclass(frozen=True)
class DriftReport:
    node_id: str
    name: str
    findings: list[DriftFinding]
    # What happened to the optional model review: "done", "cached", or "skipped: <why>" /
    # "failed: <why>". The static findings are always present either way.
    model_review: str


@dataclass(frozen=True)
class Narration:
    node_id: str
    text: str
    cached: bool  # True when an earlier explanation of identical code was reused
