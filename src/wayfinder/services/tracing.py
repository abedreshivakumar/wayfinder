"""Flow-Tracer: run a piece of the repository, watch which functions call which, and
compare that with what static analysis found.

This is the only place Wayfinder executes the code it is analyzing, so the rules here are
the strictest: nothing runs unless the owner turned tracing on, the entry point must be a
Python file inside the repo, and the run is time- and size-limited (see collect.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from wayfinder.analysis.tracing.collect import run_trace
from wayfinder.analysis.tracing.reconcile import FuncKey, name_position, reconcile
from wayfinder.core.errors import BadRequest, Forbidden, WayfinderError
from wayfinder.domain.results import TraceReport
from wayfinder.guardrails import inputs
from wayfinder.guardrails.secrets import redact_secrets
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TraceService:
    def __init__(self, ctx: ServiceContext, analysis: AnalysisService) -> None:
        self._ctx = ctx
        self._analysis = analysis

    def trace(
        self,
        repo: str,
        file: str,
        function: str | None = None,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> TraceReport:
        """Run `file` as a script, or - when `function` is given - import it and call that
        top-level function with `args`/`kwargs`."""
        settings = self._ctx.settings
        if not settings.allow_trace:
            raise Forbidden(
                "tracing runs the repository's own code, so it is turned off. Set "
                "WAYFINDER_ALLOW_TRACE=1 (only for code you trust) and restart to enable it."
            )
        repo_root, file_path = inputs.resolve_file(repo, file)
        args, kwargs = args or [], kwargs or {}
        if function is not None and not _IDENTIFIER.match(function):
            raise BadRequest("function must be the name of a top-level function")
        if function is None and (args or kwargs):
            raise BadRequest("arguments only make sense together with a function to call")
        try:
            size = len(json.dumps([args, kwargs]))
        except (TypeError, ValueError) as e:
            raise BadRequest("args and kwargs must be plain JSON values") from e
        if size > settings.limits.max_trace_input_chars:
            raise BadRequest(f"the arguments are {size:,} characters; the limit is {settings.limits.max_trace_input_chars:,}")

        limits = settings.limits
        raw = run_trace(
            repo_root,
            file_path,
            function,
            args,
            kwargs,
            timeout=limits.trace_timeout_seconds,
            max_edges=limits.max_trace_edges,
        )
        nodes, edges, checked, skipped = reconcile(
            raw, repo_root, lambda key: self._static_callees(repo_root, key), limits.max_traced_functions
        )
        returned = redact_secrets(raw.returned)[0] if raw.returned else None
        return TraceReport(
            entry=f"{file}:{function}" if function else file,
            nodes=nodes,
            edges=edges,
            error=redact_secrets(raw.error)[0] if raw.error else None,
            returned=returned,
            output=redact_secrets(raw.output)[0],
            truncated=raw.truncated,
            checked_functions=checked,
            unchecked_functions=skipped,
        )

    def _static_callees(self, repo_root: Path, key: FuncKey) -> set[tuple[str, str]] | None:
        """What static analysis says this function calls, or None if it can't be looked up."""
        file, name, _, first_line = key
        path = Path(file)
        try:
            lines = path.read_text().splitlines()
            where = name_position(lines, name, first_line)
            if where is None:
                return None
            dfg = self._analysis.analyze(
                str(repo_root), str(path.relative_to(repo_root)), line=where[0], col=where[1], hops=1, direction="outgoing"
            )
        except (OSError, ValueError, WayfinderError):
            return None
        graph = dfg.graph
        return {(str(graph.nodes[e.to_id].path.resolve()), graph.nodes[e.to_id].name) for e in graph.edges if e.from_id == graph.root_id}
