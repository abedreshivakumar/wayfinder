"""Finding how one function reaches another. Pure graph logic - no database, no pyright."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from wayfinder.domain.graph import Edge


def shortest_call_path(
    start_id: str,
    goal_id: str,
    max_hops: int,
    callees_of: Callable[[str], Iterable[Edge]],
) -> list[Edge] | None:
    """The shortest chain of calls from `start_id` to `goal_id` (each edge is caller ->
    callee, in call order), or None if there isn't one within `max_hops`.

    `callees_of(node_id)` yields the edges leaving a node - whatever the graph is stored
    in. Equally short chains are resolved by node id, so the answer never varies."""
    arrived_by: dict[str, Edge] = {}
    seen = {start_id}
    frontier = [start_id]

    for _ in range(max_hops):
        next_frontier: list[str] = []
        for current in frontier:
            for edge in sorted(callees_of(current), key=lambda e: e.to_id):
                if edge.to_id in seen:
                    continue
                seen.add(edge.to_id)
                arrived_by[edge.to_id] = edge
                next_frontier.append(edge.to_id)
                if edge.to_id == goal_id:
                    return _walk_back(arrived_by, start_id, goal_id)
        frontier = next_frontier
        if not frontier:
            break
    return None


def _walk_back(arrived_by: dict[str, Edge], start_id: str, goal_id: str) -> list[Edge]:
    chain: list[Edge] = []
    at = goal_id
    while at != start_id:
        chain.append(arrived_by[at])
        at = arrived_by[at].from_id
    return chain[::-1]
