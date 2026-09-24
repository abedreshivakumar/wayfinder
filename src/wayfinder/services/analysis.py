"""Analyze a function: find it, walk its calls, label the data flow, save the result."""

from __future__ import annotations

from wayfinder.analysis.call_graph import build_call_graph
from wayfinder.analysis.dataflow.annotate import annotate_graph
from wayfinder.core.errors import AmbiguousSymbol, BadRequest, SymbolNotFound
from wayfinder.domain.graph import Direction
from wayfinder.domain.labels import DataFlowGraph
from wayfinder.guardrails import inputs
from wayfinder.lsp.symbols import find_symbols
from wayfinder.services.context import ServiceContext


class AnalysisService:
    def __init__(self, ctx: ServiceContext) -> None:
        self._ctx = ctx

    def analyze(
        self,
        repo: str,
        file: str,
        *,
        symbol: str | None = None,
        line: int | None = None,
        col: int | None = None,
        hops: int = 1,
        direction: Direction | None = None,
    ) -> DataFlowGraph:
        """Analyze a function with pyright, save the result, and return the graph around
        it. Name the function with `symbol`, or with `line` + `col`.

        direction=None returns callers and callees; "incoming" only callers; "outgoing"
        only callees."""
        ctx = self._ctx
        inputs.check_target(symbol, line, col)
        inputs.check_hops(hops, ctx.settings.limits)
        repo_root, file_path = inputs.resolve_file(repo, file)

        with ctx.lock:
            driver = ctx.pool.get(repo_root)
            if symbol is not None:
                matches = find_symbols(driver, file_path, symbol)
                if not matches:
                    raise SymbolNotFound(f"no function, method or class named '{symbol}' in {file}")
                if len(matches) > 1:
                    raise AmbiguousSymbol(symbol, matches)
                line, col = matches[0].line, matches[0].col
            assert line is not None and col is not None

            try:
                graph = build_call_graph(driver, file_path, line, col, hops)
            except ValueError as e:  # no callable symbol at that position
                raise BadRequest(str(e)) from e
            assert graph.root_id is not None

            ctx.store.save(annotate_graph(graph, driver))
            return ctx.store.get_dataflow_graph(graph.root_id, hops, direction)
