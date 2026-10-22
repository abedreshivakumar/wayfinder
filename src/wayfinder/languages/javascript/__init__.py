"""JavaScript/TypeScript, registered as a `Language`: `typescript-language-server` for the
driver (the TypeScript compiler API's own call-hierarchy support, over LSP - same transport
pyright uses), the Node-based `analyze.js` for outline and import resolution.
"""

from __future__ import annotations

from wayfinder.languages import Language, register
from wayfinder.languages.javascript.imports import build_import_graph
from wayfinder.languages.javascript.outline import outline
from wayfinder.lsp.tsserver_driver import TSServerDriver

JAVASCRIPT = Language(
    id="javascript",
    extensions=frozenset({".js", ".jsx", ".ts", ".tsx"}),
    skipped_dirs=frozenset({"node_modules", "dist", "build", ".next", "coverage", ".turbo"}),
    make_driver=TSServerDriver,
    outline=outline,
    build_imports=build_import_graph,
)

register(JAVASCRIPT)
