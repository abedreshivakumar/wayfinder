"""The tools other agents can call. Each is one service call; the docstrings are what the
calling model reads to decide how to use them, so they say exactly what each argument
means and what comes back."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.types import ToolAnnotations

from wayfinder.domain.graph import Direction
from wayfinder.mcp_server.app import mcp
from wayfinder.mcp_server.errors import tool_errors
from wayfinder.mcp_server.lifecycle import get_services

# Read-only as far as the user's code and environment go; the only thing written is
# Wayfinder's own cache under ~/.wayfinder.
READ_ONLY = ToolAnnotations(readOnlyHint=True)


def _graph(repo: str, file: str, symbol: str, hops: int, direction: Direction | None) -> dict[str, Any]:
    with tool_errors():
        return get_services().analysis.analyze(
            repo, file, symbol=symbol, hops=hops, direction=direction
        ).to_dict()


@mcp.tool(annotations=READ_ONLY)
def who_calls(repo: str, file: str, symbol: str, hops: int = 1) -> dict[str, Any]:
    """Find the callers of a Python function, method or class.

    Args:
        repo: Absolute path to the repository root.
        file: Path of the file defining the symbol, relative to `repo`.
        symbol: Name of the function/method/class. Use "Class.method" if the plain
            name is ambiguous (the error lists the candidates).
        hops: How many caller levels to walk (1 = direct callers only, max 5).

    Returns a graph: `root_id` is the symbol you asked about, `nodes` are functions
    (file is a URI, lines are 1-indexed), `edges` are calls from `from_id` to `to_id`.
    `call_labels` give each call's line, arguments with types, and return type.
    """
    return _graph(repo, file, symbol, hops, "incoming")


@mcp.tool(annotations=READ_ONLY)
def what_does_this_call(repo: str, file: str, symbol: str, hops: int = 1) -> dict[str, Any]:
    """Find everything a Python function, method or class calls.

    Args:
        repo: Absolute path to the repository root.
        file: Path of the file defining the symbol, relative to `repo`.
        symbol: Name of the function/method/class. Use "Class.method" if the plain
            name is ambiguous (the error lists the candidates).
        hops: How many callee levels to walk (1 = direct calls only, max 5).

    Returns the same graph shape as who_calls, walking toward callees instead.
    """
    return _graph(repo, file, symbol, hops, "outgoing")


@mcp.tool(annotations=READ_ONLY)
def trace_data_flow(repo: str, file: str, symbol: str, hops: int = 1) -> dict[str, Any]:
    """Show how data moves through a function: who calls it, what it calls, and
    which value returned by one call is passed into another.

    Args:
        repo: Absolute path to the repository root.
        file: Path of the file defining the symbol, relative to `repo`.
        symbol: Name of the function/method/class. Use "Class.method" if the plain
            name is ambiguous (the error lists the candidates).
        hops: How many levels to walk in both directions (max 5).

    Returns the who_calls graph in both directions plus `flow_links`: each says that
    the call `producer` returned a value stored in variable `var` (of type `type`)
    which was later passed to the call `consumer`, inside function `caller`.
    """
    return _graph(repo, file, symbol, hops, None)


@mcp.tool(annotations=READ_ONLY)
def explain_function(repo: str, file: str, symbol: str) -> dict[str, Any]:
    """Explain in plain language what a Python function, method or class does.

    The explanation is written from the real source plus the analyzed call graph (who
    calls it, what it calls, what data it passes on), not from guesses; where something
    isn't visible it says so. Use who_calls / trace_data_flow when you need the
    structure itself rather than a summary.

    Args:
        repo: Absolute path to the repository root.
        file: Path of the file defining the symbol, relative to `repo`.
        symbol: Name of the function/method/class. Use "Class.method" if the plain
            name is ambiguous (the error lists the candidates).

    Returns `text` (the explanation) and `cached` (true if it was reused from an
    earlier request for unchanged code). Needs a Gemini API key configured on the server.
    """
    with tool_errors():
        return asdict(get_services().explanation.explain_symbol(repo, file, symbol=symbol))


@mcp.tool(annotations=READ_ONLY)
def explain_call_path(
    repo: str, from_file: str, from_symbol: str, to_file: str, to_symbol: str, hops: int = 3
) -> dict[str, Any]:
    """Explain in plain language how one function reaches another through the calls
    between them - for example how a request handler ends up at a database call.

    The two functions may be given in either order; the chain is returned in call order
    (each function calls the next). The explanation is written from the real source and
    the analyzed argument and return types of every step, not from guesses.

    Args:
        repo: Absolute path to the repository root.
        from_file: File defining the first function, relative to `repo`.
        from_symbol: Name of the first function ("Class.method" if the name is ambiguous).
        to_file: File defining the second function, relative to `repo`.
        to_symbol: Name of the second function.
        hops: The longest chain to look for (1-5, default 3).

    Returns `names` (the chain), `node_ids`, `text` (the explanation) and `cached`. If no
    chain exists within `hops` the error says so; try a larger `hops`. Needs a Gemini API
    key configured on the server.
    """
    with tool_errors():
        return asdict(
            get_services().explanation.explain_path_between(repo, from_file, from_symbol, to_file, to_symbol, hops)
        )


@mcp.tool(annotations=READ_ONLY)
def check_docs_drift(repo: str, file: str, symbol: str) -> dict[str, Any]:
    """Check whether a Python function's documentation still matches its code.

    Finds docstrings that have gone stale: a parameter the docstring documents but the
    function doesn't have, a documented return value that is never returned, exceptions
    the docstring lists that are never raised. A model also reviews the fuzzier claims
    when one is available; the static findings never need a model.

    Args:
        repo: Absolute path to the repository root.
        file: Path of the file defining the function, relative to `repo`.
        symbol: Name of the function or method ("Class.method" if the name is ambiguous).

    Returns `findings` (each with `severity` high/medium/low, `message`, `line`, and
    `source` static or model) and `model_review`: "done", "cached", or "skipped: <why>"
    (no key, offline mode, repo not allowed) - the static findings are present either way.
    """
    with tool_errors():
        return asdict(get_services().drift.check_symbol(repo, file, symbol=symbol))
