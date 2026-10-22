"""Python, registered as a `Language`: pyright for the driver, `ast` for the outline and
import graph, the extensions and folders to skip. Importing this module registers it -
`services/container.py` does so once at startup, the same way `languages/javascript` will
register itself once it exists.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.analysis.imports import build_import_graph
from wayfinder.analysis.outline import Outline, outline
from wayfinder.languages import Language, register
from wayfinder.lsp.pyright_driver import PyrightDriver


def _outline(path: Path, source: str) -> Outline:
    # Python's ast doesn't need to know the path - every .py file is parsed the same way,
    # unlike JS/TS where the extension picks .ts vs .tsx vs .js parsing.
    return outline(source)


PYTHON = Language(
    id="python",
    extensions=frozenset({".py"}),
    skipped_dirs=frozenset({"node_modules", "__pycache__", "venv", "env", ".venv", "build", "dist", "site-packages"}),
    make_driver=PyrightDriver,
    outline=_outline,
    build_imports=build_import_graph,
)

register(PYTHON)
