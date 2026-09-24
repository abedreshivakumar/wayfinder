"""Database rows <-> domain objects: the one place column names meet field names.

If a column changes, this file and schema.py change - the repository's queries don't.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from wayfinder.domain.graph import Edge, Node
from wayfinder.domain.labels import ArgLabel, CallLabel, FlowLink


def to_node(row: sqlite3.Row) -> Node:
    return Node(**dict(row))


def to_edge(row: sqlite3.Row) -> Edge:
    return Edge(from_id=row["from_id"], to_id=row["to_id"], direction=row["direction"])


def to_call_label(row: sqlite3.Row) -> CallLabel:
    return CallLabel(
        caller_id=row["caller_id"],
        callee_id=row["callee_id"],
        line=row["line"],
        args=tuple(ArgLabel(**a) for a in json.loads(row["args_json"])),
        returns_var=row["returns_var"],
        returns_type=row["returns_type"],
    )


def to_flow_link(row: sqlite3.Row) -> FlowLink:
    return FlowLink(**{key: row[key] for key in row.keys() if key != "id"})


def call_label_params(label: CallLabel) -> tuple:
    """A CallLabel as the parameters of the INSERT into call_labels."""
    return (
        label.caller_id,
        label.callee_id,
        label.line,
        json.dumps([asdict(a) for a in label.args]),
        label.returns_var,
        label.returns_type,
    )
