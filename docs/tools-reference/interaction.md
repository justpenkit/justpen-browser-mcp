---
description: Click, type, fill forms, and dispatch keyboard events.
---

# Interaction { #_top }

Interaction tools let an agent act on the page — clicking, typing, filling forms, selecting dropdown options, dragging elements, hovering, pressing keys, handling JavaScript dialogs, and completing file uploads. Reach for these tools any time a workflow requires manipulating page content rather than just reading it. All element-targeting tools accept a `ref` obtained from a prior `browser_snapshot` call; see [Refs & snapshots](../concepts/refs-snapshots.md) for how refs work and when they become stale, and [Inspection tools](inspection.md) for the tools that produce them.

Examples below focus on tool-specific data. Registered tools also return the shared [operation metadata and error fields](../concepts/response-envelope.md). Page actions check for blocking modals after acquiring the instance's action lock. Dialog and upload recovery use a separate lock so they can resolve a modal while its triggering action is still waiting.

Optional `page_id` selects a live page without changing the selected tab; an invalid
explicit target returns `page_not_found`. Frame-capable calls also accept `frame_id`
and return `frame_not_found` for a detached or foreign frame. Omitted targets retain
existing behavior. See [explicit targeting](../concepts/instances-isolation.md#explicit-page-targets).

## browser_click { #browser_click }

Click an element by its accessibility ref from `browser_snapshot`.

**Signature**

```python
async def browser_click(
    instance: str,
    ref: str,
    *,
    double_click: bool = False,
    button: str = "left",
    modifiers: list[str] | None = None,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name           | Type                  | Default  | Description                                                                                                           |
| -------------- | --------------------- | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `instance`     | `str`                 | —        | Instance name.                                                                                                        |
| `ref`          | `str`                 | —        | Element ref from `browser_snapshot` (e.g. `"e5"`). See [Refs & snapshots](../concepts/refs-snapshots.md).             |
| `double_click` | `bool`                | `False`  | Perform a double-click instead of a single click.                                                                     |
| `button`       | `str`                 | `"left"` | Mouse button: `"left"`, `"right"`, or `"middle"`.                                                                     |
| `modifiers`    | `list[str] \| None`   | `None`   | Keyboard modifiers held during the click. Valid values: `"Alt"`, `"Control"`, `"ControlOrMeta"`, `"Meta"`, `"Shift"`. |
| `page_id`      | `str \| None`         | `None`   | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs.   |
| `frame_id`     | `str \| None`         | `None`   | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                            |
| `wait_for`     | `WaitForSpec \| None` | `None`   | One condition armed before the action; see [action observations](navigation.md#action-observations).                  |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "clicked": "e5" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `invalid_params`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_click", "arguments": { "instance": "main", "ref": "e5" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "clicked": "e5" } }
```

**Notes** — The element is scrolled into view and clicked at its center. May trigger navigation, form submission, or open a modal. After a click that causes navigation, snapshot refs are invalidated — take a fresh snapshot before referencing page elements again.

## browser_type { #browser_type }

Type text into an editable element identified by its accessibility ref.

**Signature**

```python
async def browser_type(
    instance: str,
    ref: str,
    text: str,
    *,
    clear_first: bool = True,
    submit: bool = False,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name          | Type                  | Default | Description                                                                                                                |
| ------------- | --------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `instance`    | `str`                 | —       | Instance name.                                                                                                             |
| `ref`         | `str`                 | —       | Element ref from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md).                                |
| `text`        | `str`                 | —       | Text to type.                                                                                                              |
| `clear_first` | `bool`                | `True`  | Clear the existing value before typing (uses `fill`, which is instant). Set to `False` to append via simulated keystrokes. |
| `submit`      | `bool`                | `False` | Press Enter after typing and wait up to 2 s for `domcontentloaded` (useful for forms that navigate on submit).             |
| `page_id`     | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs.        |
| `frame_id`    | `str \| None`         | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                                 |
| `wait_for`    | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                       |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "typed_into": "e12" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{
  "name": "browser_type",
  "arguments": { "instance": "main", "ref": "e12", "text": "hello@example.com" }
}
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "typed_into": "e12" } }
```

## browser_fill_form { #browser_fill_form }

Fill multiple form fields in one call, in the order provided.

**Signature**

```python
async def browser_fill_form(
    instance: str,
    fields: list[dict[str, Any]],
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type                  | Default | Description                                                                                                                                                                                                                                                |
| ---------- | --------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`                 | —       | Instance name.                                                                                                                                                                                                                                             |
| `fields`   | `list[dict]`          | —       | Ordered list of field descriptors. Each dict must have `"ref"` (from `browser_snapshot`) and `"value"`, plus an optional `"type"`: `"textbox"` (default), `"checkbox"`, `"radio"`, or `"combobox"`. See [Refs & snapshots](../concepts/refs-snapshots.md). |
| `page_id`  | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs.                                                                                                                                        |
| `frame_id` | `str \| None`         | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                                                                                                                                                                 |
| `wait_for` | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                                                                                                                                                       |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "filled_count": 3 }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `invalid_params`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{
  "name": "browser_fill_form",
  "arguments": {
    "instance": "main",
    "fields": [
      { "ref": "e10", "value": "Alice" },
      { "ref": "e11", "value": "alice@example.com" },
      { "ref": "e12", "value": true, "type": "checkbox" }
    ]
  }
}
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "filled_count": 3 } }
```

**Notes** — Filling is sequential: if any field fails, the tool stops at that field and earlier fields retain their new values. Take a fresh snapshot to verify the form state after a partial failure. Checkbox and radio values are coerced via `coerce_bool`, which accepts real booleans or the strings `"true"`/`"false"`/`"1"`/`"0"`/`"checked"`/`"unchecked"`/`"yes"`/`"no"` (case-insensitive).

## browser_select_option { #browser_select_option }

Select an option in a `<select>` dropdown by its HTML `value` attribute.

**Signature**

```python
async def browser_select_option(
    instance: str,
    ref: str,
    value: str | list[str],
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type                  | Default | Description                                                                                                         |
| ---------- | --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`                 | —       | Instance name.                                                                                                      |
| `ref`      | `str`                 | —       | Ref of the `<select>` element from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md).       |
| `value`    | `str \| list[str]`    | —       | HTML `value` attribute of the option to select (not the display label). Pass a list for multi-select elements.      |
| `page_id`  | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `frame_id` | `str \| None`         | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                          |
| `wait_for` | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "selected": "us" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{
  "name": "browser_select_option",
  "arguments": { "instance": "main", "ref": "e20", "value": "us" }
}
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "selected": "us" } }
```

**Notes** — Use the snapshot to inspect option elements nested under the `<select>` to find the correct `value` attributes. To select multiple options, pass a list: `"value": ["opt1", "opt2"]`.

## browser_hover { #browser_hover }

Hover the mouse over an element identified by its accessibility ref.

**Signature**

```python
async def browser_hover(
    instance: str,
    ref: str,
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name       | Type                  | Default | Description                                                                                                         |
| ---------- | --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`                 | —       | Instance name.                                                                                                      |
| `ref`      | `str`                 | —       | Element ref from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md).                         |
| `page_id`  | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `frame_id` | `str \| None`         | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                          |
| `wait_for` | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "hovered": "e8" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `modal_state_blocked`

