"""Choosing which model client to use, from the settings."""

from __future__ import annotations

from wayfinder.agents.llm.base import LLM
from wayfinder.agents.llm.claude import ClaudeLLM
from wayfinder.agents.llm.gemini import GeminiLLM
from wayfinder.core.config import Settings


def create_llm(settings: Settings) -> LLM | None:
    """The configured model client, or None when no API key is set up.

    Claude wins when both are configured - usually because Gemini's free-tier cap
    (14 calls/minute) was the reason someone added a Claude key in the first place."""
    if settings.anthropic_api_key is not None:
        return ClaudeLLM(settings.anthropic_api_key, settings.claude_model)
    if settings.gemini_api_key is not None:
        return GeminiLLM(settings.gemini_api_key, settings.model)
    return None
