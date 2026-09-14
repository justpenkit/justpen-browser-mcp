# Codex

Connect Codex to the 46 browser tools after completing
[installation](../getting-started/install.md) and fetching Camoufox.

## Registration

Add the stdio server with an absolute path to the environment where it is installed:

```bash
codex mcp add justpen-browser -- /absolute/path/to/.venv/bin/python -m justpen_browser_mcp
```

Codex stores MCP servers in `~/.codex/config.toml`. Trusted projects may instead
use `.codex/config.toml`. The equivalent configuration is:

```toml
[mcp_servers.justpen-browser]
command = "/absolute/path/to/.venv/bin/python"
args = ["-m", "justpen_browser_mcp"]
```

Add this table alongside existing settings; preserve any project permission or
hook configuration. The same configuration is shared by the desktop app, CLI
and IDE extension. See [OpenAI's MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## HTTP connection

Start the browser server separately:

```bash
uv run justpen-browser-mcp --transport http --host 127.0.0.1 --port 8931
```

Use this table in place of the stdio table:

```toml
[mcp_servers.justpen-browser]
url = "http://127.0.0.1:8931/mcp"
```

Codex supports Streamable HTTP servers through the `url` field. See
[OpenAI's MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

!!! warning "No built-in authentication"

    Anyone who can reach this server can control its browser instances. Keep the
    loopback binding unless you supply your own authentication and authorization
    layer. Read the [HTTP transport warning](../getting-started/run-server.md#transport).

## Telemetry

For stdio, add a server environment table as supported by
[Codex's MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli):

```toml
[mcp_servers.justpen-browser.env]
JUSTPEN_BROWSER_OTEL_ENABLED = "true"
JUSTPEN_BROWSER_OTEL_ENDPOINT = "http://127.0.0.1:4318"
JUSTPEN_SESSION_ID = "pentest-example"
JUSTPEN_BROWSER_OTEL_RESOURCE_ATTRIBUTES = "justpen.run.id=run-example"
```

For HTTP, set these variables on the separately started server process. See
[Telemetry](../getting-started/telemetry.md) for session ownership, collector
settings and the [measured native tracing limits](../getting-started/telemetry.md#measured-client-limits).

## Verify the connection

Run `codex mcp list`, or use `/mcp` in the Codex CLI, to inspect connected servers.
Ask Codex to call `browser_health`; this reports server status without launching
a browser. Then create an ephemeral instance, navigate to a test page, take a
snapshot, and destroy the instance when finished.

If startup fails, verify the absolute interpreter path and run
`uv run python -m justpen_browser_mcp.browser_runtime` from the installation project. See the
[server guide](../getting-started/run-server.md) for logs and invocation forms.

For contributing to this repository with Codex, use the separate
[agent development guide](../contributing/agents.md).
