"""What we accept back from a model."""

from __future__ import annotations

from wayfinder.core.config import Limits
from wayfinder.guardrails.secrets import redact_secrets


def sanitize_output(text: str, limits: Limits) -> str:
    """Blank out anything that looks like a secret (a model can repeat one it was shown)
    and cap the length, cutting at a word so it doesn't end mid-word."""
    text, _ = redact_secrets(text)
    if len(text) > limits.max_output_chars:
        cut = text[: limits.max_output_chars]
        text = cut[: cut.rfind(" ")] if " " in cut else cut
        text = text.rstrip() + " …"
    return text
