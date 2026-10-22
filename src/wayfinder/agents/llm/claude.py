"""Anthropic's Claude API, via the official SDK.

Used instead of Gemini when `ANTHROPIC_API_KEY` is set - mainly to get past Gemini's
15-calls/minute free-tier ceiling on a big repo, since a Claude API key's rate limit is
an account-level setting, not a fixed per-model cap baked into this file.
"""

from __future__ import annotations

import anthropic

from wayfinder.core.config import DEFAULT_CLAUDE_MODEL
from wayfinder.core.errors import LLMError

# Opus 5.5's safety classifiers can decline a request outright; routing a decline to
# Anthropic's recommended fallback model (by refusal category) means one rare classifier
# hit doesn't surface as "the model isn't available" for an otherwise-ordinary prompt.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeLLM:
    external = True  # every prompt is sent to Anthropic

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_CLAUDE_MODEL,
        *,
        max_output_tokens: int = 4096,
    ) -> None:
        self.model = model
        self._max_output_tokens = max_output_tokens
        # The SDK's own retrying (429s, 5xxs, connection errors - exponential backoff,
        # 2 attempts by default) covers transient failures; our own rate limiter in
        # guardrails/rate_limit.py is what actually paces calls against the account's cap.
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, prompt: str) -> str:
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=self._max_output_tokens,
                betas=[_FALLBACK_BETA],
                fallbacks="default",
                output_config={"effort": "medium"},
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError as e:
            raise LLMError(f"Claude rate-limited this request: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude returned HTTP {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"could not reach Claude: {e}") from e
        return self._text(response)

    @staticmethod
    def _text(response: anthropic.types.Message) -> str:
        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise LLMError(f"Claude declined to answer (category: {category or 'unspecified'})")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError(f"Claude gave an empty answer (stop reason: {response.stop_reason})")
        return text
