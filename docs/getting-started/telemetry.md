---
description: Export correlated MCP traces, operational logs and metrics over OTLP.
---

# Telemetry

Telemetry is opt-in and works with both stdio and HTTP MCP connections. It exports
request spans, operational events and request count/duration metrics to an OTLP
collector. It does not export tool arguments, results, page content or exception text.

## Setup

With an HTTP/protobuf collector listening on port 4318:

```bash
export JUSTPEN_BROWSER_OTEL_ENABLED=true
export JUSTPEN_BROWSER_OTEL_PROTOCOL=http/protobuf
export JUSTPEN_BROWSER_OTEL_ENDPOINT=http://127.0.0.1:4318
export JUSTPEN_SESSION_ID=pentest-example
export JUSTPEN_BROWSER_OTEL_RESOURCE_ATTRIBUTES=justpen.run.id=run-example,deployment.environment.name=local
export JUSTPEN_BROWSER_OTEL_REQUIRE_SESSION=true
uv run justpen-browser-mcp
```

The endpoint is the **telemetry collector**, separate from the MCP listener and
the browser's inspection proxy. For a client-spawned stdio server, pass these
variables through its MCP configuration: [Codex](../client-setup/codex.md#telemetry)
or [Claude Code](../client-setup/claude-code.md#telemetry).

## Session identity

`justpen.session.id` is a resource attribute on all three signals, taken **only**
from `JUSTPEN_SESSION_ID`. The server removes that key from additional resource
attributes, including encoded and duplicate entries. Missing or invalid session
values never fall back to request metadata, HTTP headers or a native client session.
Set `JUSTPEN_BROWSER_OTEL_REQUIRE_SESSION=true` to reject enabled startup without it.

The launcher owns these IDs: retain the same session for a pentest and its retests,
and optionally supply a different `justpen.run.id` per run. One server process has
one fixed session/run resource. Each process generates a new `service.instance.id`
unless explicitly supplied. Session and run IDs accept 1–128 ASCII letters, digits,
periods, underscores, colons and hyphens. Additional resource fields use comma-separated
`key=value` pairs with percent encoding for reserved characters.

Filter the backend by the **resource** field `justpen.session.id`. Native client
session/thread IDs remain separate. Retention, sampling and collector delivery
determine which records are available; session tagging does not guarantee delivery.

## Settings

All suffixes below use the prefix **`JUSTPEN_BROWSER_OTEL_`**. `JUSTPEN_SESSION_ID`
is the dedicated exception. Booleans accept `true` or `false`, case-insensitively.
Invalid values produce diagnostics without printing their contents.

| Suffix                                                    | Meaning / default                                                                       |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `ENABLED`                                                 | Master switch; `false`.                                                                 |
| `TRACES_ENABLED`, `LOGS_ENABLED`, `METRICS_ENABLED`       | Individual signals; each `true` when master is enabled.                                 |
| `REQUIRE_SESSION`                                         | Require a valid session when enabled; `false`.                                          |
| `SERVICE_NAME`                                            | `justpen-browser-mcp`; overrides additional `service.name`.                             |
| `RESOURCE_ATTRIBUTES`                                     | Additional fields, such as `justpen.run.id`; excludes `justpen.session.id`.             |
| `PROTOCOL`                                                | `http/protobuf` (default) or `grpc`.                                                    |
| `ENDPOINT`                                                | Collector base URL; SDK defaults to localhost:4318 for HTTP or localhost:4317 for gRPC. |
| `HEADERS`                                                 | Collector headers as comma-separated, percent-encoded `key=value` pairs.                |
| `TIMEOUT`                                                 | Positive exporter timeout in seconds; SDK default 10.                                   |
| `CERTIFICATE`, `CLIENT_CERTIFICATE`, `CLIENT_KEY`         | CA and optional client certificate/key file paths.                                      |
| `COMPRESSION`, `INSECURE`                                 | `none`/`gzip`/`deflate`; gRPC insecure-channel boolean.                                 |
| `TRACES_*`, `LOGS_*`, `METRICS_*`                         | Per-signal overrides for protocol and the exporter options above.                       |
| `TRACES_SAMPLER`, `TRACES_SAMPLER_ARG`                    | Sampler; `parentbased_always_on`. Ratio argument between 0 and 1.                       |
| `BSP_MAX_QUEUE_SIZE`, `BLRP_MAX_QUEUE_SIZE`               | Trace/log queue capacity; SDK default 2048.                                             |
| `BSP_MAX_EXPORT_BATCH_SIZE`, `BLRP_MAX_EXPORT_BATCH_SIZE` | Batch size; SDK default 512, capped at queue capacity.                                  |
| `BSP_SCHEDULE_DELAY`, `BLRP_SCHEDULE_DELAY`               | Batch delay in milliseconds; SDK defaults 5000/1000.                                    |
| `BSP_EXPORT_TIMEOUT`, `BLRP_EXPORT_TIMEOUT`               | SDK batch flush timeout in milliseconds; default 30000.                                 |
| `METRIC_EXPORT_INTERVAL`, `METRIC_EXPORT_TIMEOUT`         | Milliseconds; SDK defaults 60000/30000.                                                 |
| `SHUTDOWN_TIMEOUT_MS`                                     | Total telemetry cleanup budget after browser cleanup; `5000`.                           |

Per-signal options take precedence. An HTTP base endpoint gains `/v1/traces`,
`/v1/logs` or `/v1/metrics`; a signal-specific endpoint is used exactly as supplied.
Samplers accept `always_on`, `always_off`, `traceidratio` and their `parentbased_`
variants. Invalid protocols disable the affected signal. Queue, batch and interval
values must be positive integers. Use exporter `TIMEOUT` to bound network attempts;
SDK batch flush settings do not interrupt an exporter already blocked in a call.

Raw `OTEL_*` variables do not configure this server. Enabled CLI startup clears
them in its own process before applying the validated browser settings; the parent
client is unaffected. Leave FastMCP's telemetry mode at its default `native`.

## Trace continuity and correlation

A valid HTTP `traceparent` takes priority over MCP request `params._meta` context.
Otherwise, valid `_meta.traceparent` is used. Valid `tracestate` is retained. With
neither, the request starts a new root trace. Each call has a new server span whose
parent is the supplied span; concurrent calls keep independent context.

The server enriches FastMCP's existing spans with request IDs, browser operation
UUIDs and resolved instance/page/frame IDs when available. Codex `_meta.callId`
and Claude `_meta["claudecode/toolUseId"]` map to `gen_ai.tool.call.id`; conflicting
IDs are flagged rather than merged. Native session/thread/turn/item IDs are retained
separately when present. No new tool arguments or browser HTTP headers are required.

## Measured client limits

Headless probes on **2026-09-14**, using Codex **0.154.0** (`codex exec`) and
Claude Code **2.1.270** (`claude -p`), observed:

| Client      | stdio                                                           | HTTP                                                                           |
| ----------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Codex       | No W3C context; independent MCP trace with call-ID correlation. | W3C context from a separate transport-worker trace, not its native tool trace. |
| Claude Code | No W3C context; independent MCP trace with call-ID correlation. | W3C context continued the native tool-execution trace.                         |

The MCP continues the context it receives; it cannot reconstruct an upstream
parent that the client did not send. These probes do not establish interactive,
subagent, resume or retest behavior. Those require separate launcher integration tests.

## Runtime behavior

Operational logs contain fixed request/lifecycle events; ordinary Python logs
remain on stderr. Stdio stdout stays reserved for MCP. Request metrics are
`justpen.mcp.requests` and `justpen.mcp.request.duration` (seconds), labeled only
by method, transport and outcome. Logs retain active trace/span IDs even when the
trace is unsampled. Errors and cancellations preserve available operation IDs.

Disabled telemetry creates no providers or exporter threads. Enabled export uses
bounded queues; a slow or unavailable collector can lose records without failing
browser calls. Shutdown attempts all signal flushes within one budget after
browser cleanup; blocked exporters cannot keep the interpreter alive indefinitely.
