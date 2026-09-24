"""Which code may leave this machine.

Explaining code with a hosted model means sending that code to a third party. Two rules,
checked in this order:

1. Offline mode: while it is on, nothing is sent, whatever else is configured.
2. Default-deny allowlist: nothing is sent unless its repo has been named on purpose.
"""

from __future__ import annotations

from pathlib import Path

from wayfinder.core.errors import Forbidden

OFFLINE_MESSAGE = (
    "offline mode is on, so nothing is sent to an external model. Analysis still works. "
    "Turn it off by removing WAYFINDER_OFFLINE from the environment or ~/.wayfinder/.env."
)


def refuse_if_offline(offline: bool) -> None:
    if offline:
        raise Forbidden(OFFLINE_MESSAGE)


class EgressPolicy:
    def __init__(self, allowed_repos: frozenset[Path], offline: bool = False) -> None:
        self._allowed = allowed_repos
        self._offline = offline

    def allows(self, file: Path) -> bool:
        """Is `file` inside a repo on the allowlist? (Says nothing about offline mode.)"""
        resolved = file.resolve()
        return any(resolved.is_relative_to(repo) for repo in self._allowed)

    def check(self, file: Path) -> None:
        """Raise Forbidden unless `file` may be sent to an external model."""
        refuse_if_offline(self._offline)
        if self.allows(file):
            return
        raise Forbidden(
            f"{file.name} is in a repository that isn't allowed to be sent to an external model. "
            "Code leaves this machine only for repos you name in WAYFINDER_LLM_ALLOWED_REPOS "
            "(an environment variable, or a line in ~/.wayfinder/.env; separate several paths "
            "with ':'). Only allow code you are permitted to share."
        )
