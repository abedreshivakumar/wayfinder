"""Every error this package raises on purpose, in one hierarchy.

Inner layers (services, agents, guardrails) raise these; the outer layers (the HTTP API
and the MCP server) translate them - each in its own way, in one place each. Anything
that is *not* a WayfinderError is a bug, and is allowed to surface as one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wayfinder.domain.results import SymbolMatch


class WayfinderError(Exception):
    """Base of every deliberate error. The message is written to be shown to a person."""


class BadRequest(WayfinderError):
    """The request itself is wrong; the caller can fix it and try again."""


class PromptTooLarge(BadRequest):
    """What we would send to the model is over the size limit."""


class Forbidden(WayfinderError):
    """The request is understood but a guardrail refuses it (e.g. code that may not be
    sent to an external model)."""


class RateLimited(WayfinderError):
    """Too many model calls too quickly; `retry_after` is how many seconds to wait."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotFound(WayfinderError):
    """Something the request refers to doesn't exist."""


class SymbolNotFound(NotFound):
    """No function, method or class with that name."""


class NodeNotFound(NotFound):
    """No analyzed function with that id."""


class NoPath(NotFound):
    """The analyzed graph has no chain of calls between the two functions."""


class AmbiguousSymbol(WayfinderError):
    """A name matches several symbols; `matches` says which, so the caller can pick one."""

    def __init__(self, query: str, matches: Sequence[SymbolMatch]) -> None:
        self.matches = list(matches)
        names = ", ".join(f"{m.qualified_name} (line {m.line})" for m in self.matches)
        super().__init__(f"'{query}' matches {len(self.matches)} symbols: {names}. Use a qualified name.")


class NotConfigured(WayfinderError):
    """Something the server needs (for example an LLM key) isn't set up."""


class UpstreamError(WayfinderError):
    """A service we depend on failed - not the caller's fault, and not a bug here."""


class LLMError(UpstreamError):
    """The model provider failed or refused. The message never contains the API key."""
