"""Which JS/TS files of a repository import which - the JS/TS counterpart of
`analysis/imports.py`. Resolves relative imports (`./foo`, `../bar`) and simple
`tsconfig.json` path aliases to real files; a bare package import (`react`, `lodash`) is
external and isn't resolved to anything in the repo, the same way Python's resolver drops
an import it can't find among the repo's own files.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from wayfinder.analysis.imports import FileInfo, ImportEdge
from wayfinder.languages.javascript.outline import analyze

_MAX_FILE_BYTES = 1_000_000
_MAX_NAMES_SHOWN = 40
_CANDIDATE_EXTENSIONS = (".ts", ".tsx", ".d.ts", ".js", ".jsx")
_INDEX_FILES = tuple(f"index{ext}" for ext in _CANDIDATE_EXTENSIONS)
_MAX_WORKERS = 8  # each analyze() spawns a Node process to load the TS compiler - the
# dominant per-file cost - so parsing several files at once turns a repo's total parse time
# from "every file's cost added up" into roughly "the slowest file's cost".


_TSCONFIG_SKIP = {"node_modules", "vendor", "dist", "build", ".next", "coverage", ".turbo"}


def _aliases_from(tsconfig: Path, repo_root: Path) -> dict[str, list[str]]:
    """`compilerOptions.paths` from one `tsconfig.json`, resolved against its own
    `baseUrl` - `{"@app/*": ["src/app/*"]}` becomes `{"@app/": ["src/app/"]}`. Missing,
    malformed, or using project-reference `extends` chains: treated as no aliases - those
    imports just end up external instead, same as a package Wayfinder doesn't resolve."""
    try:
        options = json.loads(tsconfig.read_text(encoding="utf-8", errors="replace")).get("compilerOptions", {})
    except ValueError:
        return {}
    base = (tsconfig.parent / options.get("baseUrl", ".")).resolve()
    out: dict[str, list[str]] = {}
    for pattern, targets in (options.get("paths") or {}).items():
        key = pattern.removesuffix("*")
        resolved = [(base / t.removesuffix("*")) for t in targets if isinstance(t, str)]
        out[key] = [str(r.relative_to(repo_root)) for r in resolved if r.is_relative_to(repo_root)]
    return out


def _find_tsconfigs(repo_root: Path) -> dict[Path, dict[str, list[str]]]:
    """Every `tsconfig.json` in the repo, each with its own path aliases - a monorepo
    commonly has one per package (`plugins/memory/tsconfig.json`, not just one at the
    root), and each package's imports should resolve against its own, nearest one."""
    out: dict[Path, dict[str, list[str]]] = {}
    for tsconfig in repo_root.rglob("tsconfig.json"):
        if any(part in _TSCONFIG_SKIP for part in tsconfig.relative_to(repo_root).parts):
            continue
        out[tsconfig.parent] = _aliases_from(tsconfig, repo_root)
    return out


def _nearest_aliases(from_file: Path, by_dir: dict[Path, dict[str, list[str]]]) -> dict[str, list[str]]:
    for folder in (from_file.parent, *from_file.parent.parents):
        if folder in by_dir:
            return by_dir[folder]
    return {}


def _resolve(specifier: str, from_file: Path, repo_root: Path, aliases: dict[str, list[str]], by_path: set[str]) -> str | None:
    if specifier.startswith("."):
        base = (from_file.parent / specifier).resolve()
    else:
        target_dirs = next((targets for prefix, targets in aliases.items() if specifier.startswith(prefix)), None)
        if target_dirs is None:
            return None  # a bare package import (react, lodash, ...): external, not ours to resolve
        rest = specifier[len(next(p for p in aliases if specifier.startswith(p))):]
        base = (repo_root / target_dirs[0] / rest).resolve()

    # `./foo` (no extension) and `./foo.js` (the standard ESM convention of writing the
    # compiled .js extension even in a .ts source file, so the real file is `foo.ts`) both
    # need every candidate extension tried against the extensionless stem - `base.with_suffix`
    # REPLACES an existing suffix, so naively appending onto ".js" produced "foo.js.ts" and
    # never matched anything.
    stem = base.with_suffix("") if base.suffix in _CANDIDATE_EXTENSIONS else base
    for candidate in (base, *(stem.with_suffix(ext) for ext in _CANDIDATE_EXTENSIONS), *(base / name for name in _INDEX_FILES)):
        try:
            rel = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel in by_path:
            return rel
    return None


def _parse_one(repo_root: Path, rel: Path) -> tuple[str | None, dict | None, str | None]:
    """(text, parsed data, error) for one file - the part worth running off the main thread,
    since `analyze()` here is a blocking Node subprocess call."""
    full = repo_root / rel
    try:
        if full.stat().st_size > _MAX_FILE_BYTES:
            return None, None, "file too large to map"
        text = full.read_text(encoding="utf-8", errors="replace")
        data = analyze(full, text)
    except (OSError, ValueError) as e:
        return None, None, f"could not parse: {type(e).__name__}"
    return text, data, None


def build_import_graph(repo_root: Path, files: list[str]) -> tuple[list[FileInfo], list[ImportEdge]]:
    rels = [Path(f) for f in files]
    by_path = {r.as_posix() for r in rels}
    tsconfigs = _find_tsconfigs(repo_root)

    # The slow part - one Node subprocess per file - runs for every file at once instead of
    # one at a time; `map` keeps the results in the same order as `rels` regardless of which
    # subprocess finishes first, so everything below stays deterministic.
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(rels)) or 1) as pool:
        parsed = list(pool.map(lambda rel: _parse_one(repo_root, rel), rels))

    infos: list[FileInfo] = []
    edges: dict[tuple[str, str], ImportEdge] = {}

    def add_edge(source: str, target: str | None, names: list[str]) -> None:
        if target is None or target == source:
            return
        key = (source, target)
        old = edges.get(key)
        all_names = (old.names if old else []) + [n for n in names if n and n != "*"]
        edges[key] = ImportEdge(source, target, all_names[:_MAX_NAMES_SHOWN], (old.weight if old else 0) + 1)

    for rel, (text, data, error) in zip(rels, parsed):
        if error is not None:
            infos.append(FileInfo(rel.as_posix(), 0, 0, 0, None, error))
            continue

        infos.append(
            FileInfo(
                path=rel.as_posix(), lines=text.count("\n") + 1,
                classes=len(data["classes"]), functions=len(data["functions"]), doc=None,
            )
        )
        src = rel.as_posix()
        full = repo_root / rel
        aliases = _nearest_aliases(full, tsconfigs)
        for record in data["imports"]:
            target = _resolve(record["specifier"], full, repo_root, aliases, by_path)
            add_edge(src, target, record["names"])

    return infos, list(edges.values())
