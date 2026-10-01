"""Runs the Orchestrator on Claude Code, using your own Claude Code login (no API key).

The Claude Agent SDK is Claude Code as a library: it starts the `claude` program and talks to
it. That program can do a great deal (run shell commands, read and write files), none of which
Wayfinder wants, so the agent is locked down here, in one place:

- no built-in tools at all - the only tools are the ones handed in, served in-process;
- your personal Claude settings, hooks and CLAUDE.md files are not loaded;
- anything not explicitly allowed is refused without asking (`dontAsk`);
- it runs in an empty temporary directory, nowhere near your files.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from mcp.types import ToolAnnotations

from wayfinder.agents.orchestrator import RunResult, ToolSpec
from wayfinder.core.errors import WayfinderError, UpstreamError

_SERVER = "wayfinder"
# `tools=[]` already removes every built-in tool; naming them again means a change in the
# SDK's defaults could not quietly turn one back on.
_BUILT_IN_TOOLS = [
    "Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep",
    "WebFetch", "WebSearch", "Task", "TodoWrite",
]


def _text(text: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


def _adapt(spec: ToolSpec) -> Any:
    """A ToolSpec as an in-process tool the SDK can serve."""

    @tool(spec.name, spec.description, spec.schema, annotations=ToolAnnotations(readOnlyHint=True))
    async def call(args: dict[str, Any]) -> dict[str, Any]:
        try:
            # The handlers block (pyright, SQLite), so they run off the event loop.
            return _text(await asyncio.to_thread(spec.handler, args))
        except WayfinderError as e:  # a deliberate error: the model is meant to read it
            return _text(f"error: {e}", is_error=True)
        except Exception:  # noqa: BLE001 - a bug's details must not be handed to a hosted model
            return _text("error: the tool failed unexpectedly", is_error=True)

    return call


class ClaudeCodeRunner:
    external = True  # the question and every tool result go to Anthropic

    def __init__(self, model: str | None = None) -> None:
        self._model = model  # None = whatever your Claude Code login defaults to

    def run(self, *, system: str, question: str, tools: Sequence[ToolSpec], max_turns: int) -> RunResult:
        try:
            return asyncio.run(self._run(system, question, tools, max_turns))
        except ClaudeSDKError as e:
            raise UpstreamError(f"could not run Claude Code: {e}") from e

    async def _run(self, system: str, question: str, tools: Sequence[ToolSpec], max_turns: int) -> RunResult:
        server = create_sdk_mcp_server(name=_SERVER, version="1.0.0", tools=[_adapt(t) for t in tools])
        prefix = f"mcp__{_SERVER}__"
        texts: list[str] = []
        used: list[str] = []
        final: ResultMessage | None = None

        with tempfile.TemporaryDirectory(prefix="wayfinder-") as empty_dir:
            options = ClaudeAgentOptions(
                system_prompt=system,
                tools=[],
                allowed_tools=[prefix + t.name for t in tools],
                disallowed_tools=list(_BUILT_IN_TOOLS),
                mcp_servers={_SERVER: server},
                setting_sources=[],
                permission_mode="dontAsk",
                max_turns=max_turns,
                cwd=empty_dir,
                model=self._model,
            )
            async for message in query(prompt=question, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            texts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            used.append(block.name.removeprefix(prefix))
                elif isinstance(message, ResultMessage):
                    final = message

        if final is None:
            raise UpstreamError("Claude Code finished without giving an answer")
        if final.terminal_reason == "max_turns":
            raise UpstreamError(f"Claude used all {max_turns} turns without finishing; try a narrower question")
        if final.is_error:
            raise UpstreamError(f"Claude Code reported an error ({final.terminal_reason or final.subtype})")

        answer = (final.result or "").strip() if isinstance(final.result, str) else ""
        answer = answer or (texts[-1].strip() if texts else "")
        if not answer:
            raise UpstreamError("Claude Code returned an empty answer")
        return RunResult(text=answer, tools_used=used, turns=final.num_turns)
