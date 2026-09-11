---
description: Server configuration and environment variables.
---

# Configuration { #_top }

Server-level configuration comes from environment variables, optionally
overridden by CLI flags on the `justpen-browser-mcp` command; there is no
config file. Configuration is read once at server startup.

## Environment variables and CLI flags { #environment-variables-and-cli-flags }

All environment variables are prefixed `BROWSER_MCP_`. Booleans accept
`1`/`true`/`yes`/`on` for true and `0`/`false`/`no`/`off` for false
(case-insensitive); an invalid value logs a warning and falls back to the
default.

| Variable                                | CLI flag                          | Format                                                                                                  | Default     |
| --------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------- |
| `BROWSER_MCP_LOG_LEVEL`                 | `--log-level`                     | Python log level name (`DEBUG`, `INFO`, `WARNING`, `ERROR`, …)                                          | `INFO`      |
| `BROWSER_MCP_MAX_INSTANCES`             | `--max-instances`                 | Integer, minimum `1`                                                                                    | `10`        |
| `BROWSER_MCP_IDLE_TTL_SECONDS`          | `--idle-ttl`                      | Integer, minimum `0`; `0` disables the idle reaper                                                      | `0`         |
| `BROWSER_MCP_REAPER_INTERVAL_SECONDS`   | `--reaper-interval`               | Integer, minimum `1`                                                                                    | `30`        |
| `BROWSER_MCP_OPERATION_TIMEOUT_SECONDS` | `--operation-timeout`             | Positive finite seconds, including time queued for an instance                                          | `60`        |
| `BROWSER_MCP_CLOSE_TIMEOUT_SECONDS`     | `--close-timeout`                 | Positive finite seconds for cooperative teardown                                                        | `10`        |
| `BROWSER_MCP_EVENT_BUFFER_SIZE`         | `--event-buffer-size`             | Retained records per console/network stream, minimum `1`                                                | `1000`      |
| `BROWSER_MCP_MAX_RESULT_BYTES`          | `--max-result-bytes`              | UTF-8 JSON structured-envelope limit, minimum `4096`                                                    | `1048576`   |
| `BROWSER_MCP_TRANSPORT`                 | `--transport {stdio,http}`        | `stdio` or `http`                                                                                       | `stdio`     |
| `BROWSER_MCP_HOST`                      | `--host`                          | Hostname or IP string                                                                                   | `127.0.0.1` |
| `BROWSER_MCP_PORT`                      | `--port`                          | Integer, minimum `1`                                                                                    | `8931`      |
| `BROWSER_MCP_HEADLESS`                  | `--headless` / `--headful`        | Boolean, or the literal `virtual` (Xvfb on Linux)                                                       | `true`      |
| `BROWSER_MCP_PROXY_SERVER`              | `--proxy`                         | Proxy URL, e.g. `http://user:pass@host:port` or `socks5://host:port`                                    | none        |
| `BROWSER_MCP_PROXY_USERNAME`            | `--proxy-username`                | String                                                                                                  | none        |
| `BROWSER_MCP_PROXY_PASSWORD`            | `--proxy-password`                | String                                                                                                  | none        |
| `BROWSER_MCP_CAMOUFOX_OS`               | `--camoufox-os`                   | Comma-separated OS list, e.g. `windows,macos,linux`                                                     | none        |
| `BROWSER_MCP_LOCALE`                    | `--locale`                        | Locale string, e.g. `en-US`                                                                             | none        |
| `BROWSER_MCP_GEOIP`                     | `--geoip` / `--no-geoip`          | Boolean override; unset enables automatic lookup only with a proxy                                      | automatic   |
| `BROWSER_MCP_BLOCK_IMAGES`              | `--block-images`                  | Boolean flag                                                                                            | `false`     |
| `BROWSER_MCP_BLOCK_WEBRTC`              | _(env only, no CLI flag)_         | Boolean                                                                                                 | `true`      |
| `BROWSER_MCP_BLOCK_WEBGL`               | _(env only, no CLI flag)_         | Boolean                                                                                                 | `false`     |
| `BROWSER_MCP_WINDOW`                    | `--window`                        | `WxH`, e.g. `1280x800`                                                                                  | none        |
| `BROWSER_MCP_FIREFOX_PREFS`             | `--firefox-pref K=V` (repeatable) | `k=v;k2=v2` pairs; each value coerced `true`/`false` → bool, integer strings → int, else kept as string | `{}` (none) |
| `BROWSER_MCP_CAMOUFOX_ARGS`             | `--camoufox-arg` (repeatable)     | Whitespace-separated extra Camoufox CLI args                                                            | `()` (none) |
| `BROWSER_MCP_ENABLE_CACHE`              | `--enable-cache` / `--no-cache`   | Boolean                                                                                                 | `true`      |
| `BROWSER_MCP_FF_VERSION`                | `--ff-version`                    | Integer, minimum `1`                                                                                    | none        |

`--firefox-pref` and `--camoufox-arg` may be passed multiple times on the CLI;
each repetition adds one entry (joined with `;` and a space respectively when
projected onto the env overlay).

Camoufox's `humanize` setting has no server-level env var or CLI flag — it
defaults to `true` and can only be overridden per instance via
`browser_create_instance` (see below).

## Precedence { #precedence }

When the same setting can be supplied in more than one place, the most
specific source wins:

1. The matching parameter passed to `browser_create_instance` (per-instance,
    highest priority — see [Lifecycle tools](../tools-reference/lifecycle.md)).
2. The CLI flag passed to `justpen-browser-mcp`.
3. The `BROWSER_MCP_*` environment variable.
4. The built-in default (lowest priority).

CLI flags are implemented as an overlay onto the environment before
`BrowserServerConfig` is built, so a flag always wins over the corresponding
env var, and an unset flag falls through to whatever the env var (or default)
provides.

A configured proxy automatically enables GeoIP lookup using the proxy's public
IP when GeoIP is unset. Explicit `geoip=False`, `BROWSER_MCP_GEOIP=false`, or
`--no-geoip` disables that lookup, including for local inspection proxies and
offline environments. A per-instance value takes precedence over the server setting.

## Execution and evidence limits

Operation deadlines cover cooperative asynchronous browser work and time queued
for its instance. A timeout may occur after an action has changed the page; inspect
the response's operation metadata and current state before repeating a mutation.
Synchronous Python supplied to `browser_run_code` can block the shared interpreter
and cannot be preempted by an asyncio deadline. Deploy the trusted server under a
process supervisor when a hard process-level deadline is required.

Console and network streams retain a bounded recent history. Each text field is
limited to 4096 characters and reports `truncated_fields` when shortened. Retrieval
supports pagination and explicit retention-loss information. Oversized MCP results
return `result_too_large`; use smaller scopes or file output to collect large evidence.

## Instance cap { #instance-cap }

`BROWSER_MCP_MAX_INSTANCES` limits reserved slots, including pending launches,
live instances, and unfinished teardown. Once the cap is reached, `browser_create_instance`
returns an `instance_limit_exceeded` error until an existing instance is
successfully closed and its reservation is released.

```bash
BROWSER_MCP_MAX_INSTANCES=5 justpen-browser-mcp
```

## Log level { #log-level }

`BROWSER_MCP_LOG_LEVEL` accepts any standard Python log level name
(`DEBUG`, `INFO`, `WARNING`, `ERROR`). Logs go to stderr.
