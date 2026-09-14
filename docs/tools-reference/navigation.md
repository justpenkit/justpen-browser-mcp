---
description: Navigate, reload, go back/forward, and open URLs.
---

# Navigation { #_top }

Navigation tools control where the active page points and how long the agent waits before proceeding. Use `browser_navigate` to load a URL into the current tab, `browser_navigate_back` to step back through browser history, and `browser_wait_for` to pause until a piece of text appears, disappears, or a fixed delay expires. Reach for these tools any time you need to move between pages, handle redirect flows, or synchronise with dynamic content that takes time to render.

Examples below focus on tool-specific data. Registered tools also return the shared [operation metadata and error fields](../concepts/response-envelope.md).

Optional `page_id` selects a live page without changing the selected tab; an invalid
explicit target returns `page_not_found`. Frame-capable calls also accept `frame_id`
and return `frame_not_found` for a detached or foreign frame. Omitted targets retain
existing behavior. See [explicit targeting](../concepts/instances-isolation.md#explicit-page-targets).

## browser_navigate { #browser_navigate }

Navigate the active page in the given instance to a URL.

**Signature**

```python
async def browser_navigate(instance: str, url: str, *, page_id: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                         |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                      |
| `url`      | `str`         | —       | Destination URL.                                                                                                    |
| `page_id`  | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "url": "https://example.com/page", "title": "Page Title" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `navigation_failed`
- `navigation_timeout`

**Example**

Request:

```json
{ "name": "browser_navigate", "arguments": { "instance": "main", "url": "https://example.com" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "url": "https://example.com/", "title": "Example Domain" }
}
```

**Notes** — URL normalisation: `localhost[:PORT]` and bare IPv4 addresses receive an `http://` scheme; schemeless hostnames containing a dot receive `https://`, including hostnames with a port. Explicit schemes such as `data:`, `javascript:`, and `about:` are preserved.

When an observed download event matches the navigation or its redirect chain, the response data includes `"download": true` and, when the handle was retained, `download_id`, alongside the current page's `url` and `title`. A URL or error message containing the word `download` alone does not indicate success. This response confirms the download was triggered; it does not report a completed file save. After navigation changes the document, refs obtained from `browser_snapshot` are invalidated — take a fresh snapshot before referencing page elements.

## browser_navigate_back { #browser_navigate_back }

Navigate back one step in the browser history for the active page.

**Signature**

```python
async def browser_navigate_back(instance: str, *, page_id: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                         |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                      |
| `page_id`  | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "url": "https://example.com/" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `navigation_failed`
- `navigation_timeout`

**Example**

Request:

```json
{ "name": "browser_navigate_back", "arguments": { "instance": "main" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "url": "https://example.com/" } }
```

**Notes** — If there is no history entry to go back to, the page stays where it is and the returned `url` reflects the current location. After a successful back-navigation, previous snapshot refs are invalidated.

## browser_wait_for { #browser_wait_for }

Wait for text to appear, text to disappear, or a fixed duration.

**Signature**

```python
async def browser_wait_for(
    instance: str,
    text: str | None = None,
    text_gone: str | None = None,
    time: float | None = None,
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name        | Type            | Default | Description                                                                                                         |
| ----------- | --------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance`  | `str`           | —       | Instance name.                                                                                                      |
| `text`      | `str \| None`   | `None`  | Wait until at least one matching element is visible on the page.                                                    |
| `text_gone` | `str \| None`   | `None`  | Wait until no matching element is visible on the page.                                                              |
| `time`      | `float \| None` | `None`  | Seconds to wait unconditionally (capped at 30).                                                                     |
| `page_id`   | `str \| None`   | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `frame_id`  | `str \| None`   | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                          |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "waited_for": "2.0s, text='Dashboard'" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `invalid_params`
- `wait_timeout`

**Example**

Request:

```json
{ "name": "browser_wait_for", "arguments": { "instance": "main", "text": "Dashboard" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "waited_for": "text='Dashboard'" } }
```

**Notes** — At least one of `text`, `text_gone`, or `time` must be provided; omitting all three returns an `invalid_params` error immediately. When multiple conditions are given they are evaluated in order: `time` first, then `text_gone`, then `text`.

Text conditions use substring matches in the active page's main frame. Hidden duplicates do not mask a visible match. `text_gone` requires every matching element to be hidden or removed; a hidden first match alone is insufficient.

## Action observations

Pass optional `wait_for` to click, type, fill-form, select-option, hover, drag,
press-key, and coordinate mouse click/drag/wheel. `WaitForSpec` in the signatures
means one JSON object selected by `kind`:

| `kind`     | Required fields | Optional fields                                                | Match                                                                                                    |
| ---------- | --------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `response` | `url`           | `method`, `status` (100–599)                                   | Exact response URL; its request must begin after observation is armed.                                   |
| `url`      | `url`           | —                                                              | A subsequent navigation of the resolved frame reaches the exact URL, including same-document navigation. |
| `element`  | `selector`      | `state`: `attached`, `detached`, `visible` (default), `hidden` | DOM condition after the action.                                                                          |
| `text`     | `text`          | `state`: `visible` (default), `hidden`                         | Literal text condition after the action.                                                                 |
| `popup`    | —               | —                                                              | A popup opened by the target page.                                                                       |
| `download` | —               | —                                                              | A download emitted by the target page.                                                                   |

All kinds accept positive integer `timeout_ms` (default 10000); unknown fields
are rejected. Response URLs are exact strings, not patterns. Method matching is
case-normalized. An explicit `frame_id` narrows response matching to that frame;
otherwise responses may originate in any frame of the target page. Element/text
conditions may already hold and do not imply a transition. A response match means
headers/status arrived, not that its response body finished downloading.

The observer is armed before the action executes, so an event during the action
can satisfy it. The timeout starts after the action, and both share the existing
overall operation deadline. The action executes once. No retry, compound condition,
or automatic business-success inference is performed. When supplied, the explicit
observation replaces type/Enter's extra best-effort page-load wait.

```json
{
  "name": "browser_click",
  "arguments": {
    "instance": "checkout", "page_id": "page-uuid", "frame_id": "frame-uuid",
    "ref": "e12",
    "wait_for": {"kind": "response", "url": "https://example.com/orders", "method": "POST", "status": 201, "timeout_ms": 10000}
  }
}
```

Success retains existing action keys and adds `data.observation` with `kind`,
`matched: true`, and observed facts. Popup observations return the popup's
`page_id` without selecting it. Downloads return a `download_id` for explicit saving.
A completed action whose condition times out returns `observation_timeout` with
`data.action_completed: true`, its action result and an unmatched observation.
An outer operation deadline can return `operation_timeout` with the same completion
marker if it expired during observation. Outcome remains `unknown` and retry advice
is `inspect_state`; do not repeat a possibly successful submission automatically.
This is temporal association, not proof that the action caused a particular request.
