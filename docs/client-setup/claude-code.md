# Claude Code

Wire `justpen-browser-mcp` into [Claude Code](https://claude.com/claude-code).

## Prerequisites

- Claude Code installed and authenticated
- `justpen-browser-mcp` installed and on `PATH` (see
  [Install](../getting-started/install.md))

## Registration

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

## Running outside the install venv

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

## Sanity check

After registering, ask Claude Code to list available MCP servers / tools. The
`justpen-browser` server should appear with its lifecycle, navigation, and
interaction tools.

## Common pitfalls

- **`command not found`** — the `justpen-browser-mcp` script is not on the
  `PATH` Claude Code sees. Use the absolute-path form above.
- **Headless surprise** — `BROWSER_MCP_HEADLESS` defaults to `true`; set it to
  `false` in the env block of the mcpServers entry while debugging.
- **Stdio transport only** — Claude Code configs that specify an HTTP URL will
  not work. Only the `command` form is supported.

## Reference

Canonical Claude Code MCP config docs: see the Claude Code documentation site
for the up-to-date config schema.
