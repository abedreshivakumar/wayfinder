"""Which language a file belongs to, and how to get a driver for it.

Today there is one language, Python. This exists so a second one (JavaScript/TypeScript)
is additive - a new `Language` entry - rather than a rewrite of `DriverPool`, the guardrails,
or the file listing, none of which should have to know a new language was added.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from wayfinder.analysis.imports import FileInfo, ImportEdge
    from wayfinder.analysis.outline import Outline


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
    # (file path, source text) -> what that one file defines - functions, classes, schemas.
    # The path matters here (unlike for pyright/tsserver, which only ever see real files on
    # disk): a JS/TS implementation needs the extension to know whether to parse the file
    # as .ts, .tsx, .js or .jsx.
    outline: Callable[[Path, str], "Outline"]
    # (repo root, every file in the repo this language owns) -> which of those files import
    # which. Only ever called with files this language's own `extensions` matched, so an
    # implementation never has to recognize another language's import syntax.
    build_imports: Callable[[Path, list[str]], tuple[list["FileInfo"], list["ImportEdge"]]]


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


def outline_for(path: Path, source: str) -> "Outline | None":
    """`path`'s language's outline of it, or None if no registered language claims it (the
    file is then skipped rather than failing the whole repo's analysis)."""
    language = for_file(path)
    return None if language is None else language.outline(path, source)


def build_import_graph(repo_root: Path, files: list[str]) -> tuple[list["FileInfo"], list["ImportEdge"]]:
    """Every file's import info and the edges between them, across every registered
    language at once - each file goes to the language that owns its extension, so a mixed
    Python + JS repo gets both analyzed, just never cross-linked to each other (a Python
    file importing a JS one isn't a real thing to resolve)."""
    by_language: dict[str, list[str]] = {}
    for f in files:
        language = for_file(Path(f))
        if language is not None:
            by_language.setdefault(language.id, []).append(f)

    infos: list[FileInfo] = []
    edges: list[ImportEdge] = []
    for language in _REGISTRY.values():
        language_files = by_language.get(language.id, [])
        if not language_files:
            continue
        language_infos, language_edges = language.build_imports(repo_root, language_files)
        infos += language_infos
        edges += language_edges
    return infos, edges
