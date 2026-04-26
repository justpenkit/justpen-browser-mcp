# Configuration

All runtime configuration is via environment variables; there is no config
file. Variables are read at server startup.

## Environment variables

| Variable                    | Default | Description                                                                                                                                                                            |
| --------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BROWSER_MCP_MAX_INSTANCES` | `10`    | Maximum number of concurrently live Camoufox instances. Must be a positive integer; invalid values (non-integer, zero, or negative) fall back to `10` with a warning logged to stderr. |
| `BROWSER_MCP_LOG_LEVEL`     | `INFO`  | Python log level name for server-side logging to stderr.                                                                                                                               |

## Instance cap

`BROWSER_MCP_MAX_INSTANCES` controls how many Camoufox processes the server
will run at the same time. Once the cap is reached, `browser_create_instance`
returns an `instance_limit_exceeded` error until an existing instance is
destroyed.

```bash
BROWSER_MCP_MAX_INSTANCES=5 justpen-browser-mcp
```

## Log level

`BROWSER_MCP_LOG_LEVEL` accepts any standard Python log level name
(`DEBUG`, `INFO`, `WARNING`, `ERROR`). Logs go to stderr.
