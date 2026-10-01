"""Compare what a run actually called with what static analysis said could be called.

The run is the ground truth for what happened; static analysis is the ground truth for
what the code says. Where they agree the call is "confirmed"; where the run made a call
static analysis missed, that is exactly the dynamic behaviour (callbacks, dispatch tables,
monkey-patching) that the static graph cannot see.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from wayfinder.analysis.tracing.collect import RawTrace
from wayfinder.domain.results import TraceEdge, TraceNode

# A function's identity in a trace: (absolute file, name, qualified name, first line).
FuncKey = tuple[str, str, str, int]
# What the static graph says a function calls: (absolute file, name) pairs, or None when
# the function could not be looked up.
StaticCallees = Callable[[FuncKey], set[tuple[str, str]] | None]

_MODULE = "<module>"
_LOOKAHEAD = 30  # lines below a decorator to find the `def`


def name_position(lines: list[str], name: str, first_line: int) -> tuple[int, int] | None:
    """1-indexed (line, column) of `name` in its `def`/`class` line, starting from the
    line Python reports (which is the first decorator, if there are any)."""
    pattern = re.compile(rf"\b(?:def|class)\s+({re.escape(name)})\b")
    for i in range(first_line - 1, min(first_line - 1 + _LOOKAHEAD, len(lines))):
        m = pattern.search(lines[i])
        if m:
            return i + 1, m.start(1) + 1
    return None


def _key(raw: list) -> FuncKey:
    return (raw[0], raw[1], raw[2], raw[3])


def _static_targets(callee: FuncKey) -> set[tuple[str, str]]:
    """Names static analysis could know a runtime callee by. Instantiating a class shows
    up statically as a call to the class, but at runtime as a call to its __init__."""
    file, name, qualname, _ = callee
    targets = {(file, name)}
    parts = qualname.split(".")
    if name == "__init__" and len(parts) >= 2:
        targets.add((file, parts[-2]))
    return targets


def reconcile(
    raw: RawTrace, repo_root: Path, static_callees: StaticCallees, max_checked: int
) -> tuple[list[TraceNode], list[TraceEdge], int, int]:
    """(nodes, edges, checked callers, callers skipped for the limit)."""

    def node_id(k: FuncKey) -> str:
        return f"{_relative(k[0], repo_root)}:{k[2]}:{k[3]}"

    nodes: dict[str, TraceNode] = {}
    by_name: dict[tuple[str, str], str] = {}  # (file, name) -> node id, for nodes seen at runtime

    def add(k: FuncKey, in_repo: bool) -> str:
        nid = node_id(k)
        by_name.setdefault((k[0], k[1]), nid)
        if nid not in nodes:
            top_level = k[1] == _MODULE
            nodes[nid] = TraceNode(
                id=nid,
                name=(f"{Path(k[0]).name} (top level)" if top_level else k[2]),
                file=_relative(k[0], repo_root) if in_repo else Path(k[0]).name,
                line=0 if top_level else k[3],
                in_repo=in_repo,
            )
        return nid

    observed = [(_key(e["caller"]), _key(e["callee"]), e["caller_in_repo"], e["count"]) for e in raw.edges]

    calls_by_caller: dict[FuncKey, int] = {}
    for caller, _, inside, count in observed:
        if inside and caller[1] != _MODULE:
            calls_by_caller[caller] = calls_by_caller.get(caller, 0) + count
    ranked = sorted(calls_by_caller, key=lambda k: -calls_by_caller[k])
    to_check = ranked[:max_checked]
    static = {k: static_callees(k) for k in to_check}

    edges: list[TraceEdge] = []
    seen_pairs: dict[FuncKey, set[tuple[str, str]]] = {}
    for caller, callee, inside, count in observed:
        from_id, to_id = add(caller, inside), add(callee, True)
        if not inside:
            status = "runtime_only"  # called from outside the repo, e.g. a framework's callback
        elif caller[1] == _MODULE:
            status = "module_level"
        elif (caller_static := static.get(caller)) is None:
            status = "unchecked"
        else:
            targets = _static_targets(callee)
            seen_pairs.setdefault(caller, set()).update(targets)
            status = "confirmed" if targets & caller_static else "runtime_only"
        edges.append(TraceEdge(from_id, to_id, count, status))

    # Calls the code makes that this run never reached.
    for caller in to_check:
        callees = static.get(caller)
        if not callees:
            continue
        for file, name in sorted(callees - seen_pairs.get(caller, set())):
            if not _under(file, repo_root):
                continue  # library calls: the run does not record those, so absence means nothing
            nid = by_name.get((file, name)) or f"{_relative(file, repo_root)}:{name}:static"
            if nid not in nodes:
                nodes[nid] = TraceNode(nid, name, _relative(file, repo_root), 0, True)
            edges.append(TraceEdge(node_id(caller), nid, 0, "not_exercised"))

    checked = sum(1 for k in to_check if static.get(k) is not None)
    return list(nodes.values()), edges, checked, len(ranked) - len(to_check)


def _relative(file: str, repo_root: Path) -> str:
    try:
        return str(Path(file).relative_to(repo_root))
    except ValueError:
        return Path(file).name


def _under(file: str, repo_root: Path) -> bool:
    try:
        Path(file).relative_to(repo_root)
        return True
    except ValueError:
        return False
