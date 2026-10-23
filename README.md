# Wayfinder

**Find your way around unfamiliar Python, JavaScript or TypeScript code.** Point at a
repo or a function and get a real call graph, the data flowing between calls, and a
plain-language explanation - grounded in static analysis, not a model guessing at structure.

> **Status:** early stage (`0.1.0`), no automated tests yet. See [Limitations](#limitations).

![Repo overview: folders grouped into entry points, core logic, and data & schemas, each with an AI-written one-line purpose](docs/screenshots/repo-overview.png)

| | |
| --- | --- |
| ![Module view: a folder's files with a reading order and a one-line purpose each](docs/screenshots/module-view.png) Module view | ![File view: a numbered, model-written walkthrough of how the file works](docs/screenshots/file-view.png) File view |
| ![Function view: inputs, what the function does, and its output, with real types](docs/screenshots/function-view.png) Function view | ![File view: hovering an arrow shows what value it passes](docs/screenshots/file-view-tooltip.png) Hover a call to see what it passes |

## Why

The hard part of a codebase you didn't write isn't reading any one function - it's knowing
where to start and how data moves between the pieces. Generic "explain this code" tools
guess at that structure. Wayfinder builds it first, from the language server, so the graph
is exact and every explanation is grounded in it.

## Features

- **Call graph & data flow** - callers/callees of any function, up to 5 hops, with the
  types and values moving along each call
- **Plain-language explanations** - a function, a call path between two functions, or a
  whole file, written from the real analysis rather than guessed
- **Docs-drift check** - flags docstrings that no longer match the code
- **Runtime trace (opt-in)** - compares what really ran against the static graph
- **Ask in plain English** - `POST /ask` answers free-text questions by calling the tools
  above, via your own Claude Code login
- **Works offline** - analysis is 100% local; only explanations use a hosted model, and a
  single switch turns that off entirely
- **Two interfaces** - an MCP server (for Claude Code and other agents) and an HTTP API,
  plus a web UI

## Quick start

```bash
npm install -g pyright            # provides pyright-langserver
git clone https://github.com/abedreshivakumar/wayfinder.git && cd wayfinder
uv sync
claude mcp add wayfinder -- uv run --directory "$PWD" python -m wayfinder.mcp_server
```

Then ask your agent something like *"use wayfinder to show who calls `fetch_user` in
`app.py` of `/path/to/repo`"*.

## Installation

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js (for
`pyright-langserver`, and for `typescript-language-server` if you'll analyze JS/TS repos).
`/ask` additionally needs [Claude Code](https://claude.com/claude-code) installed and
logged in - no separate API key needed there.

```bash
uv sync
cd src/wayfinder/languages/javascript/tools && npm install && cd -   # JS/TS analysis only
```

**Web UI:**

```bash
cd web && npm install && npm run build      # once
uv run uvicorn wayfinder.api.main:app       # serves the UI at http://localhost:8000
```

## Usage

Every request names a function by **repo root** (absolute path), **file** (relative to
the root), and **symbol** (or an exact `line`/`col`).

**MCP tools:** `who_calls`, `what_does_this_call`, `trace_data_flow`, `explain_function`,
`explain_call_path`, `check_docs_drift`, `trace_runtime_calls` (opt-in, see
[Configuration](#configuration)). All read-only with respect to your code.

**Key HTTP routes:** `GET /overview`, `GET /purposes`, `GET /repo-summary`,
`GET /file-graph`, `GET /graph`, `POST /explain-file`, `POST /narrate`,
`POST /explain-path`, `POST /check-drift`, `POST /ask`, `POST /trace`. Full docs at `/docs`
once the server is running.

## Configuration

Settings are read from the environment first, then `~/.wayfinder/.env` (kept outside any
repo so a key can't be committed by accident), then a default.

| Variable | Default | Purpose |
| --- | --- |---|
| `ANTHROPIC_API_KEY` | none | Preferred model provider when set (Claude) |
| `GEMINI_API_KEY` | none | Fallback provider when no Anthropic key is set |
| `WAYFINDER_LLM_CALLS_PER_MINUTE` | 14 (Gemini) / 50 (Claude) | Override the model rate limit |
| `WAYFINDER_OFFLINE` | off | Blocks every call to a hosted model |
| `WAYFINDER_LLM_ALLOWED_REPOS` | none | Repos whose code may be sent to a hosted model (`:`-separated, or `*` for all) |
| `WAYFINDER_ALLOW_TRACE` | off | Lets runtime tracing execute the repo's own code - not a sandbox |

## Privacy and security

Explaining code with a hosted model means sending that code to a third party, so the
defaults are strict:

- **Default-deny allowlist** - nothing is sent anywhere unless its repo is explicitly
  allowed
- **Offline switch** - one setting refuses every hosted-model call outright
- **Secret redaction** - keys, tokens, JWTs and secret-looking values are stripped from
  every prompt and every reply before they're used or shown
- **Untrusted source** - repository code is fenced and the model is told never to follow
  instructions found inside it
- **Rate limiting & path sandboxing** - calls are capped per minute, and a request can only
  reach files inside the repo it names

`~/.wayfinder/graph.db` holds everything derived from your code (call graphs, cached
explanations) - delete it any time, it's rebuilt on demand.

## How it works

```text
request ─▶ services ─▶ analysis ─▶ a language server (LSP) ── call hierarchy, types
              │            └─ outline + imports ──────────── arguments, assignments, schemas
              ├─▶ storage (SQLite) ── graph, labels, cached explanations
              └─▶ agents ─▶ guardrails ─▶ model ───── explanations (optional)
```

A `Language` registry picks the implementation per file extension - pyright for Python,
`typescript-language-server` for JS/TS - and everything above it (storage, agents,
guardrails, the API, the UI) is identical either way. Deterministic facts (who calls what,
what a docstring claims) are computed, never asked of a model; a model is only used to put
already-verified facts into words.

## Limitations

- **Static analysis only** - dynamic dispatch, monkey-patching and runtime-registered
  callbacks are invisible to it, so those calls are missing from the graph
- **Python and JS/TS only** - and runtime tracing (Flow-Tracer) is Python-only so far
- **Dependency resolution** - pyright resolves third-party packages from the Python on
  your `PATH`, not the analyzed repo's own environment, so unresolved types show as unknown
- **Single user, local** - no authentication; meant to run on your own machine
- **No automated test suite yet**

`artifacts/` holds the early design docs from before the code was restructured - useful as
design history, but out of date on names and file paths.

## License

No license has been chosen yet. Until one is added, all rights are reserved.

## Acknowledgements

Built on [pyright](https://github.com/microsoft/pyright) and the Language Server Protocol,
[FastAPI](https://fastapi.tiangolo.com/), the
[Model Context Protocol](https://modelcontextprotocol.io/) Python SDK,
[uv](https://docs.astral.sh/uv/), and SQLite.
