# Lifecycle tools

Lifecycle tools manage the full lifespan of browser contexts — creating isolated sessions, persisting and restoring authentication state, querying what is alive, and tearing sessions down cleanly. Reach for these tools at the boundaries of a workflow: `browser_create_context` to open a session, `browser_export_context_state` / `browser_load_context_state` to save and replay login state across runs, `browser_list_contexts` to inspect what is currently active, and `browser_destroy_context` to shut everything down when the work is done.

## browser_create_context

Create a new isolated browser context (like a fresh browser profile).

**Signature**

```python
async def browser_create_context(context: str, state_path: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Name for the new context. |
| `state_path` | `str \| None` | `None` | Optional path to a Playwright storage-state JSON file to pre-load cookies and localStorage. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "created": true }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_already_exists`
- `state_file_not_found`
- `invalid_state_file`

**Example**

Request:

```json
{ "name": "browser_create_context", "arguments": { "context": "main" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "created": true } }
```

**Notes** — No pages exist immediately after creation. The first tool that needs a page (e.g. `browser_navigate`) creates one implicitly. When `state_path` is supplied the file must be valid Playwright storage-state JSON produced by `browser_export_context_state`.

## browser_load_context_state

Replace the context's cookies and localStorage in-place from a saved state file without recreating the context.

**Signature**

```python
async def browser_load_context_state(context: str, state_path: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `state_path` | `str` | — | Path to a Playwright storage-state JSON file produced by `browser_export_context_state`. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "loaded_from": "/path/to/state.json" }
```

`failed_origins` is included only when non-empty — it lists origins whose localStorage could not be restored.

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `state_file_not_found`
- `invalid_state_file`

**Example**

Request:

```json
{ "name": "browser_load_context_state", "arguments": { "context": "main", "state_path": "/tmp/session.json" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "loaded_from": "/tmp/session.json" } }
```

**Notes** — Unlike `browser_create_context(state_path=...)`, this tool does not recreate the context. The active page and all tabs remain open; only the cookie jar and localStorage are replaced.

## browser_export_context_state

Write the context's current cookies and localStorage to a JSON file.

**Signature**

```python
async def browser_export_context_state(context: str, state_path: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `state_path` | `str` | — | Destination file path. Parent directories are created automatically. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "saved_to": "/absolute/path/to/state.json" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_export_context_state", "arguments": { "context": "main", "state_path": "/tmp/session.json" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "saved_to": "/tmp/session.json" } }
```

## browser_destroy_context

Close the context and remove it from the server's registry.

**Signature**

```python
async def browser_destroy_context(context: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "destroyed": true }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_destroy_context", "arguments": { "context": "main" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "destroyed": true } }
```

**Notes** — If this was the last active context, Camoufox is automatically shut down; the next `browser_create_context` will re-launch it lazily. To close a single tab while keeping the context alive, use `browser_close` instead.

## browser_list_contexts

List all active browser contexts with summary information.

**Signature**

```python
async def browser_list_contexts() -> dict[str, Any]
```

**Parameters**

*No parameters.*

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "contexts": [
    { "context": "main", "page_count": 1, "active_url": "https://example.com", "cookie_count": 3 }
  ]
}
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `internal_error`

**Example**

Request:

```json
{ "name": "browser_list_contexts", "arguments": {} }
```

Response:

```json
{
  "status": "success",
  "context": null,
  "data": {
    "contexts": [
      { "context": "main", "page_count": 2, "active_url": "https://example.com", "cookie_count": 5 }
    ]
  }
}
```

**Notes** — Never raises a domain error — if no contexts exist the list is empty. `context` in the envelope is `null` because this is a server-level tool that does not target a specific context.
