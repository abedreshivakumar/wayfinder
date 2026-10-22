"""Which language a file belongs to, and how to get a driver for it.

Today there is one language, Python. This exists so a second one (JavaScript/TypeScript)
is additive - a new `Language` entry - rather than a rewrite of `DriverPool`, the guardrails,
or the file listing, none of which should have to know a new language was added.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class LanguageDriver(Protocol):
    """What `analysis/call_graph.py`, `analysis/dataflow/`, and `lsp/symbols.py` need from a
    language server driver. `PyrightDriver` already has this exact shape."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def prepare_call_hierarchy(self, file: Path, line: int, col: int) -> dict[str, Any] | None: ...
    def incoming_calls(self, item: dict[str, Any]) -> list[dict[str, Any]]: ...
    def outgoing_calls(self, item: dict[str, Any]) -> list[dict[str, Any]]: ...
    def hover(self, file: Path, line: int, col: int) -> str | None: ...
    def document_symbols(self, file: Path) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Language:
    id: str  # "python"
    extensions: frozenset[str]  # {".py"}
    skipped_dirs: frozenset[str]  # folder names never worth walking into for this language
    make_driver: Callable[[Path], LanguageDriver]  # repo_root -> a started-on-demand driver


_REGISTRY: dict[str, Language] = {}


def register(language: Language) -> None:
    _REGISTRY[language.id] = language


def all_languages() -> list[Language]:
    return list(_REGISTRY.values())


def all_extensions() -> frozenset[str]:
    """Every file extension any registered language claims - what `resolve_file` and the
    file listing accept."""
    out: set[str] = set()
    for language in _REGISTRY.values():
        out |= language.extensions
    return frozenset(out)


def all_skipped_dirs() -> frozenset[str]:
    out: set[str] = set()
    for language in _REGISTRY.values():
        out |= language.skipped_dirs
    return frozenset(out)


def for_file(path: Path) -> Language | None:
    """The language that owns this file's extension, or None if nothing claims it."""
    for language in _REGISTRY.values():
        if path.suffix in language.extensions:
            return language
    return None
