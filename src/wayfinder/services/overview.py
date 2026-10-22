"""The two big pictures: how a repository's files connect, and how one file works inside.

Both are assembled from smaller pieces that already exist - the import graph for the
first, the per-function call analysis for the second - and both come with a plain-language
summary built from those facts alone, so they read well with no model and no network.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from wayfinder.analysis.structure import build_structure
from wayfinder.languages import build_import_graph, outline_for
from wayfinder.core.errors import WayfinderError
from wayfinder.guardrails import inputs
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext

_METHOD, _FUNCTION, _CLASS = 6, 12, 5


def _listing(names: list[str], limit: int = 6) -> str:
    shown = ", ".join(f"`{n}`" for n in names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


class OverviewService:
    def __init__(self, ctx: ServiceContext, analysis: AnalysisService) -> None:
        self._ctx = ctx
        self._analysis = analysis

    def repo_map(self, repo: str) -> dict[str, Any]:
        """Every Python file and which files import which."""
        repo_root = inputs.resolve_repo(repo)
        files = self._analysis.list_files(repo)
        infos, edges = build_import_graph(repo_root, files)
        return {
            "files": [asdict(i) for i in infos],
            "edges": [asdict(e) for e in edges],
            "truncated": len(files) >= self._ctx.settings.limits.max_listed_files,
        }

    def structure(self, repo: str) -> dict[str, Any]:
        """Modules, layers, module links, files with their functions and schemas, and a
        reading order: everything the overview screens need, in one response."""
        repo_root = inputs.resolve_repo(repo)
        files = self._analysis.list_files(repo)
        result = build_structure(repo_root, files)
        result["truncated"] = len(files) >= self._ctx.settings.limits.max_listed_files
        result["repo"] = repo_root.name
        return result

    def file_graph(self, repo: str, file: str) -> dict[str, Any]:
        """The functions in one file and the calls between them (and out to other files of
        the repo), with the data flowing along those calls."""
        repo_root, file_path = inputs.resolve_file(repo, file)
        limits = self._ctx.settings.limits
        symbols = self._analysis.list_symbols(repo, file)
        # Classes are not walked themselves: their methods are, and a class shows up as a
        # node when something instantiates it.
        roots = [s for s in symbols if s.kind in (_METHOD, _FUNCTION)]
        truncated = len(roots) > limits.max_file_functions
        roots = roots[: limits.max_file_functions]
        rel_file = file_path.relative_to(repo_root).as_posix()

        nodes: dict[str, dict[str, Any]] = {}
        edges: set[tuple[str, str]] = set()
        labels: dict[tuple[str, str, int], dict[str, Any]] = {}
        links: list[dict[str, Any]] = []
        seen_links: set[tuple] = set()
        qualified = {f"#{s.line - 1}:{s.col - 1}": s.qualified_name for s in symbols}

        def add_node(n: dict[str, Any]) -> None:
            # `n["file"]` is a raw `file://` URI, percent-encoded by pyright (a space in a
            # folder name comes back as `%20`) - naively stripping the scheme instead of
            # decoding it left every node's path mismatched against `repo_root` whenever the
            # repo lived under a path with spaces (or any other reserved character), so every
            # node looked "external" and got silently dropped, emptying the whole graph.
            path = Path(unquote(urlparse(n["file"]).path))
            try:
                rel = path.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                return  # a library or the standard library: not part of this repo's picture
            in_file = path.resolve() == file_path
            suffix = "#" + n["id"].rpartition("#")[2]
            nodes.setdefault(
                n["id"],
                {**{k: n[k] for k in ("id", "name", "kind", "file", "start_line", "start_col")},
                 "label": qualified.get(suffix, n["name"]) if in_file else n["name"],
                 "rel_file": rel, "in_file": in_file},
            )

        for s in roots:
            try:
                dfg = self._analysis.analyze(repo, file, line=s.line, col=s.col, hops=1, direction="outgoing").to_dict()
            except WayfinderError:
                continue  # one function pyright cannot place must not lose the whole file
            for n in dfg["nodes"]:
                add_node(n)
            for e in dfg["edges"]:  # only the calls this function makes; both ends must be in the repo
                if e["from_id"] == dfg["root_id"] and e["from_id"] in nodes and e["to_id"] in nodes:
                    edges.add((e["from_id"], e["to_id"]))
            for c in dfg["call_labels"]:
                if c["caller_id"] in nodes and c["callee_id"] in nodes:
                    labels[(c["caller_id"], c["callee_id"], c["line"])] = c
            for f in dfg["flow_links"]:
                key = (f["caller_id"], f["var"], f["producer"], f["consumer"])
                if f["caller_id"] in nodes and key not in seen_links:
                    seen_links.add(key)
                    links.append(f)

        try:
            info = outline_for(file_path, file_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, ValueError):
            info = None
        if info:
            by_line = {f.line: f for f in info.functions}
            for n in nodes.values():
                f = by_line.get(n["start_line"]) if n["in_file"] else None
                if f is None and n["in_file"]:  # a decorated def: pyright's line is the name's, ast's the first decorator's
                    f = next((g for g in info.functions if g.name == n["name"] and abs(g.line - n["start_line"]) <= 6), None)
                if f:
                    n["params"] = [asdict(p) for p in f.params]
                    n["returns"] = f.returns
                    n["doc"] = f.doc

        result_edges = [{"from_id": a, "to_id": b} for a, b in sorted(edges)]
        return {
            "schemas": [asdict(x) for x in info.schemas] if info else [],
            "file": rel_file,
            "nodes": list(nodes.values()),
            "edges": result_edges,
            "call_labels": list(labels.values()),
            "flow_links": links,
            "summary": self._summary(repo, repo_root, rel_file, symbols, nodes, edges),
            "truncated": truncated,
        }

    def _summary(
        self,
        repo: str,
        repo_root: Path,
        rel_file: str,
        symbols: list[Any],
        nodes: dict[str, dict[str, Any]],
        edges: set[tuple[str, str]],
    ) -> dict[str, Any]:
        repo_map = self.repo_map(repo)
        info = next((f for f in repo_map["files"] if f["path"] == rel_file), None) or {}
        imports = sorted({e["target"] for e in repo_map["edges"] if e["source"] == rel_file})
        imported_by = sorted({e["source"] for e in repo_map["edges"] if e["target"] == rel_file})

        own = {i: n for i, n in nodes.items() if n["in_file"]}
        called_here = {b for a, b in edges if a in own and b in own}
        callables = [n for n in own.values() if n["kind"] in (_METHOD, _FUNCTION)]
        entry_points = sorted(
            n["label"] for n in callables if n["id"] not in called_here and not n["name"].startswith("__")
        )
        classes = [s.qualified_name for s in symbols if s.kind == _CLASS]
        functions = [s.qualified_name for s in symbols if s.kind in (_METHOD, _FUNCTION)]

        out: dict[str, list[str]] = {}
        for a, b in sorted(edges):
            if a in own and b in nodes:
                out.setdefault(nodes[a]["label"], []).append(nodes[b]["label"])

        parts = [f"`{Path(rel_file).name}` has {info.get('lines', '?')} lines"]
        counts = []
        if classes:
            counts.append(f"{len(classes)} class{'es' if len(classes) != 1 else ''} ({_listing(classes)})")
        if functions:
            counts.append(f"{len(functions)} function{'s' if len(functions) != 1 else ''} or method{'s' if len(functions) != 1 else ''}")
        parts[0] += (" and defines " + " and ".join(counts)) if counts else " and defines no functions or classes"
        text = [parts[0] + "."]
        if info.get("doc"):
            text.append(f"Its docstring says: \"{info['doc']}\"")
        if entry_points and callables:
            text.append(f"Nothing else in this file calls {_listing(entry_points)}, so {'it is' if len(entry_points) == 1 else 'they are'} where a reader would start (or where other files come in).")
        for caller, callees in list(out.items())[:8]:
            text.append(f"`{caller}` calls {_listing(sorted(set(callees)))}.")
        if imports:
            text.append(f"It imports from {_listing([Path(i).name for i in imports])}.")
        if imported_by:
            text.append(f"It is imported by {_listing([Path(i).name for i in imported_by])}.")
        elif imports or callables:
            text.append("No other file in the repo imports it, so it is probably an entry point or a script.")
        return {
            "lines": info.get("lines"),
            "doc": info.get("doc"),
            "classes": classes,
            "functions": functions,
            "entry_points": entry_points,
            "imports": imports,
            "imported_by": imported_by,
            "text": " ".join(text),
        }
