"""Drift-Checker: a function's documentation against its code, judged by a model.

Only the fuzzy claims come here. Parameters, return values and raised exceptions are
checked deterministically in analysis/docstrings.py, so this agent never has to guess at
facts the code states exactly. Small on purpose, like the other agents: the wording is in
prompts/drift_checker.py and the surrounding decisions belong to the service.
"""

from __future__ import annotations

from wayfinder.agents.llm import LLM
from wayfinder.agents.prompts import drift_checker as prompts
from wayfinder.domain.graph import Node
from wayfinder.domain.labels import DataFlowGraph
from wayfinder.domain.results import DriftFinding


class DriftChecker:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    @staticmethod
    def build_prompt(node: Node, source: str, dfg: DataFlowGraph) -> str:
        """Deterministic, so the service can hash it as the cache key before any model call."""
        return prompts.build_prompt(node, source, dfg)

    def review(self, prompt: str) -> list[DriftFinding]:
        return prompts.parse_reply(self._llm.complete(prompts.SYSTEM, prompt))
