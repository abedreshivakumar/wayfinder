"""Narrator: one function in, a short plain-language explanation out.

The agent is small on purpose: the wording lives in prompts/narrator.py, and the
fetching, caching and guardrails belong to the service around it. All it owns is
"turn this context into a prompt, and ask the model".
"""

from __future__ import annotations

from wayfinder.agents.llm import LLM
from wayfinder.agents.prompts import narrator as prompts
from wayfinder.domain.graph import Node
from wayfinder.domain.labels import DataFlowGraph


class Narrator:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    @staticmethod
    def build_prompt(node: Node, source: str, dfg: DataFlowGraph) -> str:
        """Deterministic, so the service can hash it as the cache key before any model call."""
        return prompts.build_prompt(node, source, dfg)

    def explain(self, prompt: str) -> str:
        return self._llm.complete(prompts.SYSTEM, prompt)
