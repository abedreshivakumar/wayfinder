"""Run the repository's code in a separate process and collect the calls it made.

The process gets a scrubbed environment (no API keys or tokens, a throwaway home
directory), a hard time limit and capped output. That limits accidents; it is not a
sandbox - the code can still read your files and use the network - which is why tracing
is opt-in (see Settings.allow_trace).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RUNNER = Path(__file__).with_name("_runner.py")
_OUTPUT_CAP = 2_000  # characters of the program's own output kept


@dataclass(frozen=True)
class RawTrace:
    # each: {caller: [file, name, qualname, line], callee: [...], caller_in_repo, count}
    edges: list[dict[str, Any]]
    truncated: bool  # more distinct calls happened than max_edges allowed
    error: str | None  # the traced code raised, exited non-zero, or hit the time limit
    returned: str | None  # repr of the function's return value (function mode only)
    output: str  # what the program printed (stdout then stderr), capped


def run_trace(
    repo_root: Path,
    entry_file: Path,
    function: str | None,
    args: list[Any],
    kwargs: dict[str, Any],
    *,
    timeout: int,
    max_edges: int,
) -> RawTrace:
    with tempfile.TemporaryDirectory(prefix="wayfinder-trace-") as tmp:
        tmp_dir = Path(tmp)
        spec_path, result_path = tmp_dir / "spec.json", tmp_dir / "result.json"
        spec_path.write_text(
            json.dumps(
                {
                    "repo": str(repo_root),
                    "entry_file": str(entry_file),
                    "function": function,
                    "args": args,
                    "kwargs": kwargs,
                    "timeout": timeout,
                    "max_edges": max_edges,
                }
            )
        )
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(tmp_dir),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        out_path, err_path = tmp_dir / "stdout.txt", tmp_dir / "stderr.txt"
        timed_out = False
        with out_path.open("wb") as out, err_path.open("wb") as err:
            try:
                subprocess.run(
                    [sys.executable, "-I", str(_RUNNER), str(spec_path), str(result_path)],
                    cwd=repo_root,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    timeout=timeout + 5,  # the runner stops itself at `timeout`; this is the backstop
                )
            except subprocess.TimeoutExpired:
                timed_out = True

        output = (_read(out_path) + _read(err_path))[:_OUTPUT_CAP]
        if not result_path.is_file():
            reason = "the run did not finish in time" if timed_out else "the traced program crashed before reporting"
            return RawTrace([], False, reason, None, output)
        data = json.loads(result_path.read_text())
        return RawTrace(data["edges"], data["truncated"], data["error"], data["returned"], output)


def _read(path: Path) -> str:
    with path.open("rb") as f:
        return f.read(_OUTPUT_CAP).decode("utf-8", "replace")
