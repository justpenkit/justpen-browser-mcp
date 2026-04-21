# Configuration

All runtime configuration is via environment variables; there is no config
file. Variables are read at server startup.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BROWSER_MCP_HEADLESS` | `true` | Launch Camoufox in headless mode. Accepts `true` or `false` (case-insensitive). |
| `BROWSER_MCP_LOG_LEVEL` | `INFO` | Python log level name for server-side logging to stderr. |

## Headless default

`BROWSER_MCP_HEADLESS` defaults to `true`. Set it to `false` (case-insensitive)
to watch Camoufox drive the browser — useful for debugging locators and
modal-state bugs.

```bash
BROWSER_MCP_HEADLESS=false justpen-browser-mcp
```

## Log level

`BROWSER_MCP_LOG_LEVEL` accepts any standard Python log level name
(`DEBUG`, `INFO`, `WARNING`, `ERROR`). Logs go to stderr.
