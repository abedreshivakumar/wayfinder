"""Python, registered as a `Language`: pyright for the driver, the extensions and folders
to skip. Importing this module registers it - `services/container.py` does so once at
startup, the same way `languages/javascript` will register itself once it exists.

The rest of Python's analysis (`analysis/outline.py`, `analysis/imports.py`, the ast-based
data-flow pass) isn't wrapped behind the `Language` interface yet - there's only one
implementation of it, so there's nothing to abstract until a second language actually
needs its own. That's Phase 2's job, once `languages/javascript` has something to plug in.
"""

from __future__ import annotations

from wayfinder.languages import Language, register
from wayfinder.lsp.pyright_driver import PyrightDriver

PYTHON = Language(
    id="python",
    extensions=frozenset({".py"}),
    skipped_dirs=frozenset({"node_modules", "__pycache__", "venv", "env", ".venv", "build", "dist", "site-packages"}),
    make_driver=PyrightDriver,
)

register(PYTHON)
