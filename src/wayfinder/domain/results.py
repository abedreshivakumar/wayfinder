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
class Answer:
    text: str
    tools_used: list[str]  # which tools the model chose, in order, without repeats
    turns: int | None  # how many rounds it took, when the runner reports it


@dataclass(frozen=True)
class Narration:
    node_id: str
    text: str
    cached: bool  # True when an earlier explanation of identical code was reused


@dataclass(frozen=True)
class TraceNode:
    id: str  # "file:qualified.name:line", unique within one trace
    name: str  # "fetch_user" or "User.__init__"
    file: str  # relative to the repo; for code outside the repo, the file name only
    line: int  # where the function is defined, 1-indexed (0 for a program's top level)
    in_repo: bool


@dataclass(frozen=True)
class TraceEdge:
    from_id: str
    to_id: str
    count: int  # how many times the call happened (0 for "not_exercised")
    # confirmed: the static graph has this call too.
    # runtime_only: it happened, but static analysis did not find it (dynamic dispatch,
    #   callbacks, monkey-patching) - the calls only a real run can show.
    # not_exercised: the static graph has it, but this run never made it.
    # module_level: made by the top level of a file, which static analysis is not asked about.
    # unchecked: the caller could not be checked against the static graph.
    status: str


@dataclass(frozen=True)
class TraceReport:
    entry: str  # what was run: a file, or "file:function"
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    error: str | None  # the program raised, exited non-zero or hit the time limit
    returned: str | None  # what the function returned, shortened
    output: str  # what the program printed, shortened
    truncated: bool  # the run made more distinct calls than were recorded
    checked_functions: int  # callers compared against the static graph
    unchecked_functions: int  # callers left out of that comparison, to stay under the limit


@dataclass(frozen=True)
class FileExplanation:
    file: str  # relative to the repo
    text: str
    cached: bool  # True when an earlier explanation of identical code and structure was reused
