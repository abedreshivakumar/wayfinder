"""Choosing which model client to use, from the settings."""

from __future__ import annotations

from wayfinder.agents.llm.base import LLM
from wayfinder.agents.llm.gemini import GeminiLLM
from wayfinder.core.config import Settings


def create_llm(settings: Settings) -> LLM | None:
    """The configured model client, or None when no API key is set up."""
    if settings.gemini_api_key is None:
        return None
    return GeminiLLM(settings.gemini_api_key, settings.model)
