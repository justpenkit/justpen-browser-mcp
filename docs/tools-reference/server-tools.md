# Server tools

Server tools report server-level state without targeting a specific context. They are safe to call when no browser is running.

## browser_status

Report server health without triggering a browser launch.

**Signature**

```python
async def browser_status() -> dict[str, Any]
```

**Parameters**

*No parameters.*

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "browser_running": true,
  "active_context_count": 1,
  "active_contexts": [ { "context": "main" } ]
}
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `internal_error`

**Example**

Request:

```json
{ "name": "browser_status", "arguments": {} }
```

Response:

```json
{
  "status": "success",
  "context": null,
  "data": {
    "browser_running": true,
    "active_context_count": 1,
    "active_contexts": [ { "context": "main" } ]
  }
}
```

**Notes** — This is the only tool safe to call before the browser is launched or after it has shut down — all other tools require an active context. `context` in the envelope is `null` because this is a server-level tool that does not target a specific context.
