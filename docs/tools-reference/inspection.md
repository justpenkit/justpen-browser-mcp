---
description: Snapshot, screenshot, console, and network inspection.
---

# Inspection { #_top }

Inspection tools let you observe the current state of a browser instance — its accessibility tree, visual appearance, console output, and network activity. `browser_snapshot` is the primary tool: it returns an LLM-friendly YAML accessibility tree where every interactive element carries a `[ref=eN]` tag that other tools consume to click, type, or drag without pixel coordinates. These refs are session-scoped and invalidated by navigation; see [Refs & snapshots](../concepts/refs-snapshots.md) for a full explanation of the ref lifecycle. Use `browser_screenshot` when visual fidelity matters, and `browser_console_messages` / `browser_network_requests` for debugging JavaScript errors and API calls.

## browser_snapshot { #browser_snapshot }

Capture an accessibility snapshot of the active page in LLM-friendly YAML.

**Signature**

```python
async def browser_snapshot(instance: str, selector: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                               |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                            |
| `selector` | `str \| None` | `None`  | Optional CSS or aria selector to scope the snapshot to a subtree. When provided, refs are **not** included in the output. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "snapshot": "<yaml string>", "url": "https://example.com/page" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_snapshot", "arguments": { "instance": "main" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "snapshot": "- button \"Submit\" [ref=e12]\n- textbox \"Email\" [ref=e7]",
    "url": "https://example.com/login"
  }
}
```

**Notes** — Default mode (`selector=None`) uses the internal `Frame.ariaSnapshot` channel with `mode="ai"` and annotates every interactive element with `[ref=eN]`. Pass a ref value to `browser_click`, `browser_type`, or other interaction tools to act on that element. Refs are session-scoped and invalidated by navigation or page reload — call `browser_snapshot` again after any navigation to obtain fresh refs. Selector mode calls `Locator.aria_snapshot` on the matching element and returns plain aria YAML without refs; use it for scoped inspection of a known subtree when you do not need to interact with the results.

## browser_screenshot { #browser_screenshot }

Take a visual screenshot as base64, or save it to an explicit server-side path.

**Signature**

```python
async def browser_screenshot(
    instance: str,
    image_format: str = "png",
    *,
    full_page: bool = False,
    path: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name           | Type   | Default | Description                                                              |
| -------------- | ------ | ------- | ------------------------------------------------------------------------ |
| `instance`     | `str`  | —       | Instance name.                                                           |
| `image_format` | `str`  | `"png"` | `"png"` (lossless) or `"jpeg"` (lossy, smaller).                         |
| `full_page`    | `bool` | `False` | Capture the entire scrollable page instead of just the current viewport. |

`path` is an optional string, default `None`; when supplied it replaces the inline
image with a file artifact reference.

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "image_base64": "<base64 string>",
  "image_format": "png",
  "width": 1280,
  "height": 720
}
```

`width` and `height` are `null` when image processing is unavailable. With
`path`, the data contains that path instead of `image_base64`; parent directories
must already exist. The image is still resized before saving.

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — `image_format` is not `"png"` or `"jpeg"`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_screenshot", "arguments": { "instance": "main", "image_format": "jpeg" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "image_base64": "/9j/4AAQ...",
    "image_format": "jpeg",
    "width": 1280,
    "height": 720
  }
}
```

**Notes** — When PIL/Pillow is installed, oversized images are automatically downscaled so the longest side is at most 1568 px (the server's image-size convention). The `width` and `height` fields in the response reflect the final, possibly downscaled dimensions. Prefer `browser_snapshot` for most inspection tasks; screenshots are most useful for visual debugging or when the accessibility tree does not carry enough detail.

## browser_console_messages { #browser_console_messages }

Read a bounded page of recent console messages retained for the instance.

**Signature**

```python
async def browser_console_messages(
    instance: str, level: str | None = None, *,
    after: str | None = None, limit: int = 100, path: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                              |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------------ |
| `instance` | `str`         | —       | Instance name.                                                                                                           |
| `level`    | `str \| None` | `None`  | Filter by message type. Valid values: `"log"`, `"info"`, `"warning"`, `"error"`, `"debug"`. `None` returns all messages. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "messages": [
    {
      "type": "error",
      "text": "Uncaught ReferenceError: foo is not defined",
      "location": "https://example.com/app.js:42:8"
    },
    { "type": "log", "text": "page ready", "location": null }
  ]
}
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — `level` is not one of the recognised values

**Example**

Request:

