---
description: Miscellaneous helpers and diagnostic tools.
---

# Utility { #_top }

Utility tools resize viewports, generate reusable locators, and manage tabs. The PDF compatibility tool reports that this Firefox/Camoufox server does not support PDF generation.

Examples below focus on tool-specific data. Registered tools also return the shared [operation metadata and error fields](../concepts/response-envelope.md).

Optional `page_id` selects a live page without changing the selected tab; an invalid
explicit target returns `page_not_found`. Frame-capable calls also accept `frame_id`
and return `frame_not_found` for a detached or foreign frame. Omitted targets retain
existing behavior. See [explicit targeting](../concepts/instances-isolation.md#explicit-page-targets).

## browser_resize { #browser_resize }

Resize the viewport of the active page to the given pixel dimensions.

**Signature**

```python
async def browser_resize(instance: str, width: int, height: int, *, page_id: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                         |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                      |
| `width`    | `int`         | —       | Viewport width in pixels.                                                                                           |
| `height`   | `int`         | —       | Viewport height in pixels.                                                                                          |
| `page_id`  | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "width": 1920, "height": 1080 }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`

**Example**

Request:

```json
{ "name": "browser_resize", "arguments": { "instance": "main", "width": 1920, "height": 1080 } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "width": 1920, "height": 1080 } }
```

**Notes** — Affects only the active page; other tabs in the instance are unchanged. Changes take effect immediately. Use this to test responsive layouts or to ensure a particular viewport before taking a screenshot.

## browser_pdf_save { #browser_pdf_save }

Report `unsupported_capability`: PDF generation requires Chromium and is unavailable on this Firefox/Camoufox server.

**Signature**

```python
async def browser_pdf_save(
    instance: str,
    file_path: str | None = None,
    paper_format: str = "A4",
    *,
    landscape: bool = False,
    print_background: bool = False,
) -> dict[str, Any]
```

**Parameters**

| Name               | Type          | Default | Description                                     |
| ------------------ | ------------- | ------- | ----------------------------------------------- |
| `instance`         | `str`         | —       | Instance name.                                  |
| `file_path`        | `str \| None` | `None`  | Retained for compatibility; no file is written. |
| `paper_format`     | `str`         | `"A4"`  | Retained for compatibility; unused.             |
| `landscape`        | `bool`        | `False` | Retained for compatibility; unused.             |
| `print_background` | `bool`        | `False` | Retained for compatibility; unused.             |

**Returns** — an error [response envelope](../concepts/response-envelope.md); there is no PDF success result on this server.

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `unsupported_capability` — PDF generation requires Chromium

**Example**

Request:

```json
{
  "name": "browser_pdf_save",
  "arguments": { "instance": "main", "paper_format": "Letter", "landscape": true }
}
```

Response:

```json
{
  "status": "error",
  "instance": "main",
  "error_type": "unsupported_capability",
  "message": "PDF generation is not supported by Firefox/Camoufox. Use browser_screenshot for visual evidence."
}
```

**Notes** — The tool name and parameters remain available for existing clients. It does not create directories, write a file, or launch another browser. Use [browser_screenshot](inspection.md#browser_screenshot) for visual evidence.

## browser_generate_locator { #browser_generate_locator }

Generate a stable, durable Playwright locator for an element.

**Signature**

```python
async def browser_generate_locator(
    instance: str,
    ref: str | None = None,
    selector: str | None = None,
    element: str | None = None,
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                                         |
| ---------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                                                      |
| `ref`      | `str \| None` | `None`  | Ephemeral snapshot ref to resolve into a stable locator. Mutually exclusive with `selector`.                        |
| `selector` | `str \| None` | `None`  | Raw CSS selector to pass through verbatim. Mutually exclusive with `ref`.                                           |
| `element`  | `str \| None` | `None`  | Optional free-form human description (logged; not used by the implementation).                                      |
| `page_id`  | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `frame_id` | `str \| None` | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                          |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "ref": "e12",
  "selector": null,
  "internal_selector": "internal:role=button[name=\"Submit\"i]",
  "python_syntax": "get_by_role(\"button\", name='Submit')"
}
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — neither or both of `ref`/`selector` supplied
- `modal_state_blocked`
- `stale_ref` — ref is from an older snapshot; capture a new snapshot

**Example**

Request:

```json
{
  "name": "browser_generate_locator",
  "arguments": { "instance": "main", "ref": "e12", "element": "Submit button" }
}
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "ref": "e12",
    "selector": null,
    "internal_selector": "internal:role=button[name=\"Submit\"i]",
    "python_syntax": "get_by_role(\"button\", name='Submit')"
  }
}
```

**Notes** — Exactly one of `ref` or `selector` must be provided. For `ref` mode, resolution priority is: data-testid > ARIA role+name > label > placeholder > alt text > title > text content > CSS fallback. The `internal_selector` field is a raw Playwright engine selector (e.g. `internal:role=button[name="Submit"i]`) suitable for use directly with `page.locator()`, and survives navigation, making it ideal for saving durable test code or reusable workflow definitions. The `python_syntax` field converts that same resolution into the equivalent Python API call (e.g. `get_by_role("button", name='Submit')`) for codegen output — the two fields describe the same element via different syntaxes, they are not identical strings. In `selector` mode, `internal_selector` preserves the supplied selector and `python_syntax` wraps it in `locator(...)`; for `selector="#main"`, these are `"#main"` and `"locator('#main')"` respectively.

Complex selectors use `locator(...)` in `python_syntax` when a shorter Python call would lose meaning. Role filters, `nth` selection, and frame chains remain intact. For example, `internal:role=button[name="Same"i] >> nth=1` stays a raw locator that selects the second matching button.

Generated locator results also include the resolved `page_id` and `frame_id`. For an explicit frame, the selector and Python syntax are frame-local; select that frame before replaying them.

## browser_tabs { #browser_tabs }

Manage tabs (pages) within a browser instance.

**Signature**

```python
async def browser_tabs(
    instance: str,
    action: str,
    index: int | None = None,
    url: str | None = None,
    page_id: str | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type          | Default | Description                                                                                  |
| ---------- | ------------- | ------- | -------------------------------------------------------------------------------------------- |
| `instance` | `str`         | —       | Instance name.                                                                               |
| `action`   | `str`         | —       | One of `"list"`, `"new"`, `"close"`, `"select"`.                                             |
| `index`    | `int \| None` | `None`  | Current zero-based tab index for `"close"` or `"select"`; mutually exclusive with `page_id`. |
| `url`      | `str \| None` | `None`  | URL to navigate to when opening a new tab (only for `"new"`).                                |
| `page_id`  | `str \| None` | `None`  | Stable tab ID for `"close"` or `"select"`; mutually exclusive with `index`.                  |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape depends on `action`:

- `"list"`: `{"tabs": [{"index": 0, "url": "https://example.com", "page_id": "page-1"}, ...]}`
- `"new"`: `{"index": 1, "url": "https://example.com", "page_id": "page-2"}`
- `"close"`: `{"closed_index": 1, "page_id": "page-2"}`
- `"select"`: `{"selected_index": 1, "page_id": "page-2"}`

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — unrecognized action, missing or unknown target, conflicting `index`/`page_id`, or `page_id` supplied for `"list"`/`"new"`
- `modal_state_blocked` — `"new"` was requested while a modal is pending

**Example**

Request (list):

```json
{ "name": "browser_tabs", "arguments": { "instance": "main", "action": "list" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "tabs": [
      { "index": 0, "url": "https://example.com", "page_id": "page-1" },
      { "index": 1, "url": "https://example.com/page2", "page_id": "page-2" }
    ]
  }
}
```

Request (new):

```json
{
  "name": "browser_tabs",
  "arguments": { "instance": "main", "action": "new", "url": "https://example.com/page2" }
}
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "index": 1, "url": "https://example.com/page2", "page_id": "page-2" }
}
```

Request (select by stable ID):

```json
{ "name": "browser_tabs", "arguments": { "instance": "main", "action": "select", "page_id": "page-2" } }
```

**Notes** — For `"close"` and `"select"`, supply either a current `index` or a `page_id` returned by this tool. IDs are opaque and remain stable for a page's lifetime, including when other tabs close and indices shift. IDs are not reusable after that page or instance is destroyed. The strings above are illustrative.

`"new"` selects the page created by that request, even if another popup opens while its URL loads. If loading fails or the request is cancelled, the tool attempts a bounded close of the newly created tab while preserving the original failure. Inspect the tab list after an error if the browser could not complete cleanup. Closing a non-active tab preserves the active page; closing the active tab selects the next remaining tab, or the previous one at the end of the list. Closing the last tab keeps the instance alive with no open pages.

Operation metadata for `"new"`, `"select"`, and `"close"` identifies the page acted on, including the closed page for `"close"`.

## browser_frames { #browser_frames }

Enumerate attached frames in one live page without changing the selected tab.

```python
async def browser_frames(instance: str, *, page_id: str | None = None) -> dict[str, Any]
```

Omitting `page_id` uses the selected page. The result contains `page_id`,
`main_frame_id`, and `frames`; each frame has `frame_id`, nullable
`parent_frame_id`, `name`, `url`, and boolean `is_main` (true only for the main frame). Frame IDs survive navigation while the same
Frame remains attached. Detach expires the ID; replacement creates a new ID.
Errors include `instance_not_found`, `page_not_found`, and `frame_not_found`.

```json
{
  "status": "success", "instance": "main",
  "data": {
    "page_id": "page-uuid", "main_frame_id": "main-frame-uuid",
    "frames": [
      {"frame_id": "main-frame-uuid", "parent_frame_id": null, "is_main": true, "name": "", "url": "https://example.com"},
      {"frame_id": "child-frame-uuid", "parent_frame_id": "main-frame-uuid", "is_main": false, "name": "checkout", "url": "https://payments.example.com"}
    ]
  }
}
```

Use the returned IDs with [snapshots and frame-local refs](../concepts/refs-snapshots.md#iframe--child-frame-refs).
