"""Turning the package's deliberate errors into what a calling model sees."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ToolError

from wayfinder.core.errors import WayfinderError


@contextmanager
def tool_errors() -> Generator[None]:
    try:
        yield
    except WayfinderError as e:
        # Only a ToolError's message reaches the calling model; any other exception is
        # reported as a bare "Error executing tool". These messages are written to be
        # acted on (e.g. the ambiguity error lists the candidates to choose from).
        raise ToolError(str(e)) from e
