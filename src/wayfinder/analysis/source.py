"""Get a function's actual source text, so agents explain the real code, not a guess.

The graph knows *where* a symbol's name is; the agents need the whole body. Python's
ast gives exact start and end lines, so no text scanning is involved.
"""

from __future__ import annotations

import ast
from pathlib import Path

MAX_CHARS = 6000  # keeps one prompt bounded: a huge class would otherwise dominate the cost


def extract_source(file: Path, name: str, line: int, max_chars: int = MAX_CHARS) -> str | None:
    """Source of the function/method/class called `name` whose `def`/`class` is on
    `line` (1-indexed), including its decorators. None if there's no such definition.
    Longer than `max_chars` is cut off, so a prompt with several of these stays bounded."""
    text = file.read_text()
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == name
            and node.lineno == line
        ):
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            assert node.end_lineno is not None
            snippet = "\n".join(text.splitlines()[first - 1 : node.end_lineno])
            if len(snippet) > max_chars:
                snippet = snippet[:max_chars] + "\n... (truncated)"
            return snippet
    return None
