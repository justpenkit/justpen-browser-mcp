---
description: "Per-page operations: browser_close."
---

# Page { #_top }

Page tools manage individual tabs within a browser instance. This page currently documents `browser_close` (closing the active tab). Closing a page leaves the instance alive — use `browser_destroy_instance` to tear down the whole session. Listing, focusing, and selecting tabs live under `browser_tabs` — see [Utility](utility.md#browser_tabs).

Examples below focus on tool-specific data. Registered tools also return the shared [operation metadata and error fields](../concepts/response-envelope.md).

Optional `page_id` selects a live page without changing the selected tab; an invalid
explicit target returns `page_not_found`. Frame-capable calls also accept `frame_id`
and return `frame_not_found` for a detached or foreign frame. Omitted targets retain
existing behavior. See [explicit targeting](../concepts/instances-isolation.md#explicit-page-targets).

## browser_close { #browser_close }

Close the active page (tab) in the instance while keeping the instance alive.

**Signature**

```python
async def browser_close(instance: str, *, page_id: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                         |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                      |
| `page_id`  | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "closed": true }
```

When there are no open pages, the shape is instead:

```json
{ "closed": false, "reason": "no open pages" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`

**Example**

Request:

```json
{ "name": "browser_close", "arguments": { "instance": "main" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "closed": true } }
```

**Notes** — Only the currently active page is closed; other tabs remain open. The next remaining tab becomes active, or the previous tab when closing the last tab in the list. This matches `browser_tabs(action="close")` when it closes the active tab. Use `browser_destroy_instance` to tear down the entire browser session.

The active page is tracked by page identity, so closing another tab does not change which page this tool targets. Operation metadata identifies the closed page. To close a specific page without selecting it first, use `browser_tabs(action="close", page_id=...)` with an ID from the tab list. Closing the last open page leaves the instance alive; the next operation that requires a page can create a blank page.
