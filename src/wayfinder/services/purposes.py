"""One-line purposes for every module and file of a repo: written by the model when it may
be used, otherwise taken from docstrings.

A whole repo costs a few model calls (a handful of files per call), every answer is cached
by the exact prompt, and the calls run a few at a time so the overview fills in quickly.
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from wayfinder.agents.prompts import purposes as prompts
from wayfinder.agents.prompts.json_reply import parse_json_object
from wayfinder.core.errors import NotConfigured, RateLimited, WayfinderError
from wayfinder.guardrails import inputs
from wayfinder.services.context import ServiceContext
from wayfinder.services.model_access import ModelAccess
from wayfinder.services.overview import OverviewService

_PARALLEL_CALLS = 4
_RATE_LIMIT_RETRIES = 3


class PurposeService:
    def __init__(self, ctx: ServiceContext, overview: OverviewService, access: ModelAccess) -> None:
        self._ctx = ctx
        self._overview = overview
        self._access = access

    def purposes(self, repo: str) -> dict[str, Any]:
        repo_root = inputs.resolve_repo(repo)
        limits = self._ctx.settings.limits
        structure = self._overview.structure(repo)
        files = {f["path"]: f for f in structure["files"] if not f["noise"]}
        module_text: dict[str, str] = {}
        file_text: dict[str, str] = {p: f["doc"] for p, f in files.items() if f["doc"]}

        llm, note = self._model(repo_root)
        if llm is None:
            return {"modules": module_text, "files": file_text, "source": "docstrings", "note": note}

        jobs: list[tuple[str | None, list[dict[str, Any]]]] = []
        groups = (
            [(m["key"], [files[p] for p in m["files"] if p in files]) for m in structure["modules"]]
            if structure["mode"] == "modules"
            else [(None, list(files.values()))]
        )
        for key, members in groups:  # modules arrive most-important first
            step = limits.purpose_files_per_call
            for i in range(0, len(members), step):
                jobs.append((key if i == 0 else None, members[i : i + step]))

        guarded = self._access.guarded(llm)
        failures: list[str] = []

        def run(job: tuple[str | None, list[dict[str, Any]]]) -> tuple[str | None, dict[str, Any] | None]:
            key, members = job
            sources = {}
            for f in members:
                try:
                    sources[f["path"]] = (repo_root / f["path"]).read_text(errors="replace")[: limits.purpose_source_chars]
                except OSError:
                    sources[f["path"]] = ""
            prompt = prompts.build_prompt(Path(key).name if key else None, members, sources)
            digest = hashlib.sha256((prompts.SYSTEM + prompt).encode()).hexdigest()
            with self._ctx.lock:
                cached = self._ctx.store.get_path_explanation(digest)
            for attempt in range(_RATE_LIMIT_RETRIES + 1):
                if cached is not None:
                    break
                try:
                    cached = guarded.complete(prompts.SYSTEM, prompt)
                except RateLimited as e:  # every file gets a purpose: wait for the limit, don't give up
                    if attempt == _RATE_LIMIT_RETRIES:
                        failures.append(str(e))
                        return key, None
                    time.sleep(min(e.retry_after + 1, 65))
                except WayfinderError as e:
                    failures.append(str(e))
                    return key, None
            if cached is not None and not self._stored(digest):
                with self._ctx.lock:
                    self._ctx.store.set_path_explanation(digest, cached, guarded.model)
            return key, parse_json_object(cached) if cached else None

        with ThreadPoolExecutor(_PARALLEL_CALLS) as pool:
            for key, reply in pool.map(run, jobs):
                if not reply:
                    continue
                if key and isinstance(reply.get("module"), str):
                    module_text[key] = reply["module"].strip()
                for path, text in (reply.get("files") or {}).items():
                    if path in files and isinstance(text, str) and text.strip():
                        file_text[path] = text.strip()

        if failures:
            note = f"some purposes are from docstrings: {failures[0]}"
        return {"modules": module_text, "files": file_text, "source": "model", "note": note}

    def _stored(self, digest: str) -> bool:
        with self._ctx.lock:
            return self._ctx.store.get_path_explanation(digest) is not None

    def _model(self, repo_root: Path) -> tuple[Any, str | None]:
        """The model, or None and why it can't be used for this repo."""
        try:
            llm = self._access.get()
        except NotConfigured:
            return None, "no Gemini key is set up, so purposes come from docstrings"
        if llm.external:
            if self._ctx.settings.offline:
                return None, "offline mode is on, so purposes come from docstrings"
            if not self._access.egress.allows(repo_root):
                return None, (
                    f"{repo_root.name} isn't in WAYFINDER_LLM_ALLOWED_REPOS, so its code isn't sent to "
                    "a model and purposes come from docstrings"
                )
        return llm, None

