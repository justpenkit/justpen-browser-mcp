---
title: Install
description: Install justpen-browser-mcp with uv and fetch the Camoufox browser binary.
---

## Prerequisites

- Python 3.11+ (same minimum as `pyproject.toml`)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Disk space: ~150 MB for the Camoufox browser binary

## Install from git

Until the package is on PyPI, install straight from git:

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.1.0"
uv run python -m camoufox fetch   # one-time ~150MB Camoufox binary download
```

## Install from a clone (contributors)

Contributors working from a clone can run `make setup` instead, which
`uv sync`s the dev and docs groups, fetches the Camoufox binary, and
installs the project's git hooks (pre-commit / pre-push / commit-msg).

## Verify

```bash
justpen-browser-mcp --help 2>&1 | head -5
```

Expected: non-empty output describing the MCP server. If the command is not
found, either your shell `PATH` does not include the venv `bin/` or you need
to invoke via `python -m justpen_browser_mcp` (see
[Run the server](/getting-started/run-server/)).
