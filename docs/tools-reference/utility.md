# Utility tools

Utility tools provide assorted helpers for viewport management, PDF rendering, locator generation, and tab navigation. These tools augment navigation and interaction by offering cross-cutting capabilities like responsive testing, document export, and durable selector resolution.

## browser_resize

Resize the viewport of the active page to the given pixel dimensions.

**Signature**

```python
async def browser_resize(context: str, width: int, height: int) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `width` | `int` | — | Viewport width in pixels. |
| `height` | `int` | — | Viewport height in pixels. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "width": 1920, "height": 1080 }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`

**Example**

Request:

```json
{ "name": "browser_resize", "arguments": { "context": "main", "width": 1920, "height": 1080 } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "width": 1920, "height": 1080 } }
```

**Notes** — Affects only the active page; other tabs in the context are unchanged. Changes take effect immediately. Use this to test responsive layouts or to ensure a particular viewport before taking a screenshot.

## browser_pdf_save

Render the active page as a PDF and save it to the given file path.

**Signature**

```python
async def browser_pdf_save(
    context: str,
    file_path: str | None = None,
    paper_format: str = "A4",
    *,
    landscape: bool = False,
    print_background: bool = False,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `file_path` | `str \| None` | `None` | Destination path. When omitted, defaults to `$JUSTPEN_WORKSPACE/output/evidence/page-{timestamp}.pdf`. |
| `paper_format` | `str` | `"A4"` | Paper size string: `"A4"`, `"Letter"`, `"A3"`, etc. |
| `landscape` | `bool` | `False` | Rotate to landscape orientation. |
| `print_background` | `bool` | `False` | Include CSS backgrounds in output. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "saved_to": "/workspace/output/evidence/page-1719234567.pdf", "size_bytes": 156789 }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{
  "name": "browser_pdf_save",
  "arguments": { "context": "main", "paper_format": "Letter", "landscape": true }
}
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": { "saved_to": "/workspace/output/evidence/page-1719234567.pdf", "size_bytes": 156789 }
}
```

**Notes** — Parent directories of `file_path` are created automatically. Only works in headless mode (Camoufox runs headless by default). The `landscape` and `print_background` parameters must be passed as keyword-only arguments.

## browser_generate_locator

Generate a stable, durable Playwright locator for an element.

**Signature**

```python
async def browser_generate_locator(
    context: str,
    ref: str | None = None,
    selector: str | None = None,
    element: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `ref` | `str \| None` | `None` | Ephemeral snapshot ref to resolve into a stable locator. Mutually exclusive with `selector`. |
| `selector` | `str \| None` | `None` | Raw CSS selector to pass through verbatim. Mutually exclusive with `ref`. |
| `element` | `str \| None` | `None` | Optional free-form human description (logged; not used by the implementation). |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "ref": "e12",
  "selector": null,
  "internal_selector": "get_by_role('button', name='Submit')",
  "python_syntax": "get_by_role('button', name='Submit')"
}
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `invalid_params` — neither or both of `ref`/`selector` supplied
- `modal_state_blocked`
- `stale_ref` — ref is from an older snapshot; capture a new snapshot

**Example**

Request:

```json
{
  "name": "browser_generate_locator",
  "arguments": { "context": "main", "ref": "e12", "element": "Submit button" }
}
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": {
    "ref": "e12",
    "selector": null,
    "internal_selector": "get_by_role('button', name='Submit')",
    "python_syntax": "get_by_role('button', name='Submit')"
  }
}
```

**Notes** — Exactly one of `ref` or `selector` must be provided. For `ref` mode, resolution priority is: data-testid > ARIA role+name > label > placeholder > alt text > title > text content > CSS fallback. The `internal_selector` form is suitable for use with `page.locator()` and survives navigation, making it ideal for saving durable test code or reusable workflow definitions. The `python_syntax` field provides a human-readable representation suitable for codegen.

## browser_tabs

Manage tabs (pages) within a browser context.

**Signature**

```python
async def browser_tabs(
    context: str,
    action: str,
    index: int | None = None,
    url: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `action` | `str` | — | One of `"list"`, `"new"`, `"close"`, `"select"`. |
| `index` | `int \| None` | `None` | Tab index (required for `"close"` and `"select"`). |
| `url` | `str \| None` | `None` | URL to navigate to when opening a new tab (only for `"new"`). |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape depends on `action`:

- `"list"`: `{"tabs": [{"index": 0, "url": "https://example.com"}, ...]}`
- `"new"`: `{"index": 1, "url": "https://example.com"}`
- `"close"`: `{"closed_index": 1}`
- `"select"`: `{"selected_index": 1}`

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `invalid_params` — unrecognized action, or index missing/out of range

**Example**

Request (list):

```json
{ "name": "browser_tabs", "arguments": { "context": "main", "action": "list" } }
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": { "tabs": [{"index": 0, "url": "https://example.com"}, {"index": 1, "url": "https://example.com/page2"}] }
}
```

Request (new):

```json
{
  "name": "browser_tabs",
  "arguments": { "context": "main", "action": "new", "url": "https://example.com/page2" }
}
```

Response:

```json
{
  "status": "success",
  "context": "main",
  "data": { "index": 1, "url": "https://example.com/page2" }
}
```

**Notes** — The `action` parameter is required and must be one of the four values listed above. For `"close"` and `"select"`, the `index` parameter must be a valid tab index (0-based). The active page index is automatically adjusted when a tab is closed to ensure the context always has an active page.
