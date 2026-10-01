"""Runs a repository's code and records which of its functions call which.

This file is NOT imported by Wayfinder. It is run as a separate Python process by
collect.py, so the repository's code never executes inside the server. It uses only the
standard library because it may run under an interpreter that has no Wayfinder installed.

Input: one JSON object in the file named by argv[1]. Output: a JSON file named by argv[2],
written when the run ends - or when the time limit is reached, so a run that never finishes
still reports the calls it made.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
import threading
import traceback

_SKIP_DIRS = ("/site-packages/", "/.venv/", "/venv/", "/node_modules/", "/__pycache__/")
_INLINE = {"<listcomp>", "<dictcomp>", "<setcomp>", "<genexpr>", "<lambda>"}  # belong to the enclosing function


def main() -> None:
    spec = json.load(open(sys.argv[1]))
    out_path = sys.argv[2]
    repo = os.path.realpath(spec["repo"]) + os.sep
    edges: dict[tuple, int] = {}
    state = {"truncated": False, "error": None, "returned": None, "dumped": False}
    lock = threading.Lock()

    own_file = os.path.realpath(__file__)

    def in_repo(filename: str) -> bool:
        if filename.startswith("<"):  # <frozen importlib...>, <string>: not files, and realpath would put them in the repo
            return False
        real = os.path.realpath(filename)
        return real.startswith(repo) and not any(d in real for d in _SKIP_DIRS)

    def describe(frame):
        code = frame.f_code
        while code.co_name in _INLINE and frame.f_back is not None:  # attribute to the enclosing function
            frame = frame.f_back
            code = frame.f_code
        name = getattr(code, "co_qualname", code.co_name)
        return (os.path.realpath(code.co_filename), code.co_name, name, code.co_firstlineno)

    def profile(frame, event, arg):
        if event != "call" or frame.f_code.co_name in _INLINE or not in_repo(frame.f_code.co_filename):
            return
        caller = frame.f_back
        if caller is None or frame.f_code.co_name == "<module>":  # importing a module is not a call to it
            return
        if "__qualname__" in frame.f_locals:  # a class body running, not a function call
            return
        if os.path.realpath(caller.f_code.co_filename) == own_file:  # this runner starting the entry point
            return
        key = (describe(caller), describe(frame), in_repo(caller.f_code.co_filename))
        with lock:
            if key in edges:
                edges[key] += 1
            elif len(edges) < spec["max_edges"]:
                edges[key] = 1
            else:
                state["truncated"] = True

    def dump() -> None:
        with lock:
            if state["dumped"]:
                return
            state["dumped"] = True
            payload = {
                "edges": [
                    {"caller": list(c), "callee": list(e), "caller_in_repo": inside, "count": n}
                    for (c, e, inside), n in edges.items()
                ],
                "truncated": state["truncated"],
                "error": state["error"],
                "returned": state["returned"],
            }
            with open(out_path, "w") as f:
                json.dump(payload, f)

    def on_timeout() -> None:
        state["error"] = f"stopped after {spec['timeout']} seconds"
        sys.setprofile(None)
        dump()
        os._exit(124)

    watchdog = threading.Timer(spec["timeout"], on_timeout)
    watchdog.daemon = True
    watchdog.start()

    sys.path.insert(0, os.path.dirname(spec["entry_file"]))
    sys.path.insert(0, repo.rstrip(os.sep))
    sys.setprofile(profile)
    threading.setprofile(profile)
    try:
        if spec.get("function"):
            module = runpy.run_path(spec["entry_file"], run_name="wayfinder_entry")
            target = module[spec["function"]]
            result = target(*spec.get("args", []), **spec.get("kwargs", {}))
            state["returned"] = repr(result)[:300]
        else:
            runpy.run_path(spec["entry_file"], run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            state["error"] = f"the program exited with status {e.code}"
    except BaseException as e:  # noqa: BLE001 - whatever the traced code raises is a result, not our failure
        tb = traceback.extract_tb(e.__traceback__)
        where = f" at {os.path.basename(tb[-1].filename)}:{tb[-1].lineno}" if tb else ""
        state["error"] = f"{type(e).__name__}: {e}{where}"[:500]
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
        watchdog.cancel()
        dump()


if __name__ == "__main__":
    main()
