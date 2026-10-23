"""analysis/imports.py: plain `ast` parsing, no pyright - which files import which, and
by which names. Pinned down against the bundled sample repo, where the answer is known:
`dynamic.py` imports `fetch_user` and `process` from `app.py`.
"""

from __future__ import annotations

from wayfinder.analysis.imports import build_import_graph


def test_build_import_graph_finds_the_known_edge(sample_repo):
    infos, edges = build_import_graph(sample_repo, ["app.py", "dynamic.py"])

    by_path = {i.path: i for i in infos}
    assert by_path["app.py"].error is None
    assert by_path["dynamic.py"].error is None

    edge = next((e for e in edges if e.source == "dynamic.py" and e.target == "app.py"), None)
    assert edge is not None, f"expected dynamic.py -> app.py, got {[(e.source, e.target) for e in edges]}"
    assert set(edge.names) == {"fetch_user", "process"}


def test_build_import_graph_has_no_edge_the_other_way(sample_repo):
    _, edges = build_import_graph(sample_repo, ["app.py", "dynamic.py"])
    assert not any(e.source == "app.py" and e.target == "dynamic.py" for e in edges)


def test_build_import_graph_counts_functions_and_classes(sample_repo):
    infos, _ = build_import_graph(sample_repo, ["app.py"])
    app = infos[0]
    assert app.classes == 1  # User
    assert app.functions == 4  # User.__init__, fetch_user, process, handle_login
