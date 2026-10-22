"""What a JS/TS file defines, via a Node subprocess running `tools/analyze.js` (the
TypeScript compiler API) - the JS/TS counterpart of `analysis/outline.py`'s `ast` pass.

Returns the same shared dataclasses (`Outline`, `FunctionInfo`, `SchemaInfo`, `Param`) that
Python's outline uses, so nothing downstream (the UI, the file-explainer prompt, the
reading-order logic) has to know or care which language produced them.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from wayfinder.analysis.outline import FunctionInfo, Outline, Param, SchemaInfo
from wayfinder.core.errors import UpstreamError

_SCRIPT = Path(__file__).with_name("tools") / "analyze.js"
_TIMEOUT_SECONDS = 15


def analyze(path: Path, source: str) -> dict:
    """The analyzer's full parsed JSON - functions, classes, schemas, imports,
    has_main_guard - for callers (namely `imports.py`) that need more than one view of it,
    so a file is only ever parsed once."""
    return _run(path, source)


def _run(path: Path, source: str) -> dict:
    # `analyze.js` reads from disk (not stdin) so the TypeScript compiler can use the real
    # extension to pick .ts/.tsx/.js/.jsx parsing. When `path` is a real file already on
    # disk with the right extension, it's read directly; a caller handing in text that
    # hasn't been saved yet (there isn't one today, but `outline()`'s signature allows it)
    # gets a same-suffix temp file instead, so the extension is still right.
    if path.is_file():
        target = path
        cleanup = None
    else:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=path.suffix or ".js", delete=False, encoding="utf-8")
        tmp.write(source)
        tmp.close()
        target = Path(tmp.name)
        cleanup = target

    try:
        result = subprocess.run(
            ["node", str(_SCRIPT), str(target)],
            capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UpstreamError(f"could not run the JS/TS analyzer: {e}") from e
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)

    if result.returncode != 0:
        raise UpstreamError(f"the JS/TS analyzer failed on {path.name}: {result.stderr.strip()[:300]}")
    try:
        return json.loads(result.stdout)
    except ValueError as e:
        raise UpstreamError(f"the JS/TS analyzer returned something that wasn't JSON for {path.name}") from e


def outline(path: Path, source: str) -> Outline:
    data = analyze(path, source)
    functions = [
        FunctionInfo(
            qualname=f["qualname"], name=f["name"], line=f["line"],
            params=[Param(p["name"], p["type"]) for p in f["params"]],
            returns=f["returns"], doc=f["doc"], is_async=f["is_async"],
        )
        for f in data["functions"]
    ]
    schemas = [
        SchemaInfo(
            name=s["name"], kind=s["kind"], line=s["line"],
            fields=[Param(p["name"], p["type"]) for p in s["fields"]], doc=s["doc"],
        )
        for s in data["schemas"]
    ]
    return Outline(functions=functions, classes=data["classes"], schemas=schemas, has_main_guard=data["has_main_guard"])

