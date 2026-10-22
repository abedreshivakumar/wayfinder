"""JavaScript/TypeScript support - outline and import resolution are built (this is Phase
2 of the JS build-out plan); the call graph is not (Phase 1, still pending): there's no
`TSServerDriver` yet, so asking for callers/callees of a JS/TS function fails with a clear
message instead of a crash. The repo map, folder/module/layer structure, and schema
detection (interfaces, Zod schemas, enums) all work today without one.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.core.errors import NotConfigured
from wayfinder.languages import Language, register
from wayfinder.languages.javascript.imports import build_import_graph
from wayfinder.languages.javascript.outline import outline


def _no_driver_yet(repo_root: Path):
    raise NotConfigured(
        "JavaScript/TypeScript call graphs aren't built yet - only the repo map, file "
        "structure, and schema detection are. Who calls a function, what it calls, and its "
        "data flow need a typescript-language-server driver that doesn't exist yet."
    )


JAVASCRIPT = Language(
    id="javascript",
    extensions=frozenset({".js", ".jsx", ".ts", ".tsx"}),
    skipped_dirs=frozenset({"node_modules", "dist", "build", ".next", "coverage", ".turbo"}),
    make_driver=_no_driver_yet,
    outline=outline,
    build_imports=build_import_graph,
)

register(JAVASCRIPT)
