"""The graph's shape: what a node and an edge actually contain.

This is the contract every later part reads from - the API, the frontend, the
agents. None of them talk to pyright directly; they all read Node/Edge/Graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse


# Which way to walk the call graph: "incoming" toward callers, "outgoing" toward callees.
Direction = Literal["incoming", "outgoing"]


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    kind: int  # raw LSP SymbolKind (12 = Function, 6 = Method, 5 = Class, ...)
    file: str  # a file:// URI, as pyright reports it - use `path` for a real path
    # 1-indexed, like everything human-facing (see lsp/position.py). Only the wire
    # format to pyright is 0-indexed. The range covers the symbol's *name*.
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    language: str = "python"

    @property
    def path(self) -> Path:
        return Path(unquote(urlparse(self.file).path))


@dataclass(frozen=True)
class Edge:
    from_id: str  # caller
    to_id: str  # callee
    # Which query discovered this edge first - debug provenance only. compare=False
    # keeps it out of __eq__/__hash__, so the *same* call found from both ends
    # (once expanding the caller, once expanding the callee) still dedupes to one
    # edge instead of two - direction never changes what a call actually is.
    direction: Literal["incoming", "outgoing"] = field(compare=False)


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[Edge] = field(default_factory=set)
    root_id: str | None = None  # the node this graph was built around / expanded from
    # Nodes whose callers AND callees were all asked for, so their edges are known to be
    # complete. Only for these may a save replace what's stored (calls that no longer
    # exist must disappear); nodes at the edge of the search are not expanded, and their
    # other stored edges must be left alone.
    expanded_ids: set[str] = field(default_factory=set)

    def add_node(self, node: Node) -> bool:
        """Returns True if this node was new (not seen before)."""
        if node.id in self.nodes:
            return False
        self.nodes[node.id] = node
        return True

    def add_edge(self, edge: Edge) -> None:
        self.edges.add(edge)  # Edge is frozen + hashable, so this dedupes for free

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "nodes": [vars(n) for n in self.nodes.values()],
            "edges": [vars(e) for e in self.edges],
        }
