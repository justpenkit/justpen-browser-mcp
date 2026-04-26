---
title: Run the server
description: Start the MCP server over stdio and connect a client.
---

## Invocation forms

The install exposes two equivalent invocations — the `justpen-browser-mcp`
console script (added by `[project.scripts]` in `pyproject.toml`) and the
`python -m justpen_browser_mcp` module entry point:

```bash
justpen-browser-mcp
# or
python -m justpen_browser_mcp
```

## Transport

`justpen-browser-mcp` speaks MCP over **stdio**. There is no HTTP transport.
Your client is responsible for spawning the process and piping its stdin/stdout.

## Server identity

| Property     | Value                                                                             |
| ------------ | --------------------------------------------------------------------------------- |
| FastMCP name | `camoufox-mcp`                                                                    |
| Entry points | `justpen-browser-mcp` (console script) / `python -m justpen_browser_mcp` (module) |

## Running outside the install venv

If the client runs outside the virtualenv where the package is installed,
use the `python -m justpen_browser_mcp` form with an explicit interpreter
path instead.

## Logs

Server-side logs go to stderr. See [Configuration](/getting-started/configuration/) for the
`BROWSER_MCP_LOG_LEVEL` variable.

## Next steps

- Wire it into a client: [Client setup → Claude Code](/client-setup/claude-code/)
- See the tool surface: [Tools reference → Lifecycle](/tools-reference/lifecycle/)
