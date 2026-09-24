"""How the services reach a language model: one place for the key lookup, the allowlist,
the rate limiter and the guards, shared by every service that calls a model."""

from __future__ import annotations

from wayfinder.agents.llm import LLM, GuardedLLM, create_llm
from wayfinder.core.config import Settings
from wayfinder.core.errors import NotConfigured
from wayfinder.guardrails.egress import EgressPolicy
from wayfinder.guardrails.rate_limit import SlidingWindowLimiter


class ModelAccess:
    def __init__(self, settings: Settings, llm: LLM | None = None) -> None:
        self._settings = settings
        self._llm = llm  # None = look for a key when first needed, so analysis works without one
        self.egress = EgressPolicy(settings.llm_allowed_repos, settings.offline)
        # One limiter for the life of the service: the limit is over time, not per request.
        self._limiter = SlidingWindowLimiter(settings.limits.llm_calls_per_minute)

    def get(self) -> LLM:
        """The model client, or NotConfigured if there's no key."""
        if self._llm is None:
            self._llm = create_llm(self._settings)
        if self._llm is None:
            raise NotConfigured(
                "no Gemini API key found: set GEMINI_API_KEY, or put "
                "GEMINI_API_KEY=... in ~/.wayfinder/.env"
            )
        return self._llm

    def guarded(self, llm: LLM) -> GuardedLLM:
        """`llm` with the size limit, rate limit, offline switch and output cleaning applied."""
        return GuardedLLM(llm, self._settings.limits, self._limiter, self._settings.offline)
