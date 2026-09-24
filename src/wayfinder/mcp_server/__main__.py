"""Run over stdio:  uv run --directory <project> python -m wayfinder.mcp_server
Register with Claude Code:
  claude mcp add wayfinder -- uv run --directory <project> python -m wayfinder.mcp_server

stdout carries the protocol itself, so nothing in this package may print to it.
"""

from wayfinder.mcp_server import tools  # noqa: F401 - importing registers the tools on the server
from wayfinder.mcp_server.app import mcp


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
