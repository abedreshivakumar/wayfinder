"""What may be sent to a model, and how untrusted text is presented to it."""

from __future__ import annotations

import re

from wayfinder.core.config import Limits
from wayfinder.core.errors import PromptTooLarge


def fence(text: str, info: str = "python") -> str:
    """`text` in a code fence that the text itself cannot close.

    Repository source is untrusted: a string or comment inside it could contain a line of
    backticks to break out of the block and pose as instructions. The fence is made one
    backtick longer than the longest run inside the text, so that can't happen - and it
    is deterministic, so the same source always gives the same prompt (the cache key)."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{info}\n{text}\n{ticks}"


def check_prompt_size(system: str, prompt: str, limits: Limits) -> None:
    size = len(system) + len(prompt)
    if size > limits.max_prompt_chars:
        raise PromptTooLarge(
            f"the request would send {size:,} characters to the model; the limit is "
            f"{limits.max_prompt_chars:,}. Ask about a smaller function or fewer hops."
        )
