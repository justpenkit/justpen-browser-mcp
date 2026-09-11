---
description: Wire justpen-browser-mcp into GitHub Copilot CLI.
---

# Copilot CLI { #_top }

Wire `justpen-browser-mcp` into [GitHub Copilot CLI](https://github.com/github/gh-copilot) MCP-enabled builds.

## Prerequisites { #prerequisites }

- Copilot CLI installed and authenticated with MCP support enabled
- `justpen-browser-mcp` installed and on `PATH` (see
    [Install](../getting-started/install.md))

## Registration { #registration }

Add to your Copilot CLI MCP config (see upstream Copilot CLI docs for the
canonical config file location):

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

If Copilot CLI runs outside the venv where `justpen-browser-mcp` is
installed, use an explicit interpreter path:

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

After registering, list MCP servers / tools from within Copilot CLI. The
`justpen-browser` server should appear with its lifecycle, navigation, and
interaction tools.

## Common pitfalls { #common-pitfalls }

- **`command not found`** — the `justpen-browser-mcp` script is not on the
    `PATH` Copilot CLI sees. Use the absolute-path form above.
- **Headless mode** — `browser_create_instance` defaults to `headless=true`. Pass `headless=false` to the tool call when you want to watch the browser for debugging.
- **Transport selection** — these examples use stdio. The server also
    supports HTTP when started with `--transport http`; configure your client
    for Streamable HTTP at `http://127.0.0.1:8931/mcp` to use it. See
    [Run the server](../getting-started/run-server.md#transport), including
    its warning about the lack of built-in authentication.

## Reference { #reference }

Canonical Copilot CLI MCP config docs: see the upstream Copilot CLI
documentation for the up-to-date config schema and config-file location.
