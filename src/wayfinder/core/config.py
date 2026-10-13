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
    max_output_chars: int = 8_000  # what we accept back from a model (JSON for a whole file's functions needs room)
    # Just under Gemini's free tier (15 a minute), so Wayfinder waits its turn instead of
    # being refused by Google; it also bounds a runaway loop.
    llm_calls_per_minute: int = 14
    max_question_chars: int = 2_000  # a plain-English question to the Orchestrator
    max_turns: int = 8  # tool-using rounds the Orchestrator may take for one question
    max_tool_result_chars: int = 12_000  # what any one tool may hand back to the model
    trace_timeout_seconds: int = 30  # a traced run is stopped after this long
    max_trace_edges: int = 3_000  # distinct calls recorded in one run; the rest are dropped
    max_traced_functions: int = 40  # functions checked against the static graph per trace
    max_trace_input_chars: int = 10_000  # the JSON arguments handed to the traced function
    max_listed_files: int = 2_000  # Python files listed for the UI's file picker
    max_file_functions: int = 60  # functions analyzed when a whole file is drawn
    max_file_source_chars: int = 12_000  # a file's source in a prompt
    purpose_source_chars: int = 1_500  # start of each file shown when writing one-line purposes
    purpose_files_per_call: int = 8


@dataclass(frozen=True)
class Settings:
    db_path: Path
    gemini_api_key: str | None = None
    model: str = DEFAULT_MODEL
    limits: Limits = field(default_factory=Limits)
    # Repos whose source may be sent to an external (hosted) model. Empty means none:
    # code never leaves the machine unless its repo is named here.
    llm_allowed_repos: frozenset[Path] = frozenset()
    # WAYFINDER_LLM_ALLOWED_REPOS=* : every repo may be sent, a deliberate choice by the owner.
    llm_allow_all_repos: bool = False
    # A kill switch: while on, no prompt is sent to any hosted model, whatever else is
    # configured. Analysis (which runs locally) and already-cached explanations still work.
    offline: bool = False
    # Tracing RUNS the repository's own code, so it is off unless you turn it on. Nothing
    # else in Wayfinder executes the code it analyzes.
    allow_trace: bool = False

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
            allow_trace=(setting("WAYFINDER_ALLOW_TRACE") or "").lower() in ("1", "true", "yes", "on"),
            llm_allow_all_repos=allowed.strip() == "*",
            llm_allowed_repos=frozenset(
                Path(p).expanduser().resolve()
                for p in (part.strip() for part in allowed.split(os.pathsep))
                if p and p != "*"  # blanks (a trailing ':' or a space after one) are skipped
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
