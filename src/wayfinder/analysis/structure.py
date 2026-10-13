"""The shape of a repository as a newcomer needs it: modules, the layer each sits in, how
they depend on each other, and an order to read the files in.

Built only from import lines and file outlines (no pyright, no model), so it is fast and
the same for every repo. The rules adapt to the repo: folders become modules; a repo with
everything in one folder is split by which files import each other; a tiny repo skips
modules and shows its files directly.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wayfinder.analysis.imports import FileInfo, ImportEdge, build_import_graph
from wayfinder.analysis.outline import Outline, outline

# Files a newcomer skips on a first read. The UI can still show them on request.
_NOISE = [
    re.compile(p, re.I)
    for p in (
        r"(^|/)tests?(/|$)", r"(^|/)test_[^/]+\.py$", r"[^/]+_test\.py$", r"(^|/)conftest\.py$",
        r"(^|/)__init__\.py$", r"(^|/)(migrations|fixtures|scripts|examples|docs|benchmarks?)(/|$)",
        r"(^|/)setup\.py$", r"(^|/)conf\.py$", r"(^|/)noxfile\.py$",
    )
]
_ENTRY_NAMES = {"main.py", "__main__.py", "cli.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py", "run.py"}
_DATA_NAMES = {"schema.py", "schemas.py", "models.py", "model.py", "types.py", "dto.py", "entities.py", "domain.py"}
_TINY_REPO = 6  # this many core files or fewer: show files, not modules
_READING_PATH = 8


def is_noise(path: str) -> bool:
    return any(p.search(path) for p in _NOISE)


@dataclass
class FileEntry:
    path: str
    module: str
    layer: str  # entry | core | data
    noise: bool
    lines: int
    doc: str | None
    error: str | None
    functions: list[dict[str, Any]]
    classes: list[str]
    schemas: list[dict[str, Any]]


def _dir(path: str) -> str:
    return path.rpartition("/")[0] or "(root)"


def _components(files: list[str], edges: list[ImportEdge]) -> list[list[str]]:
    """Groups of files that import each other, directly or through others."""
    neighbours: dict[str, set[str]] = defaultdict(set)
    inside = set(files)
    for e in edges:
        if e.source in inside and e.target in inside:
            neighbours[e.source].add(e.target)
            neighbours[e.target].add(e.source)
    seen: set[str] = set()
    groups: list[list[str]] = []
    for f in files:
        if f in seen:
            continue
        group, queue = [], deque([f])
        seen.add(f)
        while queue:
            cur = queue.popleft()
            group.append(cur)
            for n in neighbours[cur] - seen:
                seen.add(n)
                queue.append(n)
        groups.append(sorted(group))
    return groups


def _through_packages(edges: list[ImportEdge]) -> tuple[list[ImportEdge], list[tuple[str, str, int]]]:
    """Imports of a package (its __init__.py) redirected to the files that really define
    the names, when __init__.py only re-exports them. Returns the rewritten edges, plus
    (importer, package folder, weight) for names the package defines itself."""
    reexports: dict[str, dict[str, str]] = defaultdict(dict)
    for e in edges:
        if e.source.endswith("__init__.py"):
            for n in e.names:
                reexports[e.source][n] = e.target
    out: list[ImportEdge] = []
    to_package: list[tuple[str, str, int]] = []
    for e in edges:
        table = reexports.get(e.target)
        if not e.target.endswith("__init__.py") or e.source.endswith("__init__.py") or not table:
            out.append(e)
            continue
        targets: dict[str, list[str]] = defaultdict(list)
        unresolved = 0
        for n in e.names or [""]:
            if n in table and table[n] != e.source:
                targets[table[n]].append(n)
            else:
                unresolved += 1
        out += [ImportEdge(e.source, t, ns, len(ns)) for t, ns in targets.items()]
        if unresolved:
            to_package.append((e.source, _dir(e.target), unresolved))
    return out, to_package


def build_structure(repo_root: Path, paths: list[str]) -> dict[str, Any]:
    infos, edges = build_import_graph(repo_root, paths)
    info_by_path: dict[str, FileInfo] = {i.path: i for i in infos}

    outlines: dict[str, Outline] = {}
    for i in infos:
        if i.error:
            continue
        try:
            outlines[i.path] = outline((repo_root / i.path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, ValueError):
            pass

    core = [i.path for i in infos if not is_noise(i.path) and not i.error]
    core_set = set(core)
    edges, package_edges = _through_packages(edges)
    core_edges = [e for e in edges if e.source in core_set and e.target in core_set]
    any_importers: dict[str, set[str]] = defaultdict(set)  # including tests and scripts
    for e in core_edges + [e for e in edges if e.source not in core_set]:
        any_importers[e.target].add(e.source)
    importers: dict[str, set[str]] = defaultdict(set)
    imports: dict[str, list[str]] = defaultdict(list)
    for e in core_edges:
        importers[e.target].add(e.source)
        imports[e.source].append(e.target)

    # --- modules ---
    module_of: dict[str, str] = {p: _dir(p) for p in core}
    if len(set(module_of.values())) == 1 and len(core) > 10:
        # Everything in one folder: group it by which files belong together instead.
        groups = [g for g in _components(core, core_edges) if len(g) > 1]
        if len(groups) > 1:
            module_of = {p: "(other)" for p in core}
            for g in groups:
                hub = max(g, key=lambda p: (len(importers[p]), p))
                for p in g:
                    module_of[p] = f"{Path(hub).stem} group"
    modules: dict[str, list[str]] = defaultdict(list)
    for p in core:
        modules[module_of[p]].append(p)
    mode = "files" if len(core) <= _TINY_REPO or len(modules) <= 1 else "modules"

    # --- layers ---
    def file_layer(p: str) -> str:
        o = outlines.get(p)
        top_functions = [f for f in o.functions if "." not in f.qualname] if o else []
        if o and o.schemas and (len(o.schemas) >= len(top_functions) or Path(p).name in _DATA_NAMES):
            return "data"
        if Path(p).name in _ENTRY_NAMES or (o and o.has_main_guard) or (not any_importers[p] and imports[p]):
            return "entry"
        return "core"

    layer_of = {p: file_layer(p) for p in core}

    def runnable(p: str) -> bool:  # started directly, not just unused
        o = outlines.get(p)
        return Path(p).name in _ENTRY_NAMES or bool(o and o.has_main_guard)

    module_edges: Counter[tuple[str, str]] = Counter()
    for e in core_edges:
        a, b = module_of[e.source], module_of[e.target]
        if a != b:
            module_edges[(a, b)] += e.weight
    for source, package, weight in package_edges:  # `import pkg` itself: counts toward pkg's module
        if source in core_set and package in modules and module_of[source] != package:
            module_edges[(module_of[source], package)] += weight
    module_importers: dict[str, set[str]] = defaultdict(set)
    for a, b in module_edges:
        module_importers[b].add(a)

    def module_layer(key: str) -> str:
        counts = Counter(layer_of[p] for p in modules[key])
        if counts["data"] * 2 >= len(modules[key]):
            return "data"
        if counts["entry"] * 2 >= len(modules[key]) or any(runnable(p) for p in modules[key]):
            return "entry"
        return "core"

    names = Counter(Path(k).name for k in modules)
    module_list = []
    for key, files in modules.items():
        short = Path(key).name if key not in ("(root)", "(other)") else key
        degree = sum(w for (a, b), w in module_edges.items() if key in (a, b))
        module_list.append(
            {
                "key": key,
                # Two folders both called "utils" are told apart by their parent.
                "name": short if names[Path(key).name] == 1 else "/".join(Path(key).parts[-2:]),
                "layer": module_layer(key),
                "files": sorted(files),
                "rank": len(files) + 2 * degree,
            }
        )
    module_list.sort(key=lambda m: -m["rank"])

    # --- reading order: a tour, not a list. One file per folder (its siblings usually work the
    # same way), following what the main entry point uses, deepest-shared code last. ---
    entries = sorted(
        (p for p in core if layer_of[p] == "entry"), key=lambda p: (not runnable(p), -len(imports[p]), p)
    ) or sorted(core, key=lambda p: -len(importers[p]))[:1]
    order: list[str] = []
    similar: dict[str, int] = {}
    folders_done: set[str] = set()

    def richest(paths: list[str]) -> str:  # the sibling that shows the most of how things work
        return max(paths, key=lambda q: (len(imports[q]), outlines[q].functions.__len__() if q in outlines else 0, q))

    def visit(p: str) -> None:
        order.append(p)
        folders_done.add(_dir(p))

    queue = deque([entries[0]])
    visit(entries[0])
    while queue and len(order) < _READING_PATH:
        cur = queue.popleft()
        by_folder: dict[str, list[str]] = defaultdict(list)
        for q in set(imports[cur]):
            if q not in order and _dir(q) not in folders_done:
                by_folder[_dir(q)].append(q)
        # Folders most of the repo depends on go last: they are foundations, read after the flow.
        for folder in sorted(by_folder, key=lambda f: (sum(len(importers[q]) for q in by_folder[f]), f)):
            if len(order) >= _READING_PATH:
                break
            pick = richest(by_folder[folder])
            similar[pick] = len(by_folder[folder]) - 1
            visit(pick)
            queue.append(pick)
    # Finish with the most depended-on files not yet covered: config, models, the database.
    for p in sorted(core, key=lambda q: -len(importers[q])):
        if len(order) >= _READING_PATH or len(importers[p]) < 2:
            break
        if p not in order and _dir(p) not in folders_done:
            visit(p)

    files_out = []
    for i in infos:
        o = outlines.get(i.path)
        files_out.append(
            asdict(
                FileEntry(
                    path=i.path,
                    module=module_of.get(i.path, _dir(i.path)),
                    layer=layer_of.get(i.path, "core"),
                    noise=i.path not in core_set,
                    lines=i.lines,
                    doc=i.doc,
                    error=i.error,
                    functions=[asdict(f) for f in o.functions] if o else [],
                    classes=o.classes if o else [],
                    schemas=[asdict(s) for s in o.schemas] if o else [],
                )
            )
        )
    return {
        "mode": mode,
        "modules": module_list,
        "module_edges": [{"source": a, "target": b, "weight": w} for (a, b), w in module_edges.items()],
        "files": files_out,
        "file_edges": [asdict(e) for e in edges],
        "reading_order": order,
        "reading_similar": {p: n for p, n in similar.items() if n > 0},  # siblings the tour skipped
        "hidden": len(infos) - len(core),
    }
