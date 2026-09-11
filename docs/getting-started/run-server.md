---
description: Start the MCP server over stdio or HTTP and connect a client.
---

# Run the server { #_top }

## Invocation forms { #invocation-forms }

The install exposes two equivalent invocations — the `justpen-browser-mcp`
console script (added by `[project.scripts]` in `pyproject.toml`) and the
`python -m justpen_browser_mcp` module entry point. From your uv project,
use `uv run` to select its installed environment:

```bash
uv run justpen-browser-mcp
# or
uv run python -m justpen_browser_mcp
```

## Transport { #transport }

`justpen-browser-mcp` supports two transports, selected with
`BROWSER_MCP_TRANSPORT` or `--transport`:

- **stdio** (default) — the client spawns the process and speaks MCP over its
    stdin/stdout. No network socket is opened.
- **http** — the server listens for MCP-over-HTTP connections on a TCP host
    and port.

```bash
# stdio (default) — no flags needed
uv run justpen-browser-mcp

# HTTP, bound to loopback only
uv run justpen-browser-mcp --transport http --host 127.0.0.1 --port 8931
```

The HTTP MCP endpoint is `http://127.0.0.1:8931/mcp`.

`--host` and `--port` (or `BROWSER_MCP_HOST` / `BROWSER_MCP_PORT`) only take
effect when `--transport http` is selected; they are ignored on stdio. See
[Configuration](configuration.md) for the full flag/env
reference and precedence rule.

!!! warning "No built-in authentication"

    The HTTP transport has **no built-in authentication or authorization**.
    Anyone who can reach the host/port can drive every browser instance on the
    server. Bind to `127.0.0.1` (the default) or another trusted, non-routable
    address, and only expose it on a trusted network — never bind `--host` to
    `0.0.0.0` or a public interface without putting your own auth/proxy layer in
    front of it.

## Server identity { #server-identity }

| Property     | Value                                                                             |
| ------------ | --------------------------------------------------------------------------------- |
| FastMCP name | `camoufox-mcp`                                                                    |
| Entry points | `justpen-browser-mcp` (console script) / `python -m justpen_browser_mcp` (module) |

## Running outside the install venv { #running-outside-the-install-venv }

If the client runs outside the virtualenv where the package is installed,
use the `python -m justpen_browser_mcp` form with an explicit interpreter
path instead.

## Logs { #logs }

Server-side logs go to stderr. See [Configuration](configuration.md) for the
`BROWSER_MCP_LOG_LEVEL` variable.

## Next steps { #next-steps }

- Wire it into a client: [Client setup → Claude Code](../client-setup/claude-code.md)
- See the tool surface: [Tools reference → Lifecycle](../tools-reference/lifecycle.md)
