"""BFS expansion: walk outward from one symbol, N hops, into a Graph.

This is where Part 1 actually answers "who calls this, and what does it call" -
everything before this file just made asking pyright a single question possible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wayfinder.domain.graph import Edge, Graph, Node
from wayfinder.lsp.position import from_lsp_position
from wayfinder.languages import LanguageDriver


def _node_id(item: dict[str, Any]) -> str:
    """A stable id for a CallHierarchyItem: its file + exact position.

    Using file+position (not just name) matters because two different functions
    in two different files can share a name - the id has to be unambiguous.
    """
    sel = item["selectionRange"]["start"]
    return f"{item['uri']}#{sel['line']}:{sel['character']}"


def _item_to_node(item: dict[str, Any]) -> Node:
    start_line, start_col = from_lsp_position(item["range"]["start"])
    end_line, end_col = from_lsp_position(item["range"]["end"])
    return Node(
        id=_node_id(item),
        name=item["name"],
        kind=item["kind"],
        file=item["uri"],
        start_line=start_line,
        start_col=start_col,
        end_line=end_line,
        end_col=end_col,
    )


def build_call_graph(driver: LanguageDriver, file: Path, line: int, col: int, hops: int = 2) -> Graph:
    """line, col are 1-indexed. Expands `hops` levels out in both directions
    from the symbol at that position."""
    start_item = driver.prepare_call_hierarchy(file, line, col)
    if start_item is None:
        raise ValueError(f"no callable symbol found at {file}:{line}:{col}")

    graph = Graph()
    root = _item_to_node(start_item)
    graph.add_node(root)
    graph.root_id = root.id

    frontier = [start_item]  # items still to expand, this hop
    for _ in range(hops):
        next_frontier: list[dict[str, Any]] = []

        for item in frontier:
            item_id = _node_id(item)
            graph.expanded_ids.add(item_id)

            for call in driver.incoming_calls(item):
                caller_item = call["from"]
                caller_node = _item_to_node(caller_item)
                if graph.add_node(caller_node):
                    next_frontier.append(caller_item)
                graph.add_edge(Edge(from_id=caller_node.id, to_id=item_id, direction="incoming"))

            for call in driver.outgoing_calls(item):
                callee_item = call["to"]
                callee_node = _item_to_node(callee_item)
                if graph.add_node(callee_node):
                    next_frontier.append(callee_item)
                graph.add_edge(Edge(from_id=item_id, to_id=callee_node.id, direction="outgoing"))

        frontier = next_frontier
        if not frontier:
            break  # nothing new to expand - graph has stabilized before `hops` was reached

    return graph
