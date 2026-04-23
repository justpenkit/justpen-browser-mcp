# Page tools

Page tools manage individual tabs within a browser instance. Closing a page leaves the instance alive — use `browser_destroy_instance` to tear down the whole session.

## browser_close

Close the active page (tab) in the instance while keeping the instance alive.

**Signature**

```python
async def browser_close(instance: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instance` | `str` | — | Instance name. |

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

**Notes** — Only the currently active page is closed; other tabs remain open. After close, the previous tab becomes active — matching `browser_tabs(action="close")` behavior. Use `browser_destroy_instance` to tear down the entire browser session.
