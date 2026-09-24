"""One long-lived pyright process per repo.

Starting pyright costs time, so the first request to a repo pays it and later ones don't.
A PyrightDriver is single-threaded: callers must hold the service lock while using one.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.lsp.pyright_driver import PyrightDriver


class DriverPool:
    def __init__(self) -> None:
        self._drivers: dict[Path, PyrightDriver] = {}

    def get(self, repo_root: Path) -> PyrightDriver:
        driver = self._drivers.get(repo_root)
        if driver is None:
            driver = PyrightDriver(repo_root)
            driver.start()
            self._drivers[repo_root] = driver
        return driver

    def started(self) -> list[Path]:
        """The repos that have a pyright process running."""
        return list(self._drivers)

    def close(self) -> None:
        for driver in self._drivers.values():
            driver.stop()
        self._drivers.clear()
