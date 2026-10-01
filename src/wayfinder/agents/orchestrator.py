"""Orchestrator: a plain-English question in, an answer out, by choosing which of
Wayfinder's tools to call.

This is the one agent that runs a tool-using loop, so it is the only one that needs more
than "prompt in, text out". What runs that loop is an AgentRunner; the agent itself is the
rules it is given plus the tools it may use. Which tools exist, which repository they are
bound to, and every guardrail around them belong to the service that builds them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from wayfinder.agents.prompts import orchestrator as prompts


@dataclass(frozen=True)
class ToolSpec:
    """One tool the model may call."""

    name: str
    description: str
    schema: dict[str, Any]  # JSON Schema for the arguments (type: object)
    # Runs the tool and returns text for the model. A WayfinderError means "tell the model
    # what went wrong" and is shown to it as an error result.
    handler: Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class RunResult:
    text: str
    tools_used: list[str]  # names of the tools called, in order
    turns: int | None = None


class AgentRunner(Protocol):
    # True when the question and every tool result are sent to a hosted model.
    external: bool

    def run(self, *, system: str, question: str, tools: Sequence[ToolSpec], max_turns: int) -> RunResult: ...


class Orchestrator:
    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    @property
    def external(self) -> bool:
        return self._runner.external

    def answer(self, question: str, tools: Sequence[ToolSpec], max_turns: int) -> RunResult:
        return self._runner.run(system=prompts.SYSTEM, question=question, tools=tools, max_turns=max_turns)
