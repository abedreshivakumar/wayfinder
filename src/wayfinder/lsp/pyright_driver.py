"""Drives a pyright-langserver subprocess through the specific LSP calls Wayfinder needs.

client.py knows how to send/receive *any* JSON-RPC message. This file knows what
messages to send, in what order, to get pyright to answer "who calls this function."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wayfinder.lsp.client import LSPClient
from wayfinder.lsp.position import to_lsp_position


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


class PyrightDriver:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.client = LSPClient()
        # file -> (mtime_ns, version) of the text pyright currently has for it
        self._opened: dict[Path, tuple[int, int]] = {}

    def start(self) -> None:
        self.client.start(["pyright-langserver", "--stdio"])
        self._initialize()

    def stop(self) -> None:
        self.client.shutdown()

    # --- handshake: must happen in this exact order before anything else works ---

    def _initialize(self) -> None:
        self.client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": _file_uri(self.repo_root),
                "capabilities": {
                    "textDocument": {
                        "callHierarchy": {"dynamicRegistration": True},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        # Without this, documentSymbol comes back as a flat list that
                        # loses which class a method belongs to.
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    }
                },
                "workspaceFolders": [
                    {"uri": _file_uri(self.repo_root), "name": self.repo_root.name}
                ],
            },
        )
        # "initialized" tells the server the handshake is done and it may now
        # send/receive normal requests - skipping this leaves pyright waiting.
        self.client.notify("initialized", {})

    def open_file(self, file: Path) -> None:
        """pyright only analyzes files it's been told are 'open' via didOpen.

        If the file changed on disk since we last sent it, send the new text: a
        long-running server would otherwise keep answering from the old code."""
        mtime = file.stat().st_mtime_ns
        known = self._opened.get(file)
        if known is not None and known[0] == mtime:
            return

        text = file.read_text()
        if known is None:
            version = 1
            self.client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": _file_uri(file),
                        "languageId": "python",
                        "version": version,
                        "text": text,
                    }
                },
            )
        else:
            version = known[1] + 1
            self.client.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": _file_uri(file), "version": version},
                    "contentChanges": [{"text": text}],  # no range = the whole new text
                },
            )
        self._opened[file] = (mtime, version)

    # --- the actual questions we care about ---

    def prepare_call_hierarchy(self, file: Path, line: int, col: int) -> dict[str, Any] | None:
        """line, col are 1-indexed. Returns the first CallHierarchyItem at that
        position, or None if there isn't a callable symbol there."""
        self.open_file(file)
        result = self.client.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": {"uri": _file_uri(file)}, "position": to_lsp_position(line, col)},
        )
        if not result:
            return None
        return result[0]

    def incoming_calls(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Who calls this symbol."""
        result = self.client.request("callHierarchy/incomingCalls", {"item": item})
        return result or []

    def outgoing_calls(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        """What this symbol calls."""
        result = self.client.request("callHierarchy/outgoingCalls", {"item": item})
        return result or []

    def hover(self, file: Path, line: int, col: int) -> str | None:
        """Raw markdown hover text - type info lives in here as a formatted string,
        not as structured data. Parsing it is dataflow/type_resolver.py's job, later."""
        self.open_file(file)
        result = self.client.request(
            "textDocument/hover",
            {"textDocument": {"uri": _file_uri(file)}, "position": to_lsp_position(line, col)},
        )
        if not result:
            return None
        contents = result.get("contents")
        if isinstance(contents, dict):
            return contents.get("value")
        return contents

    def document_symbols(self, file: Path) -> list[dict[str, Any]]:
        """Every symbol in a file as a tree: classes contain their methods.
        Used to turn a name like "fetch_user" into a position."""
        self.open_file(file)
        result = self.client.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": _file_uri(file)}}
        )
        return result or []
