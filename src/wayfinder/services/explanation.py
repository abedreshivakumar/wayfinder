"""Explain analyzed code in plain language, using the agents."""

from __future__ import annotations

import hashlib

from wayfinder.agents.narrator import Narrator
from wayfinder.agents.path_explainer import PathExplainer
from wayfinder.analysis.source import extract_source
from wayfinder.core.errors import BadRequest, NodeNotFound, NoPath
from wayfinder.domain.graph import Node
from wayfinder.domain.results import Narration, PathExplanation
from wayfinder.guardrails import inputs
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext
from wayfinder.services.model_access import ModelAccess


class ExplanationService:
    def __init__(self, ctx: ServiceContext, analysis: AnalysisService, access: ModelAccess) -> None:
        self._ctx = ctx
        self._analysis = analysis
        self._access = access

    # --- one function ---

    def narrate(self, node_id: str) -> Narration:
        """Plain-language explanation of an already-analyzed function."""
        ctx = self._ctx
        llm = self._access.get()
        narrator = Narrator(self._access.guarded(llm))

        with ctx.lock:
            node = ctx.store.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"no analyzed function with id {node_id}; analyze it first")
            source = self._source_of(node, ctx.settings.limits.max_source_chars)
            if source is None:
                raise BadRequest(
                    f"can't find the source of '{node.name}' at {node.path.name}:{node.start_line}; "
                    "the file may have changed since it was analyzed"
                )
            prompt = narrator.build_prompt(node, source, ctx.store.get_dataflow_graph(node_id, hops=1))
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            cached = ctx.store.get_narration(node_id, digest)

        if cached is not None:
            return Narration(node_id, cached, cached=True)  # nothing is sent anywhere

        if llm.external:
            self._access.egress.check(node.path)  # only about to send code off the machine
        # The model call takes seconds. The lock is deliberately NOT held for it, or
        # every other request would freeze while we wait on the network.
        text = narrator.explain(prompt)

        with ctx.lock:
            ctx.store.set_narration(node_id, digest, text, narrator.model)
        return Narration(node_id, text, cached=False)

    def explain_symbol(
        self,
        repo: str,
        file: str,
        *,
        symbol: str | None = None,
        line: int | None = None,
        col: int | None = None,
    ) -> Narration:
        """Analyze a function, then explain it - the one-call form for callers that
        don't already hold a node id (the MCP tool)."""
        dfg = self._analysis.analyze(repo, file, symbol=symbol, line=line, col=col, hops=1)
        assert dfg.graph.root_id is not None
        return self.narrate(dfg.graph.root_id)

    # --- a chain of calls ---

    def explain_path(self, from_id: str, to_id: str, max_hops: int = 5) -> PathExplanation:
        """Explain how one analyzed function reaches another through the calls between
        them. The two may be given in either order; the chain comes back in call order."""
        ctx = self._ctx
        inputs.check_hops(max_hops, ctx.settings.limits)
        if from_id == to_id:
            raise BadRequest("give two different functions")
        llm = self._access.get()
        explainer = PathExplainer(self._access.guarded(llm))

        with ctx.lock:
            for node_id in (from_id, to_id):
                if ctx.store.get_node(node_id) is None:
                    raise NodeNotFound(f"no analyzed function with id {node_id}; analyze it first")
            chain = ctx.store.find_path(from_id, to_id, max_hops) or ctx.store.find_path(to_id, from_id, max_hops)
            if not chain:
                raise NoPath(
                    f"no chain of calls of up to {max_hops} between these functions in what has been "
                    "analyzed. Analyze the first with more hops, or check that one really leads to the other."
                )
            node_ids = [chain[0].from_id] + [e.to_id for e in chain]
            nodes = [n for i in node_ids if (n := ctx.store.get_node(i)) is not None]

            # A chain can run through code outside the allowed repos (a library, another
            # project). For a hosted model that code is withheld rather than sent; only
            # the two functions actually asked about must be allowed (checked below).
            limit = ctx.settings.limits.max_path_source_chars
            sources = [
                self._source_of(n, limit) if (not llm.external or self._access.egress.allows(n.path)) else None
                for n in nodes
            ]
            hop_labels = [ctx.store.get_call_labels(e.from_id, e.to_id) for e in chain]
            prompt = explainer.build_prompt(nodes, sources, hop_labels)
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            cached = ctx.store.get_path_explanation(digest)

        names = [n.name for n in nodes]
        if cached is not None:
            return PathExplanation(node_ids, names, cached, cached=True)

        if llm.external:
            for endpoint in (nodes[0], nodes[-1]):
                self._access.egress.check(endpoint.path)
        text = explainer.explain(prompt)  # lock not held: this takes seconds

        with ctx.lock:
            ctx.store.set_path_explanation(digest, text, explainer.model)
        return PathExplanation(node_ids, names, text, cached=False)

    def explain_path_between(
        self,
        repo: str,
        from_file: str,
        from_symbol: str,
        to_file: str,
        to_symbol: str,
        hops: int = 3,
    ) -> PathExplanation:
        """Analyze two functions by name, then explain how one reaches the other - the
        one-call form for callers that don't hold node ids (the MCP tool)."""
        first = self._analysis.analyze(repo, from_file, symbol=from_symbol, hops=hops)
        second = self._analysis.analyze(repo, to_file, symbol=to_symbol, hops=1)
        assert first.graph.root_id is not None and second.graph.root_id is not None
        return self.explain_path(first.graph.root_id, second.graph.root_id, hops)

    # --- helpers ---

    def _source_of(self, node: Node, max_chars: int) -> str | None:
        try:
            return extract_source(node.path, node.name, node.start_line, max_chars)
        except (OSError, SyntaxError):  # file deleted, or edited into invalid Python
            return None