**Example**

Request:

```json
{ "name": "browser_hover", "arguments": { "instance": "main", "ref": "e8" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "hovered": "e8" } }
```

**Notes** — The element is scrolled into view and the cursor is positioned at its center. Useful for triggering hover-activated menus, tooltips, or CSS `:hover` styles. Take a fresh snapshot after hovering to observe any newly-revealed elements.

## browser_drag { #browser_drag }

Drag an element to a target element using accessibility refs.

**Signature**

```python
async def browser_drag(
    instance: str,
    source_ref: str,
    target_ref: str,
    *,
    page_id: str | None = None,
    frame_id: str | None = None,
    wait_for: WaitForSpec | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name         | Type                  | Default | Description                                                                                                         |
| ------------ | --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance`   | `str`                 | —       | Instance name.                                                                                                      |
| `source_ref` | `str`                 | —       | Ref of the element to drag (from `browser_snapshot`). See [Refs & snapshots](../concepts/refs-snapshots.md).        |
| `target_ref` | `str`                 | —       | Ref of the drop target (from `browser_snapshot`).                                                                   |
| `page_id`    | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `frame_id`   | `str \| None`         | `None`  | Attached frame ID from `browser_frames`; explicit scope never falls back to another frame.                          |
| `wait_for`   | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "dragged": "e3", "to": "e7" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `stale_ref`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{
  "name": "browser_drag",
  "arguments": { "instance": "main", "source_ref": "e3", "target_ref": "e7" }
}
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "dragged": "e3", "to": "e7" } }
```

**Notes** — Performs a full pointer-event drag sequence: mouse-down on the source, move to the target center, mouse-up. This supports drag-and-drop implementations that respond to pointer events.

Native HTML5 `draggable` / `DataTransfer` behavior depends on the application and browser backend. Check the resulting page state to confirm that the intended drop occurred.

## browser_press_key { #browser_press_key }

Press a keyboard key on the active page (sent to whatever element currently has focus).

**Signature**

```python
async def browser_press_key(
    instance: str, key: str, *, page_id: str | None = None, wait_for: WaitForSpec | None = None
) -> dict[str, Any]
```

**Parameters**

| Name       | Type                  | Default | Description                                                                                                         |
| ---------- | --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`                 | —       | Instance name.                                                                                                      |
| `key`      | `str`                 | —       | Playwright key name, e.g. `"Enter"`, `"Tab"`, `"Escape"`, `"ArrowDown"`, `"Control+A"`, `"Shift+Tab"`.              |
| `page_id`  | `str \| None`         | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |
| `wait_for` | `WaitForSpec \| None` | `None`  | One condition armed before the action; see [action observations](navigation.md#action-observations).                |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "pressed": "Tab" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_press_key", "arguments": { "instance": "main", "key": "Tab" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "pressed": "Tab" } }
```

**Notes** — When `key` is `"Enter"`, the tool waits up to 2 s for `domcontentloaded` in case the key triggers a form submission. See the [Playwright keyboard documentation](https://playwright.dev/python/docs/api/class-keyboard) for the full list of key names.

## browser_file_upload { #browser_file_upload }

Resolve a pending native file-chooser dialog by attaching files or cancelling.

**Signature**

```python
async def browser_file_upload(
    instance: str, paths: list[str] | None = None, *, page_id: str | None = None
) -> dict[str, Any]
```

**Parameters**

| Name       | Type                | Default | Description                                                                                                          |
| ---------- | ------------------- | ------- | -------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`               | —       | Instance name.                                                                                                       |
| `paths`    | `list[str] \| None` | `None`  | Absolute paths of the files to attach. `None` or an empty list cancels the file chooser without attaching any files. |
| `page_id`  | `str \| None`       | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs.  |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape (mutually exclusive):

```json
{ "uploaded_count": 2 }
```

```json
{ "cancelled": true }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_file_upload", "arguments": { "instance": "main", "paths": ["/tmp/report.pdf"] } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "uploaded_count": 1 } }
```

**Notes** — A file-chooser must already be pending before calling this tool (opened by a prior `browser_click` on a file input). The modal-state listener captures the chooser automatically. This tool can run while the triggering action is still waiting. If resolution fails or is cancelled while the page remains alive, the chooser is retained for retry. A chooser belonging to a closed page returns `modal_state_blocked`. Operation metadata identifies the chooser's page, which may be a popup rather than the active tab. See [Modal state](../concepts/modal-state.md) for the broader dialog/chooser lifecycle.

## browser_handle_dialog { #browser_handle_dialog }

Resolve a pending JavaScript dialog (alert, confirm, or prompt).

**Signature**

```python
async def browser_handle_dialog(
    instance: str, *, accept: bool, prompt_text: str | None = None, page_id: str | None = None
) -> dict[str, Any]
```

**Parameters**

| Name          | Type          | Default | Description                                                                                                         |
| ------------- | ------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `instance`    | `str`         | —       | Instance name.                                                                                                      |
| `accept`      | `bool`        | —       | `True` to accept the dialog (calls `dialog.accept`); `False` to dismiss it.                                         |
| `prompt_text` | `str \| None` | `None`  | Text to submit with a `prompt` dialog. Ignored for `alert` and `confirm` dialogs.                                   |
| `page_id`     | `str \| None` | `None`  | Stable page ID; omitted uses the selected page. Explicit targeting preserves selection and rejects unavailable IDs. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "action": "accepted", "dialog_type": "confirm", "message": "Are you sure?" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`

**Example**

Request:

```json
{ "name": "browser_handle_dialog", "arguments": { "instance": "main", "accept": true } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "action": "accepted", "dialog_type": "alert", "message": "Upload complete." }
}
```

**Notes** — The dialog must already be open before calling this tool; it was triggered by a prior tool call and captured automatically by the modal-state listener. The triggering action may still be waiting: dialog recovery uses an independent lock and can unblock it. This tool does not pre-register a handler for future dialogs.

If accepting or dismissing fails or is cancelled while the page remains alive, the dialog is normally retained for retry. A definitive Playwright response that the dialog was already handled discards the stale entry and returns an error with uncertain outcome; it does not claim that this call resolved the dialog. A dialog belonging to a closed page returns `modal_state_blocked`. Operation metadata identifies the dialog's page, including a non-active popup. See [Modal state](../concepts/modal-state.md) for the broader dialog lifecycle.
