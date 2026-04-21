# Mouse tools

Mouse tools provide low-level positional control over the browser's mouse pointer. Use these tools when you need to interact with elements that are not in the accessibility snapshot, trigger hover effects at specific coordinates, compose custom gesture sequences with `browser_mouse_down` / `browser_mouse_up`, or perform pixel-precise drag operations. When a target element is visible in `browser_snapshot`, prefer the higher-level ref-based tools (`browser_click`, `browser_hover`, `browser_drag`) — they are more stable across layout changes.

## browser_mouse_click_xy

Click the mouse at an absolute pixel position on the active page.

**Signature**

```python
async def browser_mouse_click_xy(
    context: str,
    x: int,
    y: int,
    button: str = "left",
    click_count: int = 1,
    delay_ms: int = 0,
) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `x` | `int` | — | Page-relative horizontal pixel coordinate (0 = left edge). |
| `y` | `int` | — | Page-relative vertical pixel coordinate (0 = top edge). |
| `button` | `str` | `"left"` | One of `"left"`, `"right"`, `"middle"`. |
| `click_count` | `int` | `1` | Number of clicks to deliver; use `2` for a double-click. |
| `delay_ms` | `int` | `0` | Delay in milliseconds between mousedown and mouseup. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "clicked_at": [120, 340], "button": "left" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_click_xy", "arguments": { "context": "main", "x": 120, "y": 340 } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "clicked_at": [120, 340], "button": "left" } }
```

**Notes** — Prefer `browser_click(ref=...)` when the target element is in the accessibility snapshot — it is more reliable and does not depend on exact layout coordinates.

## browser_mouse_move_xy

Move the mouse cursor to an absolute pixel position without clicking.

**Signature**

```python
async def browser_mouse_move_xy(context: str, x: int, y: int) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `x` | `int` | — | Target horizontal pixel coordinate. |
| `y` | `int` | — | Target vertical pixel coordinate. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "moved_to": [120, 340] }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_move_xy", "arguments": { "context": "main", "x": 120, "y": 340 } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "moved_to": [120, 340] } }
```

**Notes** — Useful for triggering hover effects at specific coordinates. Prefer `browser_hover(ref=...)` when the target is in the accessibility snapshot. Use before `browser_mouse_wheel` when targeting a specific scrollable container.

## browser_mouse_down

Press a mouse button down without releasing it.

**Signature**

```python
async def browser_mouse_down(context: str, button: str = "left") -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `button` | `str` | `"left"` | One of `"left"`, `"right"`, `"middle"`. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "button_down": "left" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_down", "arguments": { "context": "main", "button": "left" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "button_down": "left" } }
```

**Notes** — Pair with `browser_mouse_up` to complete a press-and-release sequence. For drag operations, prefer `browser_mouse_drag_xy` which handles the full sequence.

## browser_mouse_up

Release a previously pressed mouse button.

**Signature**

```python
async def browser_mouse_up(context: str, button: str = "left") -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `button` | `str` | `"left"` | Must match the button passed to `browser_mouse_down`. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "button_up": "left" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_up", "arguments": { "context": "main", "button": "left" } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "button_up": "left" } }
```

## browser_mouse_drag_xy

Drag the mouse from one absolute pixel position to another.

**Signature**

```python
async def browser_mouse_drag_xy(context: str, from_x: int, from_y: int, to_x: int, to_y: int) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `from_x` | `int` | — | Starting horizontal pixel coordinate. |
| `from_y` | `int` | — | Starting vertical pixel coordinate. |
| `to_x` | `int` | — | Ending horizontal pixel coordinate. |
| `to_y` | `int` | — | Ending vertical pixel coordinate. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "from": [50, 100], "to": [300, 100] }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_drag_xy", "arguments": { "context": "main", "from_x": 50, "from_y": 100, "to_x": 300, "to_y": 100 } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "from": [50, 100], "to": [300, 100] } }
```

**Notes** — Performs: move to (`from_x`, `from_y`), press left button, move to (`to_x`, `to_y`), release. For element-to-element drag, prefer `browser_drag(source_ref, target_ref)` which uses accessibility refs and is more stable across layout changes.

## browser_mouse_wheel

Scroll the mouse wheel by the given pixel deltas at the current cursor position.

**Signature**

```python
async def browser_mouse_wheel(context: str, delta_x: int = 0, delta_y: int = 0) -> dict[str, Any]
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `context` | `str` | — | Context name. |
| `delta_x` | `int` | `0` | Horizontal scroll in CSS pixels (positive = right). |
| `delta_y` | `int` | `0` | Vertical scroll in CSS pixels (positive = down). |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "scrolled": [0, 300] }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `context_not_found`
- `invalid_params`
- `modal_state_blocked`
- `internal_error`

**Example**

Request:

```json
{ "name": "browser_mouse_wheel", "arguments": { "context": "main", "delta_y": 300 } }
```

Response:

```json
{ "status": "success", "context": "main", "data": { "scrolled": [0, 300] } }
```

**Notes** — At least one of `delta_x` or `delta_y` must be non-zero; providing both as `0` returns an `invalid_params` error immediately. The scroll is delivered at the current cursor position — call `browser_mouse_move_xy` first to target a specific scrollable container.
