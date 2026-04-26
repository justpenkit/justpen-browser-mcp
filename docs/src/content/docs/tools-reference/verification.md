---
title: Verification
description: Wait for conditions and assert page state.
---

Verification tools let you assert that the current state of a page matches expectations — checking element visibility, text presence, or input values — without the round-trip of a full snapshot. Each tool returns on success or emits a `verification_failed` error code (specific to this module) when the assertion does not hold; see [envelope error codes](/concepts/response-envelope/#error_type-values) for the full list of `error_type` values. Use `browser_wait_for` before any verification if the state you need has not yet appeared.

## browser_verify_element_visible

Verify that the element identified by a ref is currently visible on the page.

**Signature**

```python
async def browser_verify_element_visible(instance: str, ref: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                       |
| ---------- | ----- | ------- | ------------------------------------------------- |
| `instance` | `str` | —       | Instance name.                                    |
| `ref`      | `str` | —       | Element ref (`[ref=eN]`) from `browser_snapshot`. |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "visible": true, "ref": "e12" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `stale_ref` — ref is no longer in the accessibility tree
- `verification_failed` — element exists but is not currently visible

**Example**

Request:

```json
{ "name": "browser_verify_element_visible", "arguments": { "instance": "main", "ref": "e12" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "visible": true, "ref": "e12" } }
```

**Notes** — The visibility check is synchronous — no waiting is performed. Refs that live inside iframes are resolved by falling back through child frames. Use `browser_wait_for(text=...)` first if the element may not have appeared yet.

## browser_verify_list_visible

Verify visibility of multiple elements in either refs mode or container mode.

**Signature**

```python
async def browser_verify_list_visible(
    instance: str,
    refs: list[str] | None = None,
    container_ref: str | None = None,
    items: list[str] | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name            | Type                | Default | Description                                                                                                    |
| --------------- | ------------------- | ------- | -------------------------------------------------------------------------------------------------------------- |
| `instance`      | `str`               | —       | Instance name.                                                                                                 |
| `refs`          | `list[str] \| None` | `None`  | **Refs mode**: list of element refs that must all be visible. Mutually exclusive with `container_ref`/`items`. |
| `container_ref` | `str \| None`       | `None`  | **Container mode**: ref of the parent element. Required when using `items`.                                    |
| `items`         | `list[str] \| None` | `None`  | **Container mode**: list of text strings that must be visible as descendants of `container_ref`.               |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape depends on mode:

Refs mode:

```json
{ "visible_refs": ["e3", "e7", "e12"] }
```

Container mode:

```json
{ "container_ref": "e5", "verified_items": ["Apple", "Banana", "Cherry"] }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `invalid_params` — neither mode supplied, both modes supplied, or `container_ref` given without `items`
- `stale_ref` — a ref is no longer in the accessibility tree
- `verification_failed` — one or more elements or items are not visible

**Example**

Request (refs mode):

```json
{ "name": "browser_verify_list_visible", "arguments": { "instance": "main", "refs": ["e3", "e7"] } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "visible_refs": ["e3", "e7"] } }
```

Request (container mode):

```json
{
  "name": "browser_verify_list_visible",
  "arguments": { "instance": "main", "container_ref": "e5", "items": ["Apple", "Banana"] }
}
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "container_ref": "e5", "verified_items": ["Apple", "Banana"] }
}
```

**Notes** — The two modes are mutually exclusive: pass either `refs` or `container_ref`+`items`, never both. Container mode matches by text substring (`get_by_text`) and uses `.first` to avoid strict-mode violations when text appears multiple times. Useful for post-action assertions such as verifying all rows of a rendered list.

## browser_verify_text_visible

Verify that the given text is currently visible somewhere on the active page.

**Signature**

```python
async def browser_verify_text_visible(instance: str, text: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                          |
| ---------- | ----- | ------- | ---------------------------------------------------- |
| `instance` | `str` | —       | Instance name.                                       |
| `text`     | `str` | —       | Text to look for (case-insensitive substring match). |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "text": "Welcome", "visible": true }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `verification_failed` — the text is not visible on any frame of the page

**Example**

Request:

```json
{ "name": "browser_verify_text_visible", "arguments": { "instance": "main", "text": "Welcome" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "text": "Welcome", "visible": true } }
```

**Notes** — Matching is a case-insensitive non-exact substring search via `get_by_text`. Both the main frame and all child frames are searched. Uses `.first` to avoid strict-mode violations when the text matches multiple elements. Use `browser_wait_for(text=...)` if the text may not have appeared yet.

## browser_verify_value

Verify the value or checked state of an input element.

**Signature**

```python
async def browser_verify_value(
    instance: str,
    ref: str,
    expected_value: str,
    element_type: str = "text",
) -> dict[str, Any]
```

**Parameters**

| Name             | Type  | Default  | Description                                                                                                                                                   |
| ---------------- | ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance`       | `str` | —        | Instance name.                                                                                                                                                |
| `ref`            | `str` | —        | Element ref (`[ref=eN]`) from `browser_snapshot`.                                                                                                             |
| `expected_value` | `str` | —        | Expected value. String for `"text"` mode; coerced to bool for `"checkbox"`/`"radio"` (accepts `"true"`, `"false"`, `"1"`, `"0"`, `"checked"`, `"unchecked"`). |
| `element_type`   | `str` | `"text"` | Comparison mode: `"text"` (reads via `input_value()`), `"checkbox"`, or `"radio"` (reads via `is_checked()`).                                                 |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "ref": "e7", "value": "alice@example.com", "element_type": "text" }
```

For checkbox/radio mode `value` is a `bool`:

```json
{ "ref": "e9", "value": true, "element_type": "checkbox" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `invalid_params` — `element_type` is not one of `"text"`, `"checkbox"`, `"radio"`
- `stale_ref` — ref is no longer in the accessibility tree
- `verification_failed` — actual value does not match `expected_value`

**Example**

Request:

```json
{
  "name": "browser_verify_value",
  "arguments": { "instance": "main", "ref": "e7", "expected_value": "alice@example.com" }
}
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "ref": "e7", "value": "alice@example.com", "element_type": "text" }
}
```

**Notes** — Use after `browser_type`, `browser_fill_form`, or a checkbox/radio click to confirm the change applied correctly. `element_type` defaults to `"text"`, which uses `input_value()` — suitable for `<input>`, `<textarea>`, and `<select>`. For `"checkbox"` and `"radio"`, `is_checked()` is used and `expected_value` is coerced from a string to a bool before comparison.
