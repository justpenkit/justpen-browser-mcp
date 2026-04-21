# Cookies and storage tools

Cookie jar and localStorage helpers let you manage browser storage state — setting and clearing cookies and localStorage across origins. Both tools affect the context's stored state immediately. To persist cookies and localStorage across sessions, call `browser_export_context_state` afterward.

## browser_get_cookies

Return cookies stored in the context, optionally filtered by URL and name.

**Signature**

```python
async def browser_get_cookies(context: str, urls: list[str] | None = None, name: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `urls` | `list[str] \| None` | `None` | List of full URLs to filter cookies by domain/path rules. `None` returns all cookies. |
| `name` | `str \| None` | `None` | Exact cookie name to filter by (applied after URL filtering). |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "cookies": [{"name": "sessionid", "value": "abc123", "domain": ".example.com", "path": "/", "expires": 1735689600, "httpOnly": true, "secure": true, "sameSite": "Strict"}] }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_get_cookies", "arguments": { "context": "main", "urls": ["https://example.com"] } }
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": {
    "cookies": [
      {
        "name": "sessionid",
        "value": "abc123",
        "domain": ".example.com",
        "path": "/",
        "expires": 1735689600,
        "httpOnly": true,
        "secure": true,
        "sameSite": "Strict"
      }
    ]
  }
}
```

**Notes** — When both `urls` and `name` are provided, filtering is applied in order: URLs first, then exact name match. When `name` is given but no cookies match, the result is an empty list (not an error). Cookies applicable to the given URLs are determined by matching domain and path rules per the cookie RFC.

## browser_set_cookies

Add or update cookies on the context using Playwright cookie format.

**Signature**

```python
async def browser_set_cookies(context: str, cookies: list[dict[str, Any]]) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `cookies` | `list[dict[str, Any]]` | — | List of cookie dicts. Each must have at minimum `name` and `value`. Must also include either (`domain` + `path`) or `url`. Optional fields: `path` (default `"/"`), `expires` (Unix timestamp), `httpOnly`, `secure`, `sameSite` (`"Strict"`, `"Lax"`, `"None"`). |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "set_count": 2 }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `invalid_params` — cookie has neither `domain` nor `url` and no active page exists to default from

**Example**

Request:

```json
{
  "name": "browser_set_cookies",
  "arguments": {
    "context": "main",
    "cookies": [
      {
        "name": "sessionid",
        "value": "xyz789",
        "domain": ".example.com",
        "path": "/",
        "httpOnly": true,
        "secure": true,
        "sameSite": "Strict"
      }
    ]
  }
}
```

Response:

```json
{ "status": "success", "context": "main", "data": { "set_count": 1 } }
```

**Notes** — When a cookie has neither `domain` nor `url`, the active page's hostname is used as the default domain (if a page exists). Cookies set here take effect immediately on all pages in the context. To persist cookies across browser sessions, call `browser_export_context_state` afterward.

## browser_clear_cookies

Remove all cookies from the context across all domains.

**Signature**

```python
async def browser_clear_cookies(context: str) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "cleared": true }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_clear_cookies", "arguments": { "context": "main" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "cleared": true } }
```

**Notes** — All cookies across all domains in the context are deleted immediately. Pages currently loaded in the context are not reloaded — the deletion takes effect on the next HTTP request that would send cookies.

## browser_get_local_storage

Read localStorage for the given origin.

**Signature**

```python
async def browser_get_local_storage(context: str, origin: str, key: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `origin` | `str` | — | Fully-qualified URL including scheme (e.g. `"https://example.com"`). |
| `key` | `str \| None` | `None` | Specific key to read. `None` returns all items. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape when `key` is `None`:

```json
{ "items": { "theme": "dark", "user_id": "42" }, "origin": "https://example.com" }
```

Data shape when `key` is provided:

```json
{ "key": "theme", "value": "dark", "origin": "https://example.com" }
```

If the key does not exist, `value` is `null`:

```json
{ "key": "nonexistent", "value": null, "origin": "https://example.com" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `internal_error` — navigation to origin failed (e.g. network error, redirect to different origin)

**Example**

Request (all items):

```json
{ "name": "browser_get_local_storage", "arguments": { "context": "main", "origin": "https://example.com" } }
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": { "items": { "theme": "dark", "user_id": "42" }, "origin": "https://example.com" }
}
```

Request (specific key):

```json
{ "name": "browser_get_local_storage", "arguments": { "context": "main", "origin": "https://example.com", "key": "theme" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "key": "theme", "value": "dark", "origin": "https://example.com" } }
```

**Notes** — Opens a temporary page that navigates to the origin, reads localStorage, then closes the page — the context's active page is not disturbed. `origin` must be a fully-qualified URL including scheme; partial URLs or paths are not accepted.

## browser_set_local_storage

Set localStorage key-value pairs for the given origin.

**Signature**

```python
async def browser_set_local_storage(context: str, origin: str, items: dict[str, str]) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `origin` | `str` | — | Fully-qualified URL including scheme (e.g. `"https://example.com"`). |
| `items` | `dict[str, str]` | — | Key-value pairs to set. All values must be strings. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "set_count": 2, "origin": "https://example.com" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `internal_error` — navigation to origin failed

**Example**

Request:

```json
{
  "name": "browser_set_local_storage",
  "arguments": {
    "context": "main",
    "origin": "https://example.com",
    "items": { "theme": "dark", "user_id": "42" }
  }
}
```

Response:

```json
{ "status": "success", "context": "main", "data": { "set_count": 2, "origin": "https://example.com" } }
```

**Notes** — Opens a temporary page that navigates to the origin, sets each item via `localStorage.setItem`, then closes the page — the context's active page is not disturbed. All values must be strings because localStorage only stores strings. To persist localStorage across browser sessions, call `browser_export_context_state` afterward.

## browser_clear_local_storage

Clear localStorage entries for an origin or for the currently active page.

**Signature**

```python
async def browser_clear_local_storage(context: str, origin: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `origin` | `str \| None` | `None` | Fully-qualified URL including scheme to clear. When omitted, clears localStorage on the currently active page directly. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "cleared": true, "origin": "https://example.com" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `internal_error` — navigation to origin failed

**Example**

Request (with origin):

```json
{ "name": "browser_clear_local_storage", "arguments": { "context": "main", "origin": "https://example.com" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "cleared": true, "origin": "https://example.com" } }
```

Request (active page shortcut):

```json
{ "name": "browser_clear_local_storage", "arguments": { "context": "main" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "cleared": true, "origin": "https://example.com/page" } }
```

**Notes** — When `origin` is provided, a temporary page navigates to that origin, clears localStorage, then closes — the context's active page is not disturbed. When `origin` is omitted, localStorage is cleared on the active page directly with no navigation (a shortcut for when you are already on the origin whose storage you want to clear). The `origin` field in the response always reflects which origin's storage was actually cleared.
