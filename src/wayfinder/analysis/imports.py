"""Which files of a repository import which: the repo-level map.

Plain `ast` parsing, no pyright: reading every file's import lines is fast and exact, so the
whole-repo picture appears immediately, and the slower call-level analysis is left for
the one file someone opens.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

_MAX_FILE_BYTES = 1_000_000  # anything bigger is generated or data, not code worth mapping
_MAX_NAMES_SHOWN = 40  # enough to follow re-exports through a package's __init__.py


@dataclass(frozen=True)
class FileInfo:
    path: str  # relative to the repo, "/"-separated
    lines: int
    classes: int
    functions: int  # top-level functions plus methods
    doc: str | None  # first line of the module docstring
    error: str | None = None  # set when the file could not be parsed


@dataclass(frozen=True)
class ImportEdge:
    source: str  # the file that imports
    target: str  # the file imported
    names: list[str] = field(default_factory=list)  # what it takes from there (a few)
    weight: int = 1  # how many names / import statements


def _module_parts(rel: Path) -> list[str]:
    parts = list(rel.with_suffix("").parts)
    return parts[:-1] if parts and parts[-1] == "__init__" else parts


def build_import_graph(repo_root: Path, files: list[str]) -> tuple[list[FileInfo], list[ImportEdge]]:
    rels = [Path(f) for f in files]
    by_path = {r.as_posix(): r for r in rels}

    # Every dotted suffix of a file's module path points at that file, so `import
    # wayfinder.core.config` resolves in a src/ layout, where the folder holding the
    # package is not part of the name. A name several files share (two unrelated projects
    # in the same repo can each have a "config.py") is kept as a list of candidates rather
    # than being dropped, and resolved per-importer below.
    suffixes: dict[str, list[str]] = {}
    for r in rels:
        parts = _module_parts(r)
        for i in range(len(parts)):
            dotted = ".".join(parts[i:])
            suffixes.setdefault(dotted, []).append(r.as_posix())

    def lookup(dotted: str, importer: str) -> str | None:
        """Among files sharing this dotted name, the one nearest `importer` - same folder
        tree first - since an ambiguous plain name almost always means separate projects,
        not one the importer reaches across."""
        candidates = suffixes.get(dotted)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        importer_parts = Path(importer).parts[:-1]

        def shared_depth(c: str) -> int:
            c_parts = Path(c).parts[:-1]
            n = 0
            for a, b in zip(importer_parts, c_parts):
                if a != b:
                    break
                n += 1
            return n

        return max(candidates, key=lambda c: (shared_depth(c), -len(Path(c).parts)))

    def resolve_relative(source: Path, level: int, module: str | None, name: str | None) -> str | None:
        base = source.parent
        for _ in range(level - 1):
            base = base.parent
        candidates: list[Path] = []
        target = base.joinpath(*(module.split("."))) if module else base
        if name:
            candidates += [target / f"{name}.py", target / name / "__init__.py"]
        candidates += [target.with_suffix(".py") if module else target / "__init__.py", target / "__init__.py"]
        for c in candidates:
            if c.as_posix() in by_path and c.as_posix() != source.as_posix():
                return c.as_posix()
        return None

    infos: list[FileInfo] = []
    edges: dict[tuple[str, str], ImportEdge] = {}

    def add_edge(source: str, target: str | None, name: str) -> None:
        if target is None or target == source:
            return
        key = (source, target)
        old = edges.get(key)
        names = (old.names if old else []) + ([name] if name and name != "*" else [])
        edges[key] = ImportEdge(source, target, names[:_MAX_NAMES_SHOWN], (old.weight if old else 0) + 1)

    for rel in rels:
        full = repo_root / rel
        try:
            if full.stat().st_size > _MAX_FILE_BYTES:
                infos.append(FileInfo(rel.as_posix(), 0, 0, 0, None, "file too large to map"))
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError) as e:
            infos.append(FileInfo(rel.as_posix(), 0, 0, 0, None, f"could not parse: {type(e).__name__}"))
            continue

        doc = ast.get_docstring(tree)
        infos.append(
            FileInfo(
                path=rel.as_posix(),
                lines=text.count("\n") + 1,
                classes=sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
                functions=sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)),
                doc=doc.strip().splitlines()[0] if doc and doc.strip() else None,
            )
        )
        src = rel.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dotted = alias.name
                    while dotted and lookup(dotted, src) is None:  # `import a.b.c` may only exist as a.b
                        dotted = dotted.rpartition(".")[0]
                    add_edge(src, lookup(dotted, src) if dotted else None, alias.name.rpartition(".")[2])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if node.level:
                        add_edge(src, resolve_relative(rel, node.level, node.module, alias.name), alias.name)
                    elif node.module:
                        add_edge(src, lookup(f"{node.module}.{alias.name}", src) or lookup(node.module, src), alias.name)
    return infos, list(edges.values())
