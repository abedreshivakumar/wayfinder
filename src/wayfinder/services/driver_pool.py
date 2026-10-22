"""One long-lived language-server process per (repo, language).

Starting one costs time, so the first request to a repo pays it and later ones don't. A
driver is single-threaded: callers must hold the service lock while using one. Today every
repo is Python, so this holds one `PyrightDriver` per repo; a JS/TS repo would get its own
`TSServerDriver` instance alongside it, keyed separately - the two never share a process.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.core.errors import BadRequest
from wayfinder.languages import LanguageDriver, for_file


class DriverPool:
    def __init__(self) -> None:
        self._drivers: dict[tuple[Path, str], LanguageDriver] = {}

    def get(self, repo_root: Path, file: Path) -> LanguageDriver:
        """The driver for whichever language owns `file`'s extension."""
        language = for_file(file)
        if language is None:
            raise BadRequest(f"no supported language recognizes '{file.suffix}' files")
        key = (repo_root, language.id)
        driver = self._drivers.get(key)
        if driver is None:
            driver = language.make_driver(repo_root)
            driver.start()
            self._drivers[key] = driver
        return driver

    def started(self) -> list[Path]:
        """The repos that have at least one language-server process running."""
        return list({repo_root for repo_root, _ in self._drivers})

    def close(self) -> None:
        for driver in self._drivers.values():
            driver.stop()
        self._drivers.clear()
