"""SQLite persistence for the graph: the queries, and nothing else.

GraphRepository is the only thing that opens the database file. The schema lives in
schema.py and the row <-> object conversion in mappers.py, so this file is only the
questions we ask of the data.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

from wayfinder.analysis.paths import shortest_call_path
from wayfinder.domain.graph import Direction, Edge, Graph, Node
from wayfinder.domain.labels import CallLabel, DataFlowGraph
from wayfinder.storage import mappers
from wayfinder.storage.schema import SCHEMA


class GraphRepository:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        # FastAPI runs sync routes in a thread pool, so this connection is used from
        # several threads. That's safe only because the services serialize every call
        # behind one lock - never share a GraphRepository without one.
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # --- write ---

    def save(self, dfg: DataFlowGraph) -> None:
        """Upsert a graph. Whatever this save re-analyzed replaces what was stored for
        it: every edge and label touching a node the graph fully expanded (so a call
        that was removed from the code disappears), labels for the edges it contains,
        flow links for the nodes it contains. One transaction, so a failure leaves the
        database unchanged."""
        graph = dfg.graph
        with self._db:
            self._db.executemany(
                """
                INSERT INTO nodes (id, name, kind, file, start_line, start_col, end_line, end_col, language)
                VALUES (:id, :name, :kind, :file, :start_line, :start_col, :end_line, :end_col, :language)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name, kind = excluded.kind, file = excluded.file,
                    start_line = excluded.start_line, start_col = excluded.start_col,
                    end_line = excluded.end_line, end_col = excluded.end_col,
                    language = excluded.language
                """,
                [asdict(n) for n in graph.nodes.values()],
            )
            expanded = [(i, i) for i in graph.expanded_ids]
            self._db.executemany("DELETE FROM edges WHERE from_id = ? OR to_id = ?", expanded)
            self._db.executemany("DELETE FROM call_labels WHERE caller_id = ? OR callee_id = ?", expanded)
            self._db.executemany(
                "INSERT OR IGNORE INTO edges (from_id, to_id, direction) VALUES (?, ?, ?)",
                [(e.from_id, e.to_id, e.direction) for e in graph.edges],
            )

            self._db.executemany(
                "DELETE FROM call_labels WHERE caller_id = ? AND callee_id = ?",
                [(e.from_id, e.to_id) for e in graph.edges],
            )
            # OR IGNORE: one line can call the same function twice; the first call is kept.
            self._db.executemany(
                """
                INSERT OR IGNORE INTO call_labels (caller_id, callee_id, line, args_json, returns_var, returns_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [mappers.call_label_params(c) for c in dfg.call_labels],
            )

            self._db.executemany("DELETE FROM flow_links WHERE caller_id = ?", [(i,) for i in graph.nodes])
            self._db.executemany(
                """
                INSERT INTO flow_links
                    (caller_id, caller, var, type, producer, consumer, producer_id, consumer_id)
                VALUES
                    (:caller_id, :caller, :var, :type, :producer, :consumer, :producer_id, :consumer_id)
                """,
                [asdict(f) for f in dfg.flow_links],
            )

    def set_narration(self, node_id: str, prompt_hash: str, text: str, model: str) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT INTO narrations (node_id, prompt_hash, text, model) VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    prompt_hash = excluded.prompt_hash, text = excluded.text,
                    model = excluded.model, created_at = CURRENT_TIMESTAMP
                """,
                (node_id, prompt_hash, text, model),
            )

    def set_path_explanation(self, prompt_hash: str, text: str, model: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO path_explanations (prompt_hash, text, model) VALUES (?, ?, ?)",
                (prompt_hash, text, model),
            )

    def set_drift_review(self, prompt_hash: str, findings_json: str, model: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO drift_reviews (prompt_hash, findings_json, model) VALUES (?, ?, ?)",
                (prompt_hash, findings_json, model),
            )

    # --- read: graph ---

    def get_node(self, node_id: str) -> Node | None:
        row = self._db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return mappers.to_node(row) if row else None

    def get_neighbors(self, node_id: str, hops: int = 1, direction: Direction | None = None) -> Graph:
        """Walk stored edges outward from a node. direction=None follows both ways;
        "incoming" walks toward callers, "outgoing" toward callees."""
        start = self.get_node(node_id)
        if start is None:
            raise KeyError(node_id)

        graph = Graph(root_id=node_id)
        graph.add_node(start)
        frontier = [node_id]
        for _ in range(hops):
            next_frontier: list[str] = []
            for current in frontier:
                for edge in self._edges_touching(current, direction):
                    other_id = edge.to_id if edge.from_id == current else edge.from_id
                    other = self.get_node(other_id)
                    assert other is not None  # foreign keys guarantee both ends exist
                    if graph.add_node(other):
                        next_frontier.append(other_id)
                    graph.add_edge(edge)
            frontier = next_frontier
            if not frontier:
                break
        return graph

    def get_dataflow_graph(
        self, node_id: str, hops: int = 1, direction: Direction | None = None
    ) -> DataFlowGraph:
        """get_neighbors plus the call labels and flow links that belong to it."""
        graph = self.get_neighbors(node_id, hops, direction)
        ids = list(graph.nodes)
        marks = ",".join("?" * len(ids))  # only "?" placeholders are interpolated

        label_rows = self._db.execute(
            f"""
            SELECT * FROM call_labels
            WHERE caller_id IN ({marks}) AND callee_id IN ({marks})
            ORDER BY caller_id, line
            """,
            ids + ids,
        ).fetchall()
        link_rows = self._db.execute(
            f"SELECT * FROM flow_links WHERE caller_id IN ({marks}) ORDER BY id", ids
        ).fetchall()

        return DataFlowGraph(
            graph=graph,
            call_labels=[mappers.to_call_label(r) for r in label_rows],
            flow_links=[mappers.to_flow_link(r) for r in link_rows],
        )

    def find_path(self, start_id: str, goal_id: str, max_hops: int) -> list[Edge] | None:
        """Shortest chain of calls from `start_id` to `goal_id` among the stored edges,
        or None. Both ends must have been analyzed with enough hops to connect."""
        for node_id in (start_id, goal_id):
            if self.get_node(node_id) is None:
                raise KeyError(node_id)
        return shortest_call_path(
            start_id, goal_id, max_hops, lambda node_id: self._edges_touching(node_id, "outgoing")
        )

    def get_call_labels(self, caller_id: str, callee_id: str) -> list[CallLabel]:
        """Every call from one function to another (there can be several call sites)."""
        rows = self._db.execute(
            "SELECT * FROM call_labels WHERE caller_id = ? AND callee_id = ? ORDER BY line",
            (caller_id, callee_id),
        ).fetchall()
        return [mappers.to_call_label(r) for r in rows]

    # --- read: generated text ---

    def get_narration(self, node_id: str, prompt_hash: str) -> str | None:
        """The stored explanation, but only if it was generated from this exact prompt."""
        row = self._db.execute(
            "SELECT text FROM narrations WHERE node_id = ? AND prompt_hash = ?",
            (node_id, prompt_hash),
        ).fetchone()
        return row["text"] if row else None

    def get_path_explanation(self, prompt_hash: str) -> str | None:
        row = self._db.execute(
            "SELECT text FROM path_explanations WHERE prompt_hash = ?", (prompt_hash,)
        ).fetchone()
        return row["text"] if row else None

    def get_drift_review(self, prompt_hash: str) -> str | None:
        row = self._db.execute(
            "SELECT findings_json FROM drift_reviews WHERE prompt_hash = ?", (prompt_hash,)
        ).fetchone()
        return row["findings_json"] if row else None

    # --- internal ---

    def _edges_touching(self, node_id: str, direction: Direction | None) -> list[Edge]:
        rows: list[sqlite3.Row] = []
        if direction in (None, "outgoing"):
            rows += self._db.execute("SELECT * FROM edges WHERE from_id = ?", (node_id,)).fetchall()
        if direction in (None, "incoming"):
            rows += self._db.execute("SELECT * FROM edges WHERE to_id = ?", (node_id,)).fetchall()
        return [mappers.to_edge(r) for r in rows]
