"""The services behind the tools: built on first use, closed at exit."""

from __future__ import annotations

import atexit
import threading

from wayfinder.services import Services, build_services

_services: Services | None = None
_lock = threading.Lock()


def get_services() -> Services:
    # Created on first use (pyright itself only starts per repo when a tool needs it) and
    # closed at exit so the pyright processes are shut down cleanly.
    global _services
    with _lock:
        if _services is None:
            _services = build_services()
            atexit.register(_services.close)
        return _services
