---
title: Copilot CLI
description: Wire justpen-browser-mcp into GitHub Copilot CLI.
---

Wire `justpen-browser-mcp` into [GitHub Copilot CLI](https://github.com/github/gh-copilot) MCP-enabled builds.

## Prerequisites

- Copilot CLI installed and authenticated with MCP support enabled
- `justpen-browser-mcp` installed and on `PATH` (see
  [Install](/getting-started/install/))

## Registration

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

## Running outside the install venv

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

## Sanity check

After registering, list MCP servers / tools from within Copilot CLI. The
`justpen-browser` server should appear with its lifecycle, navigation, and
interaction tools.

## Common pitfalls

- **`command not found`** — the `justpen-browser-mcp` script is not on the
  `PATH` Copilot CLI sees. Use the absolute-path form above.
- **Headless mode** — `browser_create_instance` defaults to `headless=true`. Pass `headless=false` to the tool call when you want to watch the browser for debugging.
- **Stdio transport only** — this server speaks MCP over stdio; HTTP transport
  is not supported. Only the `command` form works.

## Reference

Canonical Copilot CLI MCP config docs: see the upstream Copilot CLI
documentation for the up-to-date config schema and config-file location.