```json
{ "name": "browser_console_messages", "arguments": { "instance": "main", "level": "error" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "messages": [
      {
        "type": "error",
        "text": "Uncaught ReferenceError: foo is not defined",
        "location": "https://example.com/app.js:42:8"
      }
    ]
  }
}
```

**Notes** — The buffer retains recent messages across pages and navigations,
evicting the oldest at its configured capacity. See [pagination and export](#event-pagination-and-export). Uncaught page errors are captured as `type="error"` entries with `location=null`. Useful for diagnosing JavaScript errors or confirming page-side logging without opening DevTools.

## browser_network_requests { #browser_network_requests }

Read a bounded page of recent network request states retained for the instance.

**Signature**

```python
async def browser_network_requests(
    instance: str,
    url_filter: str | None = None,
    *,
    static: bool = False,
    after: str | None = None,
    limit: int = 100,
    path: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name         | Type          | Default | Description                                                                                                                                          |
| ------------ | ------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance`   | `str`         | —       | Instance name.                                                                                                                                       |
| `url_filter` | `str \| None` | `None`  | Python regular expression. Only requests whose URL matches are returned. Applied after the static filter. An invalid regex returns `invalid_params`. |
| `static`     | `bool`        | `False` | When `False` (default), static asset requests (image, font, stylesheet, media, manifest) are filtered out. Pass `True` to include them.              |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "requests": [
    {
      "url": "https://api.example.com/data",
      "method": "GET",
      "status": 200,
      "resource_type": "fetch",
      "failure": null
    },
    {
      "url": "https://api.example.com/submit",
      "method": "POST",
      "status": null,
      "resource_type": "fetch",
      "failure": "net::ERR_CONNECTION_REFUSED"
    }
  ]
}
```

`status` is `null` until the response arrives or if it never does. `failure` is `null` on success or while a request is still pending.

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — `url_filter` is not a valid regular expression

**Example**

Request:

```json
{ "name": "browser_network_requests", "arguments": { "instance": "main", "url_filter": "/api/" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "requests": [
      {
        "url": "https://example.com/api/users",
        "method": "GET",
        "status": 200,
        "resource_type": "fetch",
        "failure": null
      }
    ]
  }
}
```

**Notes** — The buffer retains recent requests across pages and navigations;
old records are evicted. See [pagination and export](#event-pagination-and-export). By default, static resource types (image, font, stylesheet, media, manifest) are filtered out to reduce noise; pass `static=True` to include everything. Useful for verifying API calls were made, checking redirect chains, or diagnosing network errors during page load.

## Event pagination and export

Console and network queries accept these optional arguments:

| Parameter | Default | Meaning                                                                                                       |
| --------- | ------- | ------------------------------------------------------------------------------------------------------------- |
| `after`   | `None`  | A cursor from this same instance and event stream. Omit it to start at the oldest retained entry.             |
| `limit`   | `100`   | Maximum matching entries to return, from 1 to 500.                                                            |
| `path`    | `None`  | Save this JSON page to a server-side file instead of returning inline entries. Parent directories must exist. |

Each entry adds a monotonic `sequence`, UTC `timestamp`, and `page_id` identifying
its source tab. Network entries also have a stable `request_id`. A response or
failure updates that request with a new sequence and timestamp; consumers should
upsert by `request_id`. A pending request evicted before its response arrives is
not brought back into the retained buffer.

Each result includes `next_cursor`, `has_more`, `retained_count`, `dropped_count`,
and `retention_lost`. Reuse `next_cursor` as `after` with the same filters. Cursors
are specific to an instance lifetime and event stream; invalid or foreign cursors
return `invalid_params`. `retention_lost` means records after the requested cursor
have already been evicted. Filtered-out records are not counted as dropped.

The buffer holds at most `BROWSER_MCP_EVENT_BUFFER_SIZE` entries per stream
(default 1000). Individual string fields are capped at 4096 characters; shortened
fields are listed in `truncated_fields`. This is recent diagnostic evidence, not
a complete network archive or response-body capture. Exporting does not restore
evicted records or shortened fields.

When `path` is provided, the file contains the selected `messages` or `requests`
plus pagination metadata. The returned data contains `path`, `count`, and the
same pagination metadata, without inline entries. Artifacts refer to files on
the server; see [framework integration](../guides/framework-integration.md).

```json
{
  "name": "browser_network_requests",
  "arguments": {
    "instance": "main",
    "limit": 50,
    "path": "/workspace/evidence/network-page.json"
  }
}
```
