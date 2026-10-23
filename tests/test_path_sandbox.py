"""The sandbox in guardrails/inputs.py: a request can only reach files of a supported
language inside the repo it names. This is the one guardrail that, if it ever regressed,
would let a request read arbitrary files on the machine - worth pinning down directly.
"""

from __future__ import annotations

import pytest

from wayfinder.core.errors import BadRequest
from wayfinder.guardrails.inputs import resolve_file, resolve_repo


def test_resolve_file_accepts_a_real_file_inside_the_repo(sample_repo):
    repo_root, file_path = resolve_file(str(sample_repo), "app.py")
    assert repo_root == sample_repo.resolve()
    assert file_path == (sample_repo / "app.py").resolve()


def test_resolve_file_refuses_traversal_outside_the_repo(sample_repo):
    with pytest.raises(BadRequest, match="inside the repo"):
        resolve_file(str(sample_repo), "../../etc/passwd")


def test_resolve_file_refuses_an_absolute_path_elsewhere(sample_repo):
    with pytest.raises(BadRequest, match="inside the repo"):
        resolve_file(str(sample_repo), "/etc/passwd")


def test_resolve_file_refuses_an_unsupported_extension(tmp_path):
    (tmp_path / "notes.txt").write_text("not code")
    with pytest.raises(BadRequest, match="not a file of a supported language"):
        resolve_file(str(tmp_path), "notes.txt")


def test_resolve_repo_refuses_a_path_that_is_not_a_directory(sample_repo):
    with pytest.raises(BadRequest, match="not a directory"):
        resolve_repo(str(sample_repo / "app.py"))
