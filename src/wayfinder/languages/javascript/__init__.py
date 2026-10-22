"""JavaScript/TypeScript support - not built yet.

Planned (see the project's JS build-out plan): a `TSServerDriver` in `lsp/tsserver_driver.py`
driving `typescript-language-server` over the same LSP transport `lsp/client.py` already
speaks to pyright with, registered here as a `Language` the same way `languages/python`
registers Python. `services/container.py` would import this module once it exists, the same
way it imports `languages.python` today.
"""
