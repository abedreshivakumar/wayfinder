"""The one thing the agents need from a language model, whichever provider it is."""

from __future__ import annotations

from typing import Protocol


class LLM(Protocol):
    model: str
    # True when prompts leave this machine (a hosted API); False for a local model or a
    # test double. The guardrails apply their data-egress rules only to external ones.
    external: bool

    def complete(self, system: str, prompt: str) -> str:
        """One system prompt and one user prompt in, the model's text out."""
        ...
