---
description: Start the MCP server over stdio or HTTP and connect a client.
---

# Run the server { #_top }

Every startup checks compatible official Camoufox releases, including prereleases,
and prefers the newest complete browser version. While upstream is older than
152.0.4-beta.31, it uses the temporary mirror described below. It downloads the
selected browser when needed, activates it, and verifies readiness. A failed
update check or verification stops startup rather than selecting an unverified older
browser. The resolved SDK browser selector is retained for this process's launches.
Playwright 1.61.x and Camoufox SDK 0.5.6 or newer are installed through uv.

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

## Latest-build compatibility { #latest-build-compatibility }

Published Camoufox 152.0.4-beta.30 can hang on short humanized movements, initial
mouse-down, and coordinate drag. Upstream fixed content-edge coordinate rounding
and unbounded input acknowledgement waits in the official beta.31 CI build; see
[Camoufox #751](https://github.com/daijro/camoufox/issues/751#issuecomment-5556020736).

Until a fixed official release is published, the MCP uses
[Justpen's temporary mirror](https://github.com/justpenkit/justpen-browser-mcp/releases/tag/camoufox-ci-152.0.4-beta.31-eb5dc3b)
of the **unchanged official beta.31 binaries** from
[upstream run 34003878009](https://github.com/daijro/camoufox/actions/runs/34003878009).
The package contains platform-specific download URLs and SHA256 digests; the SDK
verifies downloads before installation. Normal installations need no GitHub token
to download these public release assets. Native humanization remains enabled.

Selection is automatic on **every server startup**, including when a browser is
cached. The complete Firefox version is compared first, then the Camoufox build:

| Newest compatible official release | Selected source                               |
| ---------------------------------- | --------------------------------------------- |
| 152.0.4-beta.30                    | Temporary beta.31 mirror                      |
| 152.0.4-beta.31                    | Official release, even with the mirror cached |
| 152.0.4-beta.32                    | Official release                              |
| 153.0.0-beta.30                    | Official release                              |

An equal or newer official build, including a published prerelease, immediately
takes priority at the next startup without updating this package or removing the
workaround. The mirror catalog is not needed on that path. Logs identify the
selected source and version. Failed verification stops startup. Python packages,
including fingerprint data, are not updated at runtime.

## Next steps { #next-steps }

- Wire it into a client: [Client setup → Claude Code](../client-setup/claude-code.md)
- See the tool surface: [Tools reference → Lifecycle](../tools-reference/lifecycle.md)
