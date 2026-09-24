"""Google's Gemini API, over plain HTTPS (no SDK dependency).

Retries the failures worth retrying - rate limits and Google's "high demand" 503s - with
growing waits, and gives up straight away on errors that would fail identically again.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from wayfinder.core.config import DEFAULT_MODEL
from wayfinder.core.errors import LLMError

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}  # rate limit or "try again": Google returns 503 under load


class GeminiLLM:
    external = True  # every prompt is sent to Google

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        max_attempts: int = 4,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._max_attempts = max_attempts
        self._timeout = timeout
        self._sleep = sleep  # injectable so tests don't really wait

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                # Low temperature: these agents explain code they were shown, so
                # sticking to the source matters more than variety.
                "generationConfig": {"temperature": 0.2},
            }
        ).encode()
        # The key goes in a header, never the URL, so it can't leak into logs.
        request = urllib.request.Request(
            _ENDPOINT.format(model=self.model),
            data=body,
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
        )

        for attempt in range(1, self._max_attempts + 1):
            last = attempt == self._max_attempts
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return self._text(json.load(response))
            except urllib.error.HTTPError as e:
                if e.code in _RETRYABLE_STATUS and not last:
                    self._backoff(attempt)
                    continue
                raise LLMError(f"Gemini returned HTTP {e.code}: {self._error_message(e)}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if not last:
                    self._backoff(attempt)
                    continue
                raise LLMError(f"could not reach Gemini: {e}") from e
        raise AssertionError("unreachable: the loop returns or raises on its last attempt")

    def _backoff(self, attempt: int) -> None:
        self._sleep(2 ** (attempt - 1) + random.random())  # 1s, 2s, 4s, plus jitter

    @staticmethod
    def _error_message(error: urllib.error.HTTPError) -> str:
        try:
            return json.load(error)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            return error.reason or "no details"

    @staticmethod
    def _text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
            raise LLMError(f"Gemini gave no answer ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMError(f"Gemini gave an empty answer (finish reason: {candidates[0].get('finishReason')})")
        return text
