"""File-Explainer: one file plus its analyzed structure in, a plain-language walkthrough out.
Like the Narrator, the agent only turns a prompt into a model call; fetching, caching and
guardrails belong to the service around it."""

from __future__ import annotations

from typing import Any

from wayfinder.agents.llm import LLM
from wayfinder.agents.prompts import file_explainer as prompts


class FileExplainer:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    @staticmethod
    def build_prompt(rel_file: str, source: str, graph: dict[str, Any]) -> str:
        return prompts.build_prompt(rel_file, source, graph)

    def explain(self, prompt: str) -> str:
        return self._llm.complete(prompts.SYSTEM, prompt)
