from __future__ import annotations

from pathlib import Path

import pytest

# Registering a language is a side effect of importing its package (see
# services/container.py); the real app does this at startup, so tests have to do it too
# or `all_extensions()` comes back empty and every path in the sandbox looks unsupported.
from wayfinder.languages import javascript as _javascript  # noqa: F401
from wayfinder.languages import python as _python  # noqa: F401

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo() -> Path:
    return SAMPLE_REPO
