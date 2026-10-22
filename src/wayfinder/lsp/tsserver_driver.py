"""Drives a `typescript-language-server` subprocess - the JS/TS counterpart of
`pyright_driver.py`. Same LSP transport (`client.py`), same handshake shape, same five
methods `analysis/call_graph.py` and `lsp/symbols.py` need; the only real differences are
the command to launch and the `languageId` each file is opened with.

Unlike pyright, `typescript-language-server` was tested and does NOT return an empty
`incomingCalls` right after a file is opened - there's no warm-up window to retry through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wayfinder.core.errors import NotConfigured
from wayfinder.lsp.client import LSPClient
from wayfinder.lsp.position import to_lsp_position

_BIN = Path(__file__).resolve().parent.parent / "languages/javascript/tools/node_modules/.bin/typescript-language-server"

_LANGUAGE_IDS = {".ts": "typescript", ".tsx": "typescriptreact", ".js": "javascript", ".jsx": "javascriptreact"}


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


class TSServerDriver:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.client = LSPClient()
        self._opened: dict[Path, tuple[int, int]] = {}  # file -> (mtime_ns, version)

    def start(self) -> None:
        if not _BIN.is_file():
            raise NotConfigured(
                f"typescript-language-server isn't installed at {_BIN}. Run `npm install` in "
                "src/wayfinder/languages/javascript/tools/ to set it up."
            )
        self.client.start([str(_BIN), "--stdio"])
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
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    }
                },
                "workspaceFolders": [
                    {"uri": _file_uri(self.repo_root), "name": self.repo_root.name}
                ],
            },
        )
        self.client.notify("initialized", {})

    def open_file(self, file: Path) -> None:
        """typescript-language-server only analyzes files it's been told are 'open' via
        didOpen - same rule as pyright, different languageId per extension."""
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
                        "languageId": _LANGUAGE_IDS.get(file.suffix, "typescript"),
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
                    "contentChanges": [{"text": text}],
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
        not as structured data."""
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
        Used to turn a name like "flowLayout" into a position."""
        self.open_file(file)
        result = self.client.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": _file_uri(file)}}
        )
        return result or []
