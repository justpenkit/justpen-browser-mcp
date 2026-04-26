---
title: Interaction
description: Click, type, fill forms, and dispatch keyboard events.
---

Interaction tools let an agent act on the page — clicking, typing, filling forms, selecting dropdown options, dragging elements, hovering, pressing keys, handling JavaScript dialogs, and completing file uploads. Reach for these tools any time a workflow requires manipulating page content rather than just reading it. All element-targeting tools accept a `ref` obtained from a prior `browser_snapshot` call; see [Refs & snapshots](../concepts/refs-snapshots.md) for how refs work and when they become stale, and [Inspection tools](inspection.md) for the tools that produce them.

## browser_click

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
) -> dict[str, Any]
```

**Parameters**

| Name           | Type                | Default  | Description                                                                                                           |
| -------------- | ------------------- | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `instance`     | `str`               | —        | Instance name.                                                                                                        |
| `ref`          | `str`               | —        | Element ref from `browser_snapshot` (e.g. `"e5"`). See [Refs & snapshots](../concepts/refs-snapshots.md).             |
| `double_click` | `bool`              | `False`  | Perform a double-click instead of a single click.                                                                     |
| `button`       | `str`               | `"left"` | Mouse button: `"left"`, `"right"`, or `"middle"`.                                                                     |
| `modifiers`    | `list[str] \| None` | `None`   | Keyboard modifiers held during the click. Valid values: `"Alt"`, `"Control"`, `"ControlOrMeta"`, `"Meta"`, `"Shift"`. |

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

## browser_type

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
) -> dict[str, Any]
```

**Parameters**

| Name          | Type   | Default | Description                                                                                                                |
| ------------- | ------ | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `instance`    | `str`  | —       | Instance name.                                                                                                             |
| `ref`         | `str`  | —       | Element ref from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md).                                |
| `text`        | `str`  | —       | Text to type.                                                                                                              |
| `clear_first` | `bool` | `True`  | Clear the existing value before typing (uses `fill`, which is instant). Set to `False` to append via simulated keystrokes. |
| `submit`      | `bool` | `False` | Press Enter after typing and wait up to 2 s for `domcontentloaded` (useful for forms that navigate on submit).             |

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

## browser_fill_form

Fill multiple form fields in one call, in the order provided.

**Signature**

```python
async def browser_fill_form(instance: str, fields: list[dict[str, Any]]) -> dict[str, Any]
```

**Parameters**

| Name       | Type         | Default | Description                                                                                                                                                                                                                                                |
| ---------- | ------------ | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`        | —       | Instance name.                                                                                                                                                                                                                                             |
| `fields`   | `list[dict]` | —       | Ordered list of field descriptors. Each dict must have `"ref"` (from `browser_snapshot`) and `"value"`, plus an optional `"type"`: `"textbox"` (default), `"checkbox"`, `"radio"`, or `"combobox"`. See [Refs & snapshots](../concepts/refs-snapshots.md). |

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

## browser_select_option

Select an option in a `<select>` dropdown by its HTML `value` attribute.

**Signature**

```python
async def browser_select_option(instance: str, ref: str, value: str | list[str]) -> dict[str, Any]
```

**Parameters**

| Name       | Type               | Default | Description                                                                                                    |
| ---------- | ------------------ | ------- | -------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`              | —       | Instance name.                                                                                                 |
| `ref`      | `str`              | —       | Ref of the `<select>` element from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md).  |
| `value`    | `str \| list[str]` | —       | HTML `value` attribute of the option to select (not the display label). Pass a list for multi-select elements. |

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

## browser_hover

Hover the mouse over an element identified by its accessibility ref.

**Signature**

```python
async def browser_hover(instance: str, ref: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                                                                 |
| ---------- | ----- | ------- | ------------------------------------------------------------------------------------------- |
| `instance` | `str` | —       | Instance name.                                                                              |
| `ref`      | `str` | —       | Element ref from `browser_snapshot`. See [Refs & snapshots](../concepts/refs-snapshots.md). |

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

## browser_drag

Drag an element to a target element using accessibility refs.

**Signature**

```python
async def browser_drag(instance: str, source_ref: str, target_ref: str) -> dict[str, Any]
```

**Parameters**

| Name         | Type  | Default | Description                                                                                                  |
| ------------ | ----- | ------- | ------------------------------------------------------------------------------------------------------------ |
| `instance`   | `str` | —       | Instance name.                                                                                               |
| `source_ref` | `str` | —       | Ref of the element to drag (from `browser_snapshot`). See [Refs & snapshots](../concepts/refs-snapshots.md). |
| `target_ref` | `str` | —       | Ref of the drop target (from `browser_snapshot`).                                                            |

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

**Notes** — Performs a full pointer-event drag sequence: mouse-down on the source, move to the target center, mouse-up. Works for most drag-and-drop implementations that use pointer events. Frameworks that rely on HTML5 drag events or custom libraries may not respond correctly.

## browser_press_key

Press a keyboard key on the active page (sent to whatever element currently has focus).

**Signature**

```python
async def browser_press_key(instance: str, key: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                                                                            |
| ---------- | ----- | ------- | ------------------------------------------------------------------------------------------------------ |
| `instance` | `str` | —       | Instance name.                                                                                         |
| `key`      | `str` | —       | Playwright key name, e.g. `"Enter"`, `"Tab"`, `"Escape"`, `"ArrowDown"`, `"Control+A"`, `"Shift+Tab"`. |

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

## browser_file_upload

Resolve a pending native file-chooser dialog by attaching files or cancelling.

**Signature**

```python
async def browser_file_upload(instance: str, paths: list[str] | None = None) -> dict[str, Any]
```

**Parameters**

| Name       | Type                | Default | Description                                                                                                          |
| ---------- | ------------------- | ------- | -------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str`               | —       | Instance name.                                                                                                       |
| `paths`    | `list[str] \| None` | `None`  | Absolute paths of the files to attach. `None` or an empty list cancels the file chooser without attaching any files. |

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

**Notes** — A file-chooser must already be pending before calling this tool (opened by a prior `browser_click` on a file input). The modal-state listener captures the chooser automatically. If the `set_files` call fails and the page is still alive, the chooser is re-queued so you can retry. See [Modal state](../concepts/modal-state.md) for the broader dialog/chooser lifecycle.

## browser_handle_dialog

Resolve a pending JavaScript dialog (alert, confirm, or prompt).

**Signature**

```python
async def browser_handle_dialog(instance: str, *, accept: bool, prompt_text: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name          | Type          | Default | Description                                                                       |
| ------------- | ------------- | ------- | --------------------------------------------------------------------------------- |
| `instance`    | `str`         | —       | Instance name.                                                                    |
| `accept`      | `bool`        | —       | `True` to accept the dialog (calls `dialog.accept`); `False` to dismiss it.       |
| `prompt_text` | `str \| None` | `None`  | Text to submit with a `prompt` dialog. Ignored for `alert` and `confirm` dialogs. |

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

**Notes** — The dialog must already be open before calling this tool; it was triggered by a prior tool call and captured automatically by the modal-state listener. This tool does not pre-register a handler for future dialogs. See [Modal state](../concepts/modal-state.md) for the broader dialog lifecycle.
