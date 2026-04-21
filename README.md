# justpen-browser-mcp

Camoufox-based MCP server with multi-context browser session isolation.

Exposes a stealth-patched Firefox (via [Camoufox](https://github.com/daijro/camoufox))
to MCP-aware clients as a set of browser automation tools. Each named context
is a fully isolated `BrowserContext` — cookies, storage, and cache do not leak
between contexts — so a single server process can drive parallel logged-in
flows for different users or tenants.

## Installation

Until the package is on PyPI, install straight from git:

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.1.0"
uv run python -m camoufox fetch   # one-time ~150MB Camoufox binary download
```

Contributors working from a clone can run `make setup` instead, which
`uv sync`s the dev and docs groups, fetches the Camoufox binary, and
installs the project's git hooks (pre-commit / pre-push / commit-msg).

## Usage

The install exposes two equivalent invocations — the `justpen-browser-mcp`
console script (added by `[project.scripts]` in `pyproject.toml`) and the
`python -m justpen_browser_mcp` module entry point:

```bash
justpen-browser-mcp
# or
python -m justpen_browser_mcp
```

Register with an MCP-aware client (e.g. Claude Code):

```json
{
  "mcpServers": {
    "justpen-browser": {
      "command": "justpen-browser-mcp"
    }
  }
}
```

If the client runs outside the virtualenv where the package is installed,
use the `python -m justpen_browser_mcp` form with an explicit interpreter
path instead.

## Server identity

| Property | Value |
|---|---|
| FastMCP name | `camoufox-mcp` |
| Entry points | `justpen-browser-mcp` (console script) / `python -m justpen_browser_mcp` (module) |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `BROWSER_MCP_HEADLESS` | `true` | Launch Camoufox in headless mode. Accepts `true` or `false` (case-insensitive). |
| `BROWSER_MCP_LOG_LEVEL` | `INFO` | Python log level name for server-side logging to stderr. |

## Response envelope

Every tool returns one of two envelope shapes.

**Success:**

```json
{
  "status": "success",
  "context": "<context-name> | null",
  "data": {}
}
```

**Error:**

```json
{
  "status": "error",
  "context": "<context-name> | null",
  "error_type": "<type>",
  "message": "<human-readable description>"
}
```

`context` is `null` for server-level tools (`browser_status`, `browser_list_contexts`) that are not scoped to a specific context.

### error_type values

| `error_type` | Meaning |
|---|---|
| `context_not_found` | No context with the given name exists; call `browser_create_context` first. |
| `context_already_exists` | A context with that name is already registered. |
| `invalid_state_file` | The supplied state file exists but cannot be parsed as Playwright storage state JSON. |
| `state_file_not_found` | The supplied state file path does not exist. |
| `browser_not_running` | Camoufox is not running; no page operation is possible. |
| `binary_not_found` | The Camoufox binary could not be located on the host. |
| `element_not_found` | The element could not be found in the page's accessibility tree. |
| `stale_ref` | The `ref` was valid in a previous snapshot but is no longer in the current accessibility tree. |
| `navigation_failed` | A network error, invalid URL, or page crash prevented navigation. |
| `navigation_timeout` | The page did not finish loading within the timeout. |
| `wait_timeout` | A text or state wait condition did not resolve in time. |
| `dialog_not_present` | `browser_handle_dialog` was called but no JS dialog is pending. |
| `evaluation_failed` | A JavaScript expression or Python code snippet raised an exception. |
| `verification_failed` | A verification tool found the element or text was not in the expected state. |
| `invalid_params` | A parameter value was invalid or an incompatible combination was supplied. |
| `modal_state_blocked` | A JS dialog or file-chooser is pending and must be resolved before this tool can run. |
| `internal_error` | An unexpected internal error; all non-`BrowserMcpError` exceptions map here. |

## Refs and snapshots

Most interaction tools consume a `ref` string (e.g. `"e12"`) obtained from `browser_snapshot`. Refs are annotated in the snapshot YAML as `[ref=eN]` on each interactive element. They are session-scoped and invalidated by any navigation or page reload — always take a fresh snapshot after navigating.

When `browser_snapshot` is called with `selector=<css-or-aria>`, it returns a scoped aria YAML **without** ref annotations (using `Locator.aria_snapshot`). Use the default `selector=None` mode when you need refs for subsequent interaction tools.

## Modal state

Pending JS dialogs (`alert`, `confirm`, `prompt`) and native file-choosers are captured by event listeners on the context and tracked as "modal state". Most tools check for pending modal state before running and return `modal_state_blocked` if one is present.

To unblock:

- JS dialog: call `browser_handle_dialog`.
- File chooser: call `browser_file_upload`.

## Tools

The server exposes 45 tools across 11 modules.

### Lifecycle (lifecycle.py)

#### browser_create_context

**Signature:**

```python
browser_create_context(
    context: str,
    state_path: str | None = None,
) -> dict
```

**Purpose:** Create a new isolated browser context (like a fresh browser profile).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Name for the new context. |
| `state_path` | `str \| None` | `None` | Optional path to a Playwright storage-state JSON file to pre-load cookies and localStorage. |

**Returns:**

- `created` — `True`.

**Notes:** No pages exist immediately after creation. The first tool that needs a page (e.g. `browser_navigate`) creates one implicitly.

#### browser_load_context_state

**Signature:**

```python
browser_load_context_state(
    context: str,
    state_path: str,
) -> dict
```

**Purpose:** Replace the context's cookies and localStorage in-place from a saved state file without recreating the context.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `state_path` | `str` | — | Path to a Playwright storage-state JSON file produced by `browser_export_context_state`. |

**Returns:**

- `loaded_from` — the path that was applied.
- `failed_origins` — list of origins whose localStorage could not be restored (only present when non-empty).

#### browser_export_context_state

**Signature:**

```python
browser_export_context_state(
    context: str,
    state_path: str,
) -> dict
```

**Purpose:** Write the context's current cookies and localStorage to a JSON file.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `state_path` | `str` | — | Destination file path. Parent directories are created automatically. |

**Returns:**

- `saved_to` — the absolute path the file was written to.

#### browser_destroy_context

**Signature:**

```python
browser_destroy_context(
    context: str,
) -> dict
```

**Purpose:** Close the context and remove it from the server's registry.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |

**Returns:**

- `destroyed` — `True`.

**Notes:** If this was the last active context, Camoufox is automatically shut down; the next `browser_create_context` will re-launch it lazily.

#### browser_list_contexts

**Signature:**

```python
browser_list_contexts() -> dict
```

**Purpose:** List all active browser contexts with summary information.

**Returns:**

- `contexts` — list of objects, each with `context` (name), `page_count`, `active_url`, and `cookie_count`.

**Notes:** Never raises an error. `context` in the envelope is `null` (server-level tool).

### Navigation (navigation.py)

#### browser_navigate

**Signature:**

```python
browser_navigate(
    context: str,
    url: str,
) -> dict
```

**Purpose:** Navigate the active page in the given context to a URL.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `url` | `str` | — | Destination URL. |

**Returns:**

- `url` — final URL after any redirects.
- `title` — page title after load.

**Notes:** URL normalization: `localhost[:port]` and bare IPv4 addresses get `http://`; schemeless hostnames with a dot get `https://`. When a download is triggered, the response includes an additional `download: true` field alongside `url` and `title`. Prior refs from `browser_snapshot` are invalidated after navigation.

#### browser_navigate_back

**Signature:**

```python
browser_navigate_back(
    context: str,
) -> dict
```

**Purpose:** Navigate back one step in the browser history for the active page.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |

**Returns:**

- `url` — URL of the page after going back.

#### browser_wait_for

**Signature:**

```python
browser_wait_for(
    context: str,
    text: str | None = None,
    text_gone: str | None = None,
    time: float | None = None,
) -> dict
```

**Purpose:** Wait for text to appear, text to disappear, or a fixed duration.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `text` | `str \| None` | `None` | Wait until this string is visible on the page. |
| `text_gone` | `str \| None` | `None` | Wait until this string is hidden on the page. |
| `time` | `float \| None` | `None` | Seconds to wait unconditionally (capped at 30). |

**Returns:**

- `waited_for` — description of the conditions waited on.

**Notes:** At least one of `text`, `text_gone`, or `time` must be provided. When multiple are given, conditions are evaluated in order: `time` → `text_gone` → `text`.

### Interaction (interaction.py)

#### browser_click

**Signature:**

```python
browser_click(
    context: str,
    ref: str,
    *,
    double_click: bool = False,
    button: str = "left",
    modifiers: list[str] | None = None,
) -> dict
```

**Purpose:** Click an element identified by its accessibility `ref` from the last `browser_snapshot`.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Element ref from `browser_snapshot`. |
| `double_click` | `bool` | `False` | Double-click instead of single. |
| `button` | `str` | `"left"` | One of `"left"`, `"right"`, `"middle"`. |
| `modifiers` | `list[str] \| None` | `None` | Any of `"Alt"`, `"Control"`, `"ControlOrMeta"`, `"Meta"`, `"Shift"`. |

**Returns:**

- `clicked` — the ref that was clicked.

**Notes:** Scrolls the element into view. May trigger navigation, form submission, or a modal.

#### browser_type

**Signature:**

```python
browser_type(
    context: str,
    ref: str,
    text: str,
    *,
    clear_first: bool = True,
    submit: bool = False,
) -> dict
```

**Purpose:** Type text into an editable element identified by its accessibility ref.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Element ref from `browser_snapshot`. |
| `text` | `str` | — | Text to type. |
| `clear_first` | `bool` | `True` | Clear existing value before typing (uses `fill`). When `False`, appends using simulated keystrokes. |
| `submit` | `bool` | `False` | Press Enter after typing and wait up to 2 s for `domcontentloaded`. |

**Returns:**

- `typed_into` — the ref that received the text.

#### browser_fill_form

**Signature:**

```python
browser_fill_form(
    context: str,
    fields: list[dict],
) -> dict
```

**Purpose:** Fill multiple form fields in one call, in the order provided.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `fields` | `list[dict]` | — | List of `{"ref": str, "value": any, "type": str?}` dicts. `type` is one of `"textbox"` (default), `"checkbox"`, `"radio"`, `"combobox"`. |

**Returns:**

- `filled_count` — number of fields filled.

**Notes:** If any field fails, filling stops at that field; earlier fields retain their new values. `coerce_bool` is used for checkbox/radio values — accepts `true`/`false`/`1`/`0`/`checked`/`unchecked`/`yes`/`no` (case-insensitive).

#### browser_select_option

**Signature:**

```python
browser_select_option(
    context: str,
    ref: str,
    value: str | list[str],
) -> dict
```

**Purpose:** Select an option in a `<select>` dropdown by its HTML value attribute.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Ref of the `<select>` element from `browser_snapshot`. |
| `value` | `str \| list[str]` | — | HTML value attribute of the option(s) to select. Use a list for multi-select elements. |

**Returns:**

- `selected` — the value(s) that were selected.

#### browser_hover

**Signature:**

```python
browser_hover(
    context: str,
    ref: str,
) -> dict
```

**Purpose:** Hover the mouse over an element identified by its accessibility ref.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Element ref from `browser_snapshot`. |

**Returns:**

- `hovered` — the ref that was hovered.

#### browser_drag

**Signature:**

```python
browser_drag(
    context: str,
    source_ref: str,
    target_ref: str,
) -> dict
```

**Purpose:** Drag an element to a target element using accessibility refs.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `source_ref` | `str` | — | Ref of the element to drag (from `browser_snapshot`). |
| `target_ref` | `str` | — | Ref of the drop target (from `browser_snapshot`). |

**Returns:**

- `dragged` — source ref.
- `to` — target ref.

#### browser_press_key

**Signature:**

```python
browser_press_key(
    context: str,
    key: str,
) -> dict
```

**Purpose:** Press a keyboard key on the active page (sent to whatever has focus).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `key` | `str` | — | Playwright key name, e.g. `"Enter"`, `"Tab"`, `"Escape"`, `"Control+A"`. |

**Returns:**

- `pressed` — the key string that was sent.

**Notes:** When `key` is `"Enter"`, waits up to 2 s for `domcontentloaded` in case the key triggers a form submission.

#### browser_file_upload

**Signature:**

```python
browser_file_upload(
    context: str,
    paths: list[str] | None = None,
) -> dict
```

**Purpose:** Resolve a pending native file-chooser dialog by attaching files or cancelling.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `paths` | `list[str] \| None` | `None` | Absolute paths of files to attach. `None` or empty list cancels the chooser. |

**Returns:**

- `uploaded_count` — number of files attached (on non-empty `paths`).
- `cancelled` — `True` (when called with no paths).

**Notes:** A file-chooser must already be pending (opened by a prior click on a file input). The modal-state listener captures it automatically.

#### browser_handle_dialog

**Signature:**

```python
browser_handle_dialog(
    context: str,
    *,
    accept: bool,
    prompt_text: str | None = None,
) -> dict
```

**Purpose:** Resolve a pending JavaScript dialog (alert/confirm/prompt).

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `accept` | `bool` | — | `True` to accept (calls `dialog.accept`), `False` to dismiss. |
| `prompt_text` | `str \| None` | `None` | Text to submit with a `prompt` dialog. Ignored for `alert`/`confirm`. |

**Returns:**

- `action` — `"accepted"` or `"dismissed"`.
- `dialog_type` — `"alert"`, `"confirm"`, or `"prompt"`.
- `message` — the dialog's message text.

### Mouse (mouse.py)

#### browser_mouse_click_xy

**Signature:**

```python
browser_mouse_click_xy(
    context: str,
    x: int,
    y: int,
    button: str = "left",
    click_count: int = 1,
    delay_ms: int = 0,
) -> dict
```

**Purpose:** Click the mouse at an absolute pixel position on the active page.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `x` | `int` | — | Page-relative horizontal pixel coordinate (0 = left edge). |
| `y` | `int` | — | Page-relative vertical pixel coordinate (0 = top edge). |
| `button` | `str` | `"left"` | One of `"left"`, `"right"`, `"middle"`. |
| `click_count` | `int` | `1` | Number of clicks to deliver; use `2` for a double-click. |
| `delay_ms` | `int` | `0` | Delay in milliseconds between mousedown and mouseup. |

**Returns:**

- `clicked_at` — `[x, y]`.
- `button` — button used.

**Notes:** Prefer `browser_click(ref=...)` when the target is in the accessibility snapshot; it is more reliable than pixel coordinates.

#### browser_mouse_move_xy

**Signature:**

```python
browser_mouse_move_xy(
    context: str,
    x: int,
    y: int,
) -> dict
```

**Purpose:** Move the mouse cursor to an absolute pixel position without clicking.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `x` | `int` | — | Target horizontal pixel coordinate. |
| `y` | `int` | — | Target vertical pixel coordinate. |

**Returns:**

- `moved_to` — `[x, y]`.

#### browser_mouse_down

**Signature:**

```python
browser_mouse_down(
    context: str,
    button: str = "left",
) -> dict
```

**Purpose:** Press a mouse button down without releasing it.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `button` | `str` | `"left"` | One of `"left"`, `"right"`, `"middle"`. |

**Returns:**

- `button_down` — the button that was pressed.

**Notes:** Pair with `browser_mouse_up` to complete a press-and-release. For drag operations prefer `browser_mouse_drag_xy`.

#### browser_mouse_up

**Signature:**

```python
browser_mouse_up(
    context: str,
    button: str = "left",
) -> dict
```

**Purpose:** Release a previously pressed mouse button.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `button` | `str` | `"left"` | Must match the button passed to `browser_mouse_down`. |

**Returns:**

- `button_up` — the button that was released.

#### browser_mouse_drag_xy

**Signature:**

```python
browser_mouse_drag_xy(
    context: str,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
) -> dict
```

**Purpose:** Drag the mouse from one absolute pixel position to another.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `from_x` | `int` | — | Starting horizontal pixel coordinate. |
| `from_y` | `int` | — | Starting vertical pixel coordinate. |
| `to_x` | `int` | — | Ending horizontal pixel coordinate. |
| `to_y` | `int` | — | Ending vertical pixel coordinate. |

**Returns:**

- `from` — `[from_x, from_y]`.
- `to` — `[to_x, to_y]`.

**Notes:** For element-to-element drag, prefer `browser_drag(source_ref, target_ref)` which uses accessibility refs and is more stable across layout changes.

#### browser_mouse_wheel

**Signature:**

```python
browser_mouse_wheel(
    context: str,
    delta_x: int = 0,
    delta_y: int = 0,
) -> dict
```

**Purpose:** Scroll the mouse wheel by the given pixel deltas at the current cursor position.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `delta_x` | `int` | `0` | Horizontal scroll in CSS pixels (positive = right). |
| `delta_y` | `int` | `0` | Vertical scroll in CSS pixels (positive = down). |

**Returns:**

- `scrolled` — `[delta_x, delta_y]`.

**Notes:** At least one of `delta_x` or `delta_y` must be non-zero. Position the cursor first with `browser_mouse_move_xy` to target a specific scrollable container.

### Inspection (inspection.py)

#### browser_snapshot

**Signature:**

```python
browser_snapshot(
    context: str,
    selector: str | None = None,
) -> dict
```

**Purpose:** Capture an accessibility snapshot of the active page in LLM-friendly YAML.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `selector` | `str \| None` | `None` | Optional CSS or aria selector to scope the snapshot to a subtree. When provided, refs are NOT included in the output. |

**Returns:**

- `snapshot` — YAML string of the accessibility tree.
- `url` — current page URL.

**Notes:** Default mode (`selector=None`) uses the internal `snapshotForAI` channel and annotates every interactive element with `[ref=eN]`. Selector mode uses `Locator.aria_snapshot` and returns plain aria YAML without refs.

#### browser_screenshot

**Signature:**

```python
browser_screenshot(
    context: str,
    image_format: str = "png",
    *,
    full_page: bool = False,
) -> dict
```

**Purpose:** Take a visual screenshot of the active page and return it as base64.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `image_format` | `str` | `"png"` | `"png"` (lossless) or `"jpeg"` (lossy, smaller). |
| `full_page` | `bool` | `False` | Capture the entire scrollable page instead of just the viewport. |

**Returns:**

- `image_base64` — base64-encoded image bytes.
- `image_format` — the format used.
- `width` — final image width in pixels (`None` when PIL is unavailable).
- `height` — final image height in pixels (`None` when PIL is unavailable).

**Notes:** When PIL/Pillow is installed, oversized images are automatically downscaled so the longest side is at most 1568 px (Claude vision limit). The `width`/`height` fields reflect the final, possibly downscaled dimensions.

#### browser_console_messages

**Signature:**

```python
browser_console_messages(
    context: str,
    level: str | None = None,
) -> dict
```

**Purpose:** Return all console messages collected since the context was created.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `level` | `str \| None` | `None` | Filter by message type: `"log"`, `"info"`, `"warning"`, `"error"`, or `"debug"`. `None` returns all. |

**Returns:**

- `messages` — list of `{"type": str, "text": str, "location": str | null}` objects.

**Notes:** The buffer is cumulative and never cleared — it includes all messages across all pages and all navigations in the context. Uncaught page errors are captured as `type="error"` entries with `location=null`.

#### browser_network_requests

**Signature:**

```python
browser_network_requests(
    context: str,
    url_filter: str | None = None,
    *,
    static: bool = False,
) -> dict
```

**Purpose:** Return all network requests collected since the context was created.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `url_filter` | `str \| None` | `None` | Python regular expression; only matching URLs are returned (applied after the static filter). |
| `static` | `bool` | `False` | Include static asset requests (image, font, stylesheet, media, manifest). |

**Returns:**

- `requests` — list of `{"url": str, "method": str, "status": int | null, "resource_type": str, "failure": str | null}` objects.

**Notes:** The buffer is cumulative and never cleared. By default, static resource types (image/font/stylesheet/media/manifest) are filtered out; pass `static=True` to include them.

### Verification (verification.py)

#### browser_verify_element_visible

**Signature:**

```python
browser_verify_element_visible(
    context: str,
    ref: str,
) -> dict
```

**Purpose:** Verify that the element identified by `ref` is currently visible on the page.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Element ref from `browser_snapshot`. |

**Returns:**

- `visible` — `True`.
- `ref` — the ref that was checked.

**Notes:** The visibility check is synchronous (no waiting). Refs in iframes are resolved by falling back through child frames.

#### browser_verify_list_visible

**Signature:**

```python
browser_verify_list_visible(
    context: str,
    refs: list[str] | None = None,
    container_ref: str | None = None,
    items: list[str] | None = None,
) -> dict
```

**Purpose:** Verify visibility of multiple elements in either refs or container mode.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `refs` | `list[str] \| None` | `None` | Refs mode: list of refs that must all be visible. Mutually exclusive with `container_ref`/`items`. |
| `container_ref` | `str \| None` | `None` | Container mode: ref of the parent element. Required when using `items`. |
| `items` | `list[str] \| None` | `None` | Container mode: list of text strings that must be visible as descendants of `container_ref`. |

**Returns (refs mode):**

- `visible_refs` — list of verified refs.

**Returns (container mode):**

- `container_ref` — the container ref used.
- `verified_items` — list of item texts that were verified visible.

#### browser_verify_text_visible

**Signature:**

```python
browser_verify_text_visible(
    context: str,
    text: str,
) -> dict
```

**Purpose:** Verify that the given text is currently visible somewhere on the active page.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `text` | `str` | — | Text to look for (case-insensitive substring match). |

**Returns:**

- `text` — the text that was checked.
- `visible` — `True`.

**Notes:** Searches the main frame and all child frames. Uses `.first` to avoid strict-mode violations when text matches multiple elements.

#### browser_verify_value

**Signature:**

```python
browser_verify_value(
    context: str,
    ref: str,
    expected_value: str,
    element_type: str = "text",
) -> dict
```

**Purpose:** Verify the value or checked state of an input element.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str` | — | Element ref from `browser_snapshot`. |
| `expected_value` | `str` | — | Expected value (string for `"text"` mode; coerced to bool for `"checkbox"`/`"radio"`). |
| `element_type` | `str` | `"text"` | One of `"text"` (read via `input_value()`), `"checkbox"`, or `"radio"` (read via `is_checked()`). |

**Returns:**

- `ref` — the ref that was verified.
- `value` — the actual value found (`str` for text mode, `bool` for checkbox/radio).
- `element_type` — the mode used.

### Code execution (code_execution.py)

#### browser_evaluate

**Signature:**

```python
browser_evaluate(
    context: str,
    expression: str,
    ref: str | None = None,
    selector: str | None = None,
) -> dict
```

**Purpose:** Evaluate a JavaScript expression on the active page and return its result.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `expression` | `str` | — | JavaScript expression (not a statement) to evaluate. Arrow functions are supported. |
| `ref` | `str \| None` | `None` | Optional accessibility ref; runs the expression via `locator.evaluate()` with the element as the first argument. Mutually exclusive with `selector`. |
| `selector` | `str \| None` | `None` | Optional CSS/aria selector; same semantics as `ref`. Mutually exclusive with `ref`. |

**Returns:**

- `result` — the JSON-serialized return value (non-serializable values become `null`).

**Notes:** When neither `ref` nor `selector` is provided, the expression runs at page scope. Use `browser_run_code` for multi-step Python logic that needs Playwright's full async API.

#### browser_run_code

**Signature:**

```python
browser_run_code(
    context: str,
    code: str,
) -> dict
```

**Purpose:** Execute a Python async code snippet with full Playwright access.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `code` | `str` | — | Python code body. Runs as the body of an async function with `page`, `context` (BrowserContext), and `ctx_mgr` in scope. Use `return` to send a value back. |

**Returns:**

- `result` — the return value of the snippet, or `null`.

**Notes:** Any exception raised inside the snippet is returned as `evaluation_failed` with the original traceback included in the message.

### Cookies and storage (cookies.py)

#### browser_get_cookies

**Signature:**

```python
browser_get_cookies(
    context: str,
    urls: list[str] | None = None,
    name: str | None = None,
) -> dict
```

**Purpose:** Return cookies stored in the context, optionally filtered by URL and name.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `urls` | `list[str] \| None` | `None` | List of full URLs to filter cookies by domain/path rules. `None` returns all cookies. |
| `name` | `str \| None` | `None` | Exact cookie name to filter by (applied after URL filtering). |

**Returns:**

- `cookies` — list of cookie objects with `name`, `value`, `domain`, `path`, `expires`, `httpOnly`, `secure`, and `sameSite` fields.

#### browser_set_cookies

**Signature:**

```python
browser_set_cookies(
    context: str,
    cookies: list[dict],
) -> dict
```

**Purpose:** Add or update cookies on the context using Playwright cookie format.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `cookies` | `list[dict]` | — | List of cookie dicts. Each must have at minimum `name` and `value`, plus either `domain`+`path` or `url`. Optional fields: `path` (default `"/"`), `expires`, `httpOnly`, `secure`, `sameSite`. |

**Returns:**

- `set_count` — number of cookies applied.

**Notes:** When a cookie has neither `domain` nor `url`, the active page's hostname is used as the default domain. To persist cookies across sessions, call `browser_export_context_state` afterward.

#### browser_clear_cookies

**Signature:**

```python
browser_clear_cookies(
    context: str,
) -> dict
```

**Purpose:** Remove all cookies from the context across all domains.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |

**Returns:**

- `cleared` — `True`.

#### browser_get_local_storage

**Signature:**

```python
browser_get_local_storage(
    context: str,
    origin: str,
    key: str | None = None,
) -> dict
```

**Purpose:** Read localStorage for the given origin.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `origin` | `str` | — | Fully-qualified URL including scheme (e.g. `"https://example.com"`). |
| `key` | `str \| None` | `None` | Specific key to read. `None` returns all items. |

**Returns (key is `None`):**

- `items` — dict of all key-value pairs.
- `origin` — the origin that was queried.

**Returns (key provided):**

- `key` — the key queried.
- `value` — the value string, or `null` if the key does not exist.
- `origin` — the origin that was queried.

**Notes:** Opens a temporary page to navigate to the origin, reads localStorage, then closes it. The context's active page is not disturbed.

#### browser_set_local_storage

**Signature:**

```python
browser_set_local_storage(
    context: str,
    origin: str,
    items: dict[str, str],
) -> dict
```

**Purpose:** Set localStorage key-value pairs for the given origin.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `origin` | `str` | — | Fully-qualified URL including scheme. |
| `items` | `dict[str, str]` | — | Key-value pairs to set. All values must be strings. |

**Returns:**

- `set_count` — number of items written.
- `origin` — the origin that was written to.

**Notes:** Opens a temporary page for the origin, sets each item, then closes it. The context's active page is not disturbed.

#### browser_clear_local_storage

**Signature:**

```python
browser_clear_local_storage(
    context: str,
    origin: str | None = None,
) -> dict
```

**Purpose:** Clear localStorage entries for an origin or for the currently active page.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `origin` | `str \| None` | `None` | Fully-qualified URL to clear. When omitted, clears localStorage on the currently active page directly. |

**Returns:**

- `cleared` — `True`.
- `origin` — the origin URL that was cleared.

### Utility (utility.py)

#### browser_resize

**Signature:**

```python
browser_resize(
    context: str,
    width: int,
    height: int,
) -> dict
```

**Purpose:** Resize the viewport of the active page to the given pixel dimensions.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `width` | `int` | — | Viewport width in pixels. |
| `height` | `int` | — | Viewport height in pixels. |

**Returns:**

- `width` — the width applied.
- `height` — the height applied.

**Notes:** Affects only the active page; other tabs are unchanged.

#### browser_pdf_save

**Signature:**

```python
browser_pdf_save(
    context: str,
    file_path: str | None = None,
    paper_format: str = "A4",
    *,
    landscape: bool = False,
    print_background: bool = False,
) -> dict
```

**Purpose:** Render the active page as a PDF and save it to the given file path.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `file_path` | `str \| None` | `None` | Destination path. When omitted, defaults to `$JUSTPEN_WORKSPACE/output/evidence/page-{timestamp}.pdf`. |
| `paper_format` | `str` | `"A4"` | Paper size string: `"A4"`, `"Letter"`, `"A3"`, etc. |
| `landscape` | `bool` | `False` | Rotate to landscape orientation. |
| `print_background` | `bool` | `False` | Include CSS backgrounds in output. |

**Returns:**

- `saved_to` — the absolute path the PDF was written to.
- `size_bytes` — size of the PDF file in bytes.

**Notes:** Parent directories of `file_path` are created automatically. Only works in headless mode.

#### browser_generate_locator

**Signature:**

```python
browser_generate_locator(
    context: str,
    ref: str | None = None,
    selector: str | None = None,
    element: str | None = None,
) -> dict
```

**Purpose:** Generate a stable, durable Playwright locator for an element.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `ref` | `str \| None` | `None` | Ephemeral snapshot ref to resolve into a stable locator. Mutually exclusive with `selector`. |
| `selector` | `str \| None` | `None` | Raw CSS selector to pass through verbatim. Mutually exclusive with `ref`. |
| `element` | `str \| None` | `None` | Optional free-form human description (logged; not used by the implementation). |

**Returns:**

- `ref` — the ref that was resolved, if any.
- `selector` — the selector that was passed through, if any.
- `internal_selector` — durable Playwright selector string usable with `page.locator()`.
- `python_syntax` — human-readable Python API call string (e.g. `get_by_role("button", name="Submit")`).

**Notes:** Exactly one of `ref` or `selector` must be provided. For `ref` mode, resolution priority is: data-testid > ARIA role+name > label > placeholder > alt text > title > text content > CSS fallback.

#### browser_tabs

**Signature:**

```python
browser_tabs(
    context: str,
    action: str,
    index: int | None = None,
    url: str | None = None,
) -> dict
```

**Purpose:** Manage tabs (pages) within a browser context.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |
| `action` | `str` | — | One of `"list"`, `"new"`, `"close"`, `"select"`. |
| `index` | `int \| None` | `None` | Tab index (required for `"close"` and `"select"`). |
| `url` | `str \| None` | `None` | URL to navigate to when opening a new tab (only for `"new"`). |

**Returns:**

- `"list"`: `tabs` — list of `{"index": int, "url": str}` objects.
- `"new"`: `index` (new tab index), `url` (URL after navigation).
- `"close"`: `closed_index` — the index that was closed.
- `"select"`: `selected_index` — the index that is now active.

### Page (page.py)

#### browser_close

**Signature:**

```python
browser_close(
    context: str,
) -> dict
```

**Purpose:** Close the active page (tab) in the context, keeping the context alive.

**Parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `context` | `str` | — | Context name. |

**Returns:**

- `closed` — `True` when a page was closed, or `False` when there were no open pages.
- `reason` — `"no open pages"` (only present when `closed` is `False`).

**Notes:** Only the currently active page is closed; other tabs remain open. Use `browser_destroy_context` to tear down the entire browser session.

### Server (server_tools.py)

#### browser_status

**Signature:**

```python
browser_status() -> dict
```

**Purpose:** Report server health without triggering a browser launch.

**Returns:**

- `browser_running` — `True` if the Camoufox process is alive.
- `active_context_count` — number of currently registered contexts.
- `active_contexts` — list of `{"context": str}` objects.

**Notes:** This is the only tool safe to call before the browser is launched or after it has shut down. All other tools require an active context. `context` in the envelope is `null` (server-level tool).

## Development

```bash
make setup       # install deps + fetch Camoufox binary
make check       # format + lint + typecheck + test (non-e2e)
make test-e2e    # e2e tests (requires Camoufox installed)
make docs-build  # build the MkDocs site (strict)
make docs-serve  # serve docs locally with live reload
make bump-patch  # bump patch version, commit, and tag locally
```

Walk `docs/contributing/pr-checklist.md` before opening a pull request, and
see `docs/contributing/release-process.md` for the full tag-and-merge flow
used by the `bump-*` targets. Lint, type-check, and LSP conventions are
documented under `docs/contributing/lint-typing.md` and
`docs/contributing/code-intelligence.md`.

## License

MIT — see `LICENSE`.
