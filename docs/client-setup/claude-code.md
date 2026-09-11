---
description: Wire justpen-browser-mcp into Claude Code.
---

# Claude Code { #_top }

Wire `justpen-browser-mcp` into [Claude Code](https://claude.com/claude-code).

## Prerequisites { #prerequisites }

- Claude Code installed and authenticated
- `justpen-browser-mcp` installed and on `PATH` (see
    [Install](../getting-started/install.md))

## Registration { #registration }

Add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "justpen-browser": {
      "command": "justpen-browser-mcp"
    }
  }
}
```

## Running outside the install venv { #running-outside-the-install-venv }

If Claude Code runs outside the venv where `justpen-browser-mcp` is installed,
use an explicit interpreter path:

```json
{
  "mcpServers": {
    "justpen-browser": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "justpen_browser_mcp"]
    }
  }
}
```

## Sanity check { #sanity-check }

After registering, ask Claude Code to list available MCP servers / tools. The
`justpen-browser` server should appear with its lifecycle, navigation, and
interaction tools.

## Common pitfalls { #common-pitfalls }

- **`command not found`** — the `justpen-browser-mcp` script is not on the
    `PATH` Claude Code sees. Use the absolute-path form above.
- **Headless mode** — `browser_create_instance` defaults to `headless=true`. Pass `headless=false` to the tool call when you want to watch the browser for debugging.
- **Transport selection** — these examples use stdio. The server also
    supports HTTP when started with `--transport http`; configure your client
    for Streamable HTTP at `http://127.0.0.1:8931/mcp` to use it. See
    [Run the server](../getting-started/run-server.md#transport), including
    its warning about the lack of built-in authentication.

## Reference { #reference }

Canonical Claude Code MCP config docs: see the Claude Code documentation site
for the up-to-date config schema.
