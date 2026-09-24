"""Settings: every environment variable and default in one place.

Each value comes from the environment first, then from ~/.wayfinder/.env (kept outside
any repo so a key can't be committed by accident), then a default. Nothing else in the
package reads os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def home_dir() -> Path:
    return Path.home() / ".wayfinder"


@dataclass(frozen=True)
class Limits:
    """Bounds that keep a single request from getting out of hand."""

    max_hops: int = 5  # each hop can multiply the graph, so this caps one request
    max_source_chars: int = 6000  # per function, in a prompt
    max_path_source_chars: int = 2500  # per function in a call-chain prompt, which holds several
    max_prompt_chars: int = 30_000  # everything sent to a model in one call
    max_output_chars: int = 4_000  # what we accept back from a model
    llm_calls_per_minute: int = 20  # hosted models cost money; this bounds a runaway loop


@dataclass(frozen=True)
class Settings:
    db_path: Path
    gemini_api_key: str | None = None
    model: str = DEFAULT_MODEL
    limits: Limits = field(default_factory=Limits)
    # Repos whose source may be sent to an external (hosted) model. Empty means none:
    # code never leaves the machine unless its repo is named here.
    llm_allowed_repos: frozenset[Path] = frozenset()
    # A kill switch: while on, no prompt is sent to any hosted model, whatever else is
    # configured. Analysis (which runs locally) and already-cached explanations still work.
    offline: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        env_file = _read_env_file(home_dir() / ".env")

        def setting(name: str) -> str | None:
            return os.environ.get(name, "").strip() or env_file.get(name) or None

        db_path = setting("WAYFINDER_DB")
        allowed = setting("WAYFINDER_LLM_ALLOWED_REPOS") or ""  # paths separated like $PATH
        return cls(
            db_path=Path(db_path) if db_path else home_dir() / "graph.db",
            gemini_api_key=setting("GEMINI_API_KEY"),
            model=setting("WAYFINDER_MODEL") or DEFAULT_MODEL,
            offline=(setting("WAYFINDER_OFFLINE") or "").lower() in ("1", "true", "yes", "on"),
            llm_allowed_repos=frozenset(
                Path(p).expanduser().resolve()
                for p in (part.strip() for part in allowed.split(os.pathsep))
                if p  # blanks (a trailing ':' or a space after one) are skipped
            ),
        )


def _read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments are ignored, quotes are stripped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep:
            values[name.strip()] = value.strip().strip("'\"")
    return values
