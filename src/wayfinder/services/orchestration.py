"""Answer a plain-English question about a repository, by letting Claude choose which of
Wayfinder's tools to call.

Everything the model sees goes to a hosted service, so this is where the strictest rules
live. Before anything runs: offline mode refuses, and the repository must be on the
allowlist. While it runs: the tools are bound to that one repository (they take no
repository argument), and every result is cleaned - secrets redacted, size capped - before
the model sees it. Afterwards: the answer is cleaned too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wayfinder.agents.claude_code_runner import ClaudeCodeRunner
from wayfinder.agents.orchestrator import AgentRunner, Orchestrator, ToolSpec
from wayfinder.agents.prompts.orchestrator import drift_to_text, graph_to_text, path_to_text
from wayfinder.core.errors import Forbidden
from wayfinder.domain.graph import Direction
from wayfinder.domain.results import Answer
from wayfinder.guardrails import inputs
from wayfinder.guardrails.egress import refuse_if_offline
from wayfinder.guardrails.llm_output import sanitize_output
from wayfinder.guardrails.secrets import redact_secrets
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext
from wayfinder.services.drift import DriftService
from wayfinder.services.explanation import ExplanationService
from wayfinder.services.model_access import ModelAccess

_FILE = {"type": "string", "description": "Path of the file, relative to the repository root."}
_SYMBOL = {"type": "string", "description": 'A function or method name, or "Class.method" if the plain name is ambiguous.'}
_HOPS = {"type": "integer", "minimum": 1, "maximum": 5, "description": "How many levels to walk. Default 1."}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


class OrchestrationService:
    def __init__(
        self,
        ctx: ServiceContext,
        analysis: AnalysisService,
        explanation: ExplanationService,
        drift: DriftService,
        access: ModelAccess,
        runner: AgentRunner | None = None,
    ) -> None:
        self._ctx = ctx
        self._analysis = analysis
        self._explanation = explanation
        self._drift = drift
        self._access = access
        self._runner = runner  # None = Claude Code, created on first use

    def ask(self, repo: str, question: str) -> Answer:
        settings = self._ctx.settings
        question = inputs.check_question(question, settings.limits)
        repo_root = inputs.resolve_repo(repo)

        runner = self._runner or ClaudeCodeRunner()
        orchestrator = Orchestrator(runner)
        if orchestrator.external:
            refuse_if_offline(settings.offline)
            if not self._access.egress.allows(repo_root):
                raise Forbidden(
                    f"{repo_root.name} isn't allowed to be sent to an external model, and answering a "
                    "question sends the question and what the tools find to one. Add the repo to "
                    "WAYFINDER_LLM_ALLOWED_REPOS, only if you may share that code."
                )
            self._access.charge()  # one hosted-model use, counted against the rate limit

        result = orchestrator.answer(question, self._tools(repo_root), settings.limits.max_turns)
        return Answer(
            text=sanitize_output(result.text, settings.limits),
            tools_used=list(dict.fromkeys(result.tools_used)),  # in order, without repeats
            turns=result.turns,
        )

    # --- the tools the model may use, all bound to one repository ---

    def _tools(self, repo_root: Path) -> list[ToolSpec]:
        repo = str(repo_root)
        limits = self._ctx.settings.limits

        def guard(text: str) -> str:
            """What a tool hands the model: secrets blanked out, and capped in size."""
            text, _ = redact_secrets(text)
            if len(text) > limits.max_tool_result_chars:
                text = text[: limits.max_tool_result_chars] + "\n... (result truncated)"
            return text

        def graph(direction: Direction | None):
            def handler(args: dict[str, Any]) -> str:
                dfg = self._analysis.analyze(
                    repo, args["file"], symbol=args["symbol"], hops=args.get("hops", 1), direction=direction
                )
                return guard(graph_to_text(dfg, repo_root))

            return handler

        def explain_function(args: dict[str, Any]) -> str:
            return guard(self._explanation.explain_symbol(repo, args["file"], symbol=args["symbol"]).text)

        def explain_call_path(args: dict[str, Any]) -> str:
            path = self._explanation.explain_path_between(
                repo, args["from_file"], args["from_symbol"], args["to_file"], args["to_symbol"], args.get("hops", 3)
            )
            return guard(path_to_text(path))

        def check_docs_drift(args: dict[str, Any]) -> str:
            return guard(drift_to_text(self._drift.check_symbol(repo, args["file"], symbol=args["symbol"])))

        target = _schema({"file": _FILE, "symbol": _SYMBOL, "hops": _HOPS}, ["file", "symbol"])
        one = _schema({"file": _FILE, "symbol": _SYMBOL}, ["file", "symbol"])
        return [
            ToolSpec("who_calls", "Find the callers of a function or method, with the arguments and types of each call.", target, graph("incoming")),
            ToolSpec("what_does_this_call", "Find everything a function or method calls, with argument and return types.", target, graph("outgoing")),
            ToolSpec("trace_data_flow", "Callers and callees of a function, plus which call's result is passed into which other call.", target, graph(None)),
            ToolSpec("explain_function", "Plain-language explanation of what a function or method does.", one, explain_function),
            ToolSpec(
                "explain_call_path",
                "Plain-language walkthrough of how one function reaches another through the calls between them.",
                _schema(
                    {
                        "from_file": _FILE,
                        "from_symbol": _SYMBOL,
                        "to_file": _FILE,
                        "to_symbol": _SYMBOL,
                        "hops": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Longest chain to look for. Default 3."},
                    },
                    ["from_file", "from_symbol", "to_file", "to_symbol"],
                ),
                explain_call_path,
            ),
            ToolSpec("check_docs_drift", "Check whether a function's docstring and comments still match its code.", one, check_docs_drift),
        ]
