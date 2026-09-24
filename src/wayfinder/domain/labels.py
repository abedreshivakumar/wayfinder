"""What the data-flow analysis says about calls: argument and return types, and which
call's result feeds which. Plain data - the algorithm that fills these in lives in
analysis/dataflow/annotate.py."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from wayfinder.domain.graph import Graph


@dataclass(frozen=True)
class ArgLabel:
    text: str  # the argument expression as written, e.g. "uid"
    keyword: str | None  # set for `uid=uid` style arguments
    type: str | None  # None when the argument isn't a bare name we can hover


@dataclass(frozen=True)
class CallLabel:
    caller_id: str
    callee_id: str
    line: int  # where the call is in the caller's file, 1-indexed
    args: tuple[ArgLabel, ...]
    returns_var: str | None  # variable the result was stored in, if any
    returns_type: str | None


@dataclass(frozen=True)
class FlowLink:
    caller_id: str  # node id of that function, so a stored link can be tied to its node
    caller: str  # name of the function whose body contains both calls
    var: str
    type: str | None
    producer: str  # callee name whose result was stored in `var`
    consumer: str  # callee name that later received `var`
    # Node ids, when that call is also an edge in the graph. None when the graph
    # was cut off (hop limit) before reaching that callee.
    producer_id: str | None
    consumer_id: str | None


@dataclass
class DataFlowGraph:
    """A Graph plus the labels and links that describe its calls."""

    graph: Graph
    call_labels: list[CallLabel] = field(default_factory=list)
    flow_links: list[FlowLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.graph.to_dict(),
            "call_labels": [asdict(c) for c in self.call_labels],
            "flow_links": [asdict(f) for f in self.flow_links],
        }
