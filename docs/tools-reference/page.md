# Page tools

Page tools manage individual tabs within a browser context. Closing a page leaves the context alive — use `browser_destroy_context` to tear down the whole session.

## browser_close

Close the active page (tab) in the context while keeping the context alive.

**Signature**

```python
async def browser_close(context: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "closed": true }
```

When there are no open pages, the shape is instead:

```json
{ "closed": false, "reason": "no open pages" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_close", "arguments": { "context": "main" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "closed": true } }
```

**Notes** — Only the currently active page is closed; other tabs remain open. After close, the previous tab becomes active — matching `browser_tabs(action="close")` behavior. Use `browser_destroy_context` to tear down the entire browser session.
