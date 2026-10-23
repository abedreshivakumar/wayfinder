"""The call graph in analysis/call_graph.py, over a real pyright-langserver - the part of
the pipeline that turns "code" into "verified facts" instead of a guess. Pinned down
against the bundled sample repo's known chain: handle_login calls fetch_user and process,
and fetch_user is in turn called from both app.py and dynamic.py.

Skipped automatically if pyright-langserver isn't on PATH (see the `integration` marker in
pyproject.toml) rather than failing - this is the one test here that needs a real subprocess.
"""

from __future__ import annotations

import shutil

import pytest

from wayfinder.analysis.call_graph import build_call_graph
from wayfinder.lsp.pyright_driver import PyrightDriver

pytestmark = pytest.mark.integration

if shutil.which("pyright-langserver") is None:
    pytest.skip("pyright-langserver not on PATH", allow_module_level=True)


@pytest.fixture
def driver(sample_repo):
    d = PyrightDriver(sample_repo)
    d.start()
    yield d
    d.stop()


def test_handle_login_calls_fetch_user_and_process(sample_repo, driver):
    # handle_login is defined on line 15 (1-indexed), starting at column 5 ("def ").
    graph = build_call_graph(driver, sample_repo / "app.py", line=15, col=5, hops=1)

    callee_names = {graph.nodes[e.to_id].name for e in graph.edges if e.direction == "outgoing"}
    assert callee_names == {"fetch_user", "process"}


def test_fetch_user_callers_include_handle_login_and_dispatch(sample_repo, driver):
    # fetch_user is defined on line 7, starting at column 5. Both app.py's handle_login
    # and dynamic.py's dispatch call it, since the driver's repo root covers both files.
    graph = build_call_graph(driver, sample_repo / "app.py", line=7, col=5, hops=1)

    caller_names = {graph.nodes[e.from_id].name for e in graph.edges if e.direction == "incoming"}
    assert caller_names == {"handle_login", "dispatch", "never_called"}
