---
description: Install justpen-browser-mcp with uv and fetch the Camoufox browser binary.
---

# Install { #_top }

## Prerequisites { #prerequisites }

- Python 3.11–3.13 (3.13 is the default for contributors)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Disk space for the Camoufox browser binary

The current lockfile supports Linux, Apple silicon macOS, and 64-bit Windows.
Intel macOS and 32-bit Windows are no longer supported by the cryptography
dependency. On Windows, use WSL to run the server and the Make workflow; the
server's signal handling requires a Unix event loop.

## Install from git { #install-from-git }

Until the package is on PyPI, install straight from git inside your Python project:

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.7.0"
```

Run `uv run justpen-browser-mcp` from that project to start the server using its
installed environment. Server startup fetches Camoufox if needed; no separate
browser-helper command is required. See [Run the server](run-server.md) for
invocation options.

## Install from a clone (contributors) { #install-from-a-clone-contributors }

Clone the repository to develop the server. Contributors can run `make setup`, which
installs the locked dev and docs groups through `uv`, fetches the Camoufox binary, and
installs the project's git hooks (pre-commit / pre-push / commit-msg).

Every server startup resolves the newest compatible official Camoufox release for
this platform, including prereleases. While upstream is older than the fixed
beta.31 CI build, it selects a SHA256-pinned mirror of that unchanged official build.
Equal or newer official releases automatically take priority at the next startup,
even when the mirror is cached. See [browser selection](run-server.md#latest-build-compatibility).
The server reuses or downloads the selected browser, activates it, and verifies it before serving
browser operations. Startup fails if that preparation cannot complete; it does not
fall back to an unverified older browser. Playwright 1.61.x and Camoufox SDK 0.5.6 or newer are required. The process
retains the exact resolved SDK browser selector for all its launches even if another SDK process
later changes the shared active selection. `make browser-fetch` uses the same
preparation flow. Python dependencies are installed through uv, not updated at runtime.

The server excludes Camoufox's automatically added uBlock Origin
extension because its startup request handler can leave navigations suspended.
Extensions already installed in a persistent profile are retained.

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
