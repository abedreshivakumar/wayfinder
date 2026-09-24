"""Path-Explainer: a chain of calls in, one narrated walk through it out.

Like the Narrator it is small on purpose: the wording lives in prompts/path_explainer.py,
and finding the chain, caching and the guardrails belong to the service around it.
"""

from __future__ import annotations

from wayfinder.agents.llm import LLM
from wayfinder.agents.prompts import path_explainer as prompts
from wayfinder.domain.graph import Node
from wayfinder.domain.labels import CallLabel


class PathExplainer:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    @staticmethod
    def build_prompt(nodes: list[Node], sources: list[str | None], hop_labels: list[list[CallLabel]]) -> str:
        """Deterministic, so the service can hash it as the cache key before any model call."""
        return prompts.build_prompt(nodes, sources, hop_labels)

    def explain(self, prompt: str) -> str:
        return self._llm.complete(prompts.SYSTEM, prompt)
