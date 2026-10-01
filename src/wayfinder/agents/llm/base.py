"""The one thing the agents need from a language model, whichever provider it is."""

from __future__ import annotations

from typing import Protocol


class LLM(Protocol):
    @property
    def model(self) -> str: ...

    # True when prompts leave this machine (a hosted API); False for a local model or a
    # test double. The guardrails apply their data-egress rules only to external ones.
    @property
    def external(self) -> bool: ...

    def complete(self, system: str, prompt: str) -> str:
        """One system prompt and one user prompt in, the model's text out."""
        ...
