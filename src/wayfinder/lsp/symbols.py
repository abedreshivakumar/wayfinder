"""Turn a name like "fetch_user" into the position the rest of the engine needs.

Everything downstream wants a line and column. People (and MCP clients like Claude
Code) know names. pyright's documentSymbol gives every symbol in a file with its
exact position, so this file is the bridge - no parsing of our own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wayfinder.domain.results import SymbolMatch
from wayfinder.lsp.position import from_lsp_position
from wayfinder.languages import LanguageDriver

# LSP SymbolKind values for things that can be called: Class(5) is included because
# instantiating a class is a call, Constructor(9) for completeness.
_CALLABLE_KINDS = {5, 6, 9, 12}  # Class, Method, Constructor, Function


def find_symbols(driver: LanguageDriver, file: Path, query: str) -> list[SymbolMatch]:
    """Callable symbols in `file` matching `query`.

    `query` is a plain name ("fetch_user") or a dotted path
    ("UserService.fetch_user"). A plain name matches every symbol with that
    name, so it can return several - the caller decides what to do about ambiguity."""
    found: list[SymbolMatch] = []

    def walk(symbols: list[dict[str, Any]], prefix: str) -> None:
        for sym in symbols:
            qualified = f"{prefix}{sym['name']}"
            if sym["kind"] in _CALLABLE_KINDS and (
                qualified == query or qualified.endswith("." + query) or sym["name"] == query
            ):
                line, col = from_lsp_position(sym["selectionRange"]["start"])
                found.append(SymbolMatch(qualified, sym["kind"], line, col))
            walk(sym.get("children", []), f"{qualified}.")

    walk(driver.document_symbols(file), "")
    return found


def list_symbols(driver: LanguageDriver, file: Path) -> list[SymbolMatch]:
    """Every callable symbol in `file`, in file order, for picking one from a list."""
    found: list[SymbolMatch] = []

    def walk(symbols: list[dict[str, Any]], prefix: str) -> None:
        for sym in symbols:
            qualified = f"{prefix}{sym['name']}"
            if sym["kind"] in _CALLABLE_KINDS:
                line, col = from_lsp_position(sym["selectionRange"]["start"])
                found.append(SymbolMatch(qualified, sym["kind"], line, col))
            walk(sym.get("children", []), f"{qualified}.")

    walk(driver.document_symbols(file), "")
    return found
