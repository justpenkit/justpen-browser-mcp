---
description: Install justpen-browser-mcp with uv and fetch the Camoufox browser binary.
---

# Install { #_top }

## Prerequisites { #prerequisites }

- Python 3.11–3.13 for the current checkout (3.13 is the default for contributors)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Disk space for the Camoufox browser binary

The current lockfile supports Linux, Apple silicon macOS, and 64-bit Windows.
Intel macOS and 32-bit Windows are no longer supported by the cryptography
dependency. Contributors using Windows need WSL for the Make workflow.

Release `v0.4.0` predates Python 3.11/3.12 support and requires Python 3.13.
Use a [clone of current main](#install-from-a-clone-contributors) for unreleased improvements.

## Install from git { #install-from-git }

Until the package is on PyPI, install straight from git:

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.4.0"
```

Server startup fetches Camoufox if needed; no separate browser-helper command
is required. See [Run the server](run-server.md) for invocation options.

## Install from a clone (contributors) { #install-from-a-clone-contributors }

Clone current main to use unreleased improvements, including Python 3.11/3.12
support and explicit browser selection. Contributors can run `make setup`, which
installs the locked dev and docs groups through `uv`, fetches the Camoufox binary, and
installs the project's git hooks (pre-commit / pre-push / commit-msg).

The current checkout selects Camoufox `135.0.1-beta.24` for its
`playwright>=1.49,<1.60` driver. Setup and server startup use the same selection,
which updates the Camoufox SDK's shared default browser for subsequent launches.
Use `make browser-fetch` to restore that selection, and keep the compatibility
bound in `pyproject.toml`.

`make install` installs dependencies only. See the
[contributor setup](../contributing/getting-started.md) for the full workflow.

## Verify { #verify }

```bash
uv run justpen-browser-mcp --help
```

Expected: non-empty output describing the MCP server. If the command is not
found, either your shell `PATH` does not include the venv `bin/` or you need
to invoke via `python -m justpen_browser_mcp` (see
[Run the server](run-server.md)).
