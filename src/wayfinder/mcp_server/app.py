"""The MCP server object. Tools register themselves on it (see tools.py).

The package is named mcp_server, not mcp, so it can't be confused with the `mcp` SDK it
is built on.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    "wayfinder",
    instructions=(
        "Answers 'who calls this function, what does it call, and what data flows "
        "between them' for Python code, using pyright's real analysis rather than "
        "guesses. Every tool needs the repo root (absolute path), a file path relative "
        "to it, and a function/method/class name."
    ),
)
