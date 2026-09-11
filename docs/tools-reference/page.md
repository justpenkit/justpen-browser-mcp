---
description: "Per-page operations: browser_close."
---

# Page { #_top }

Page tools manage individual tabs within a browser instance. This page currently documents `browser_close` (closing the active tab). Closing a page leaves the instance alive — use `browser_destroy_instance` to tear down the whole session. Listing, focusing, and selecting tabs live under `browser_tabs` — see [Utility](utility.md#browser_tabs).

## browser_close { #browser_close }

Close the active page (tab) in the instance while keeping the instance alive.

**Signature**

```python
async def browser_close(instance: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description    |
| ---------- | ----- | ------- | -------------- |
| `instance` | `str` | —       | Instance name. |

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
