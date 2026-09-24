"""A model client wrapped in the guardrails, so no agent has to remember to apply them.

Around every call: refuse a prompt that is too large, count the call against the rate
limit (hosted models only - a local model costs nothing), and clean what comes back.
"""

from __future__ import annotations

from wayfinder.agents.llm.base import LLM
from wayfinder.core.config import Limits
from wayfinder.guardrails.egress import refuse_if_offline
from wayfinder.guardrails.llm_input import check_prompt_size
from wayfinder.guardrails.llm_output import sanitize_output
from wayfinder.guardrails.rate_limit import SlidingWindowLimiter


class GuardedLLM:
    def __init__(
        self, inner: LLM, limits: Limits, limiter: SlidingWindowLimiter, offline: bool = False
    ) -> None:
        self._inner = inner
        self._limits = limits
        self._limiter = limiter
        self._offline = offline

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def external(self) -> bool:
        return self._inner.external

    def complete(self, system: str, prompt: str) -> str:
        # The last line of defence: whatever code path got here, offline means nothing is sent.
        if self._inner.external:
            refuse_if_offline(self._offline)
        check_prompt_size(system, prompt, self._limits)
        if self._inner.external:
            self._limiter.acquire()
        return sanitize_output(self._inner.complete(system, prompt), self._limits)
