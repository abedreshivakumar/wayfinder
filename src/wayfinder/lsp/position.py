"""Conversion between human-friendly positions and LSP's position format.

Humans (and editors) count lines and columns starting at 1. LSP counts both
starting at 0. Mixing these up silently points every query at the wrong
character - this is the one place that conversion happens, so it only has
to be gotten right once.
"""

from __future__ import annotations


def to_lsp_position(line: int, col: int) -> dict[str, int]:
    """line, col: 1-indexed, as you'd read them off in an editor's status bar."""
    if line < 1 or col < 1:
        raise ValueError(f"line and col are 1-indexed, got line={line} col={col}")
    return {"line": line - 1, "character": col - 1}


def from_lsp_position(position: dict[str, int]) -> tuple[int, int]:
    """Returns (line, col), 1-indexed."""
    return position["line"] + 1, position["character"] + 1
