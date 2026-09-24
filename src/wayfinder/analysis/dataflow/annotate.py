"""Join the call graph with the AST pass and pyright's types.

The call graph knows *that* handle_login calls fetch_user. The AST pass (ast_pass.py)
knows *what was passed and where the result went*. pyright's hover knows *the types*.
This file is the only place the three meet.

It returns a DataFlowGraph (domain/labels.py): the original Graph untouched, plus
  - call_labels: per call, the arguments (with types) and what it returns
  - flow_links:  per stored-then-reused value, which call produced it and which
                 call consumed it (e.g. fetch_user --[user: User]--> process)
"""

from __future__ import annotations

import re
from pathlib import Path

from wayfinder.analysis.dataflow.ast_pass import CallSite, Pos, find_call_sites
from wayfinder.analysis.dataflow.thread import thread_variables
from wayfinder.analysis.dataflow.types import HoverInfo, resolve_type
from wayfinder.domain.graph import Graph
from wayfinder.domain.labels import ArgLabel, CallLabel, DataFlowGraph, FlowLink
from wayfinder.lsp.pyright_driver import PyrightDriver

_COROUTINE = re.compile(r"^Coroutine(?:Type)?\[.+?,\s*.+?,\s*(.+)\]$")


def _unwrap_coroutine(type_: str) -> str:
    """An `async def` is declared as returning CoroutineType[Any, Any, X], but once
    awaited the value is X - and X is what flows to the next call."""
    m = _COROUTINE.match(type_)
    return m.group(1) if m else type_


class _Lookups:
    """Per-analysis caches: each position is hovered once, each file parsed once."""

    def __init__(self, driver: PyrightDriver) -> None:
        self._driver = driver
        self._hovers: dict[tuple[Path, Pos], HoverInfo | None] = {}
        self._sites: dict[Path, list[CallSite]] = {}

    def hover(self, file: Path, pos: Pos | None) -> HoverInfo | None:
        if pos is None:
            return None
        if (file, pos) not in self._hovers:
            self._hovers[(file, pos)] = resolve_type(self._driver, file, *pos)
        return self._hovers[(file, pos)]

    def sites(self, file: Path) -> list[CallSite]:
        if file not in self._sites:
            # Only real .py sources: stub files (.pyi) for stdlib callees are skipped.
            ok = file.suffix == ".py" and file.exists()
            self._sites[file] = find_call_sites(file.read_text()) if ok else []
        return self._sites[file]


def _call_labels(graph: Graph, look: _Lookups) -> list[CallLabel]:
    """One label per call site that matches an edge of the graph."""
    labels: list[CallLabel] = []
    for edge in sorted(graph.edges, key=lambda e: (e.from_id, e.to_id)):
        caller, callee = graph.nodes[edge.from_id], graph.nodes[edge.to_id]
        file = caller.path
        for site in look.sites(file):
            if site.caller != caller.name or site.callee != callee.name:
                continue
            # The stored variable's type is the value that actually flows on, so prefer
            # it; fall back to the callee's declared return type for unassigned calls.
            returns = look.hover(file, site.assigned_pos) or look.hover(file, site.pos)
            returns_type = returns.type if returns else None
            if site.awaited and returns_type:
                returns_type = _unwrap_coroutine(returns_type)
            labels.append(
                CallLabel(
                    caller_id=caller.id,
                    callee_id=callee.id,
                    line=site.pos[0],
                    args=tuple(
                        ArgLabel(
                            text=a.text,
                            keyword=a.keyword,
                            type=info.type if (info := look.hover(file, a.pos)) else None,
                        )
                        for a in site.args
                    ),
                    returns_var=site.assigned_to,
                    returns_type=returns_type,
                )
            )
    return labels


def _flow_links(graph: Graph, look: _Lookups) -> list[FlowLink]:
    """A value stored from one call, then passed to another, for every function in the graph."""
    caller_id_of = {(n.path, n.name): n.id for n in graph.nodes.values()}
    callee_id_of = {(e.from_id, graph.nodes[e.to_id].name): e.to_id for e in graph.edges}

    links: list[FlowLink] = []
    for file in sorted({n.path for n in graph.nodes.values()}):
        for link in thread_variables(look.sites(file)):
            caller_id = caller_id_of.get((file, link.producer.caller))
            if caller_id is None:
                continue  # this function isn't part of the graph we were asked about
            info = look.hover(file, link.producer.assigned_pos) or look.hover(file, link.arg.pos)
            links.append(
                FlowLink(
                    caller_id=caller_id,
                    caller=link.producer.caller,
                    var=link.var,
                    type=info.type if info else None,
                    producer=link.producer.callee,
                    consumer=link.consumer.callee,
                    producer_id=callee_id_of.get((caller_id, link.producer.callee)),
                    consumer_id=callee_id_of.get((caller_id, link.consumer.callee)),
                )
            )
    return links


def annotate_graph(graph: Graph, driver: PyrightDriver) -> DataFlowGraph:
    look = _Lookups(driver)
    return DataFlowGraph(
        graph=graph,
        call_labels=_call_labels(graph, look),
        flow_links=_flow_links(graph, look),
    )
