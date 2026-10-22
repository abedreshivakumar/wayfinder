"""Which JS/TS files of a repository import which - the JS/TS counterpart of
`analysis/imports.py`. Resolves relative imports (`./foo`, `../bar`) and simple
`tsconfig.json` path aliases to real files; a bare package import (`react`, `lodash`) is
external and isn't resolved to anything in the repo, the same way Python's resolver drops
an import it can't find among the repo's own files.
"""

from __future__ import annotations

import json
from pathlib import Path

from wayfinder.analysis.imports import FileInfo, ImportEdge
from wayfinder.languages.javascript.outline import analyze

_MAX_FILE_BYTES = 1_000_000
_MAX_NAMES_SHOWN = 40
_CANDIDATE_EXTENSIONS = (".ts", ".tsx", ".d.ts", ".js", ".jsx")
_INDEX_FILES = tuple(f"index{ext}" for ext in _CANDIDATE_EXTENSIONS)


def _read_path_aliases(repo_root: Path) -> dict[str, list[str]]:
    """`compilerOptions.paths` from the repo's own `tsconfig.json`, resolved against its
    `baseUrl` - `{"@app/*": ["src/app/*"]}` becomes `{"@app/": ["src/app/"]}`. Missing,
    malformed, or using project-reference `extends` chains: treated as no aliases - those
    imports just end up external instead, same as a package Wayfinder doesn't resolve."""
    tsconfig = repo_root / "tsconfig.json"
    if not tsconfig.is_file():
        return {}
    try:
        options = json.loads(tsconfig.read_text(encoding="utf-8", errors="replace")).get("compilerOptions", {})
    except ValueError:
        return {}
    base = (repo_root / options.get("baseUrl", ".")).resolve()
    out: dict[str, list[str]] = {}
    for pattern, targets in (options.get("paths") or {}).items():
        key = pattern.removesuffix("*")
        out[key] = [str((base / t.removesuffix("*")).relative_to(repo_root)) for t in targets if isinstance(t, str)]
    return out


def _resolve(specifier: str, from_file: Path, repo_root: Path, aliases: dict[str, list[str]], by_path: set[str]) -> str | None:
    if specifier.startswith("."):
        base = (from_file.parent / specifier).resolve()
    else:
        target_dirs = next((targets for prefix, targets in aliases.items() if specifier.startswith(prefix)), None)
        if target_dirs is None:
            return None  # a bare package import (react, lodash, ...): external, not ours to resolve
        rest = specifier[len(next(p for p in aliases if specifier.startswith(p))):]
        base = (repo_root / target_dirs[0] / rest).resolve()

    for candidate in (base, *(base.with_suffix(base.suffix + ext) for ext in _CANDIDATE_EXTENSIONS), *(base / name for name in _INDEX_FILES)):
        try:
            rel = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel in by_path:
            return rel
    return None


def build_import_graph(repo_root: Path, files: list[str]) -> tuple[list[FileInfo], list[ImportEdge]]:
    rels = [Path(f) for f in files]
    by_path = {r.as_posix() for r in rels}
    aliases = _read_path_aliases(repo_root)

    infos: list[FileInfo] = []
    edges: dict[tuple[str, str], ImportEdge] = {}

    def add_edge(source: str, target: str | None, names: list[str]) -> None:
        if target is None or target == source:
            return
        key = (source, target)
        old = edges.get(key)
        all_names = (old.names if old else []) + [n for n in names if n and n != "*"]
        edges[key] = ImportEdge(source, target, all_names[:_MAX_NAMES_SHOWN], (old.weight if old else 0) + 1)

    for rel in rels:
        full = repo_root / rel
        try:
            if full.stat().st_size > _MAX_FILE_BYTES:
                infos.append(FileInfo(rel.as_posix(), 0, 0, 0, None, "file too large to map"))
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
            data = analyze(full, text)
        except (OSError, ValueError) as e:
            infos.append(FileInfo(rel.as_posix(), 0, 0, 0, None, f"could not parse: {type(e).__name__}"))
            continue

        infos.append(
            FileInfo(
                path=rel.as_posix(), lines=text.count("\n") + 1,
                classes=len(data["classes"]), functions=len(data["functions"]), doc=None,
            )
        )
        src = rel.as_posix()
        for record in data["imports"]:
            target = _resolve(record["specifier"], full, repo_root, aliases, by_path)
            add_edge(src, target, record["names"])

    return infos, list(edges.values())
