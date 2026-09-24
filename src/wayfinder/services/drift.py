"""Check whether a function's documentation still matches its code.

Two layers, so the answer is useful even with no model: static findings (a docstring that
names a parameter the function doesn't have, and the like) come from reading the code and
are always returned; a model then reviews the fuzzier claims. If the model can't be used -
no key, offline mode, the repo isn't allowed, the provider is down - the report still comes
back with the static findings and says why the model part didn't run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from wayfinder.agents.drift_checker import DriftChecker
from wayfinder.analysis.docstrings import check_docstring, has_documentation
from wayfinder.analysis.source import extract_source
from wayfinder.core.errors import BadRequest, WayfinderError, NodeNotFound, UpstreamError
from wayfinder.domain.results import DriftFinding, DriftReport
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext
from wayfinder.services.model_access import ModelAccess

_FUNCTION_KINDS = {6, 9, 12}  # method, constructor, function (LSP SymbolKind)
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class DriftService:
    def __init__(self, ctx: ServiceContext, analysis: AnalysisService, access: ModelAccess) -> None:
        self._ctx = ctx
        self._analysis = analysis
        self._access = access

    def check(self, node_id: str) -> DriftReport:
        """Documentation-versus-code report for an already-analyzed function."""
        ctx = self._ctx
        with ctx.lock:
            node = ctx.store.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"no analyzed function with id {node_id}; analyze it first")
            if node.kind not in _FUNCTION_KINDS:
                raise BadRequest("drift checks work on functions and methods, not classes")
            try:
                source = extract_source(node.path, node.name, node.start_line, ctx.settings.limits.max_source_chars)
            except (OSError, SyntaxError):
                source = None
            if source is None:
                raise BadRequest(
                    f"can't find the source of '{node.name}' at {node.path.name}:{node.start_line}; "
                    "the file may have changed since it was analyzed"
                )
            static = check_docstring(source, node.start_line)
            has_docs = has_documentation(source)
            prompt = DriftChecker.build_prompt(node, source, ctx.store.get_dataflow_graph(node_id, hops=1))
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            cached = ctx.store.get_drift_review(digest) if has_docs else None

        def report(model_findings: list[DriftFinding], model_review: str) -> DriftReport:
            ordered = sorted(
                static + model_findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.line or 0, f.message)
            )
            return DriftReport(node_id=node_id, name=node.name, findings=ordered, model_review=model_review)

        if not has_docs:
            return report([], "skipped: the function has no docstring or comments to review")
        if cached is not None:
            return report([DriftFinding(**f) for f in json.loads(cached)], "cached")

        try:
            llm = self._access.get()
            if llm.external:
                self._access.egress.check(node.path)  # about to send code off the machine
            checker = DriftChecker(self._access.guarded(llm))
            model_findings = checker.review(prompt)  # lock not held: this takes seconds
        except WayfinderError as e:
            # A provider failure is "failed"; everything else (no key, offline, not allowed,
            # rate limit, too large) is a deliberate "skipped". The static findings stand.
            return report([], f"{'failed' if isinstance(e, UpstreamError) else 'skipped'}: {e}")

        with ctx.lock:
            ctx.store.set_drift_review(digest, json.dumps([asdict(f) for f in model_findings]), checker.model)
        return report(model_findings, "done")

    def check_symbol(
        self,
        repo: str,
        file: str,
        *,
        symbol: str | None = None,
        line: int | None = None,
        col: int | None = None,
    ) -> DriftReport:
        """Analyze a function, then check it - the one-call form for callers without a node id."""
        dfg = self._analysis.analyze(repo, file, symbol=symbol, line=line, col=col, hops=1)
        assert dfg.graph.root_id is not None
        return self.check(dfg.graph.root_id)
