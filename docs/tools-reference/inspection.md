# Inspection tools

Inspection tools let you observe the current state of a browser instance — its accessibility tree, visual appearance, console output, and network activity. `browser_snapshot` is the primary tool: it returns an LLM-friendly YAML accessibility tree where every interactive element carries a `[ref=eN]` tag that other tools consume to click, type, or drag without pixel coordinates. These refs are session-scoped and invalidated by navigation; see [Refs & snapshots](../concepts/refs-snapshots.md) for a full explanation of the ref lifecycle. Use `browser_screenshot` when visual fidelity matters, and `browser_console_messages` / `browser_network_requests` for debugging JavaScript errors and API calls.

## browser_snapshot

Capture an accessibility snapshot of the active page in LLM-friendly YAML.

**Signature**

```python
async def browser_snapshot(instance: str, selector: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instance` | `str` | — | Instance name. |
| `selector` | `str \| None` | `None` | Optional CSS or aria selector to scope the snapshot to a subtree. When provided, refs are **not** included in the output. |

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

**Notes** — Default mode (`selector=None`) uses the internal `snapshotForAI` channel and annotates every interactive element with `[ref=eN]`. Pass a ref value to `browser_click`, `browser_type`, or other interaction tools to act on that element. Refs are session-scoped and invalidated by navigation or page reload — call `browser_snapshot` again after any navigation to obtain fresh refs. Selector mode calls `Locator.aria_snapshot` on the matching element and returns plain aria YAML without refs; use it for scoped inspection of a known subtree when you do not need to interact with the results.

## browser_screenshot

Take a visual screenshot of the active page and return it as base64.

**Signature**

```python
async def browser_screenshot(
    instance: str,
    image_format: str = "png",
    *,
    full_page: bool = False,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instance` | `str` | — | Instance name. |
| `image_format` | `str` | `"png"` | `"png"` (lossless) or `"jpeg"` (lossy, smaller). |
| `full_page` | `bool` | `False` | Capture the entire scrollable page instead of just the current viewport. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "image_base64": "<base64 string>",
  "image_format": "png",
  "width": 1280,
  "height": 720
}
```

`width` and `height` are `null` when PIL/Pillow is unavailable.

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

**Notes** — When PIL/Pillow is installed, oversized images are automatically downscaled so the longest side is at most 1568 px (Claude's vision input limit). The `width` and `height` fields in the response reflect the final, possibly downscaled dimensions. Prefer `browser_snapshot` for most inspection tasks; screenshots are most useful for visual debugging or when the accessibility tree does not carry enough detail.

## browser_console_messages

Return all console messages collected since the instance was created.

**Signature**

```python
async def browser_console_messages(instance: str, level: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instance` | `str` | — | Instance name. |
| `level` | `str \| None` | `None` | Filter by message type. Valid values: `"log"`, `"info"`, `"warning"`, `"error"`, `"debug"`. `None` returns all messages. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "messages": [
    { "type": "error", "text": "Uncaught ReferenceError: foo is not defined", "location": "https://example.com/app.js:42:8" },
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
      { "type": "error", "text": "Uncaught ReferenceError: foo is not defined", "location": "https://example.com/app.js:42:8" }
    ]
  }
}
```

**Notes** — The buffer is cumulative and never cleared — it includes all messages across all pages and all navigations in the instance (not just since the last navigation). Uncaught page errors are captured as `type="error"` entries with `location=null`. Useful for diagnosing JavaScript errors or confirming page-side logging without opening DevTools.

## browser_network_requests

Return all network requests collected since the instance was created.

**Signature**

```python
async def browser_network_requests(
    instance: str,
    url_filter: str | None = None,
    *,
    static: bool = False,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instance` | `str` | — | Instance name. |
| `url_filter` | `str \| None` | `None` | Python regular expression. Only requests whose URL matches are returned. Applied after the static filter. An invalid regex returns `invalid_params`. |
| `static` | `bool` | `False` | When `False` (default), static asset requests (image, font, stylesheet, media, manifest) are filtered out. Pass `True` to include them. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "requests": [
    { "url": "https://api.example.com/data", "method": "GET", "status": 200, "resource_type": "fetch", "failure": null },
    { "url": "https://api.example.com/submit", "method": "POST", "status": null, "resource_type": "fetch", "failure": "net::ERR_CONNECTION_REFUSED" }
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
      { "url": "https://example.com/api/users", "method": "GET", "status": 200, "resource_type": "fetch", "failure": null }
    ]
  }
}
```

**Notes** — The buffer is cumulative and never cleared — it covers all requests across all pages and all navigations in the instance. By default, static resource types (image, font, stylesheet, media, manifest) are filtered out to reduce noise; pass `static=True` to include everything. Useful for verifying API calls were made, checking redirect chains, or diagnosing network errors during page load.
