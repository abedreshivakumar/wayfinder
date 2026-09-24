"""Raw JSON-RPC 2.0 client over stdio, for talking to a language server subprocess."""

from __future__ import annotations

import json
import subprocess
from typing import Any


class LSPError(Exception):
    """Raised when the server responds with a JSON-RPC error object."""


class LSPClient:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1

    def start(self, command: list[str]) -> None:
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a request and block until the response with the matching id arrives."""
        msg_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})

        while True:
            msg = self._read()
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise LSPError(msg["error"])
                return msg.get("result")
            # else: a notification or a request from the server (e.g. window/logMessage,
            # textDocument/publishDiagnostics) that arrived before our response — ignore it
            # and keep reading until we see our own id.

    def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification: no id, no response expected."""
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def shutdown(self) -> None:
        if self._proc is None:
            return
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
        finally:
            self._proc.terminate()
            self._proc = None

    # --- framing: this is the part unique to LSP, not part of JSON-RPC itself ---

    def _write(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout

        # Read header lines until the blank line that ends the header block.
        content_length: int | None = None
        while True:
            line = stdout.readline()
            if not line:
                raise LSPError("language server closed its stdout unexpectedly")
            line = line.strip()
            if line == b"":
                break  # blank line: header block is done, body follows
            if line.lower().startswith(b"content-length:"):
                content_length = int(line.split(b":", 1)[1].strip())

        if content_length is None:
            raise LSPError("message had no Content-Length header")

        body = stdout.read(content_length)
        return json.loads(body)
