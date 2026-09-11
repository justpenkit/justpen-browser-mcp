---
description: Evaluate JavaScript in the page and trusted Python in the server process.
---

# Code execution { #_top }

Execute JavaScript or Python code against the active page. Use `browser_evaluate` for single JavaScript expressions; use `browser_run_code` for multi-step Python logic that needs Playwright's full async API.

JavaScript evaluations use Camoufox's **isolated JS world**: `window.*` globals set by the page's own scripts are not visible to your expression, and values your expression assigns to `window` are not visible to the page's scripts either. DOM state, browser storage, and evaluation results remain available. This JavaScript behavior is separate from `browser_run_code`, which executes trusted Python inside the server process with that process's permissions.

Examples below focus on tool-specific data. Registered tools also return the shared [operation metadata and error fields](../concepts/response-envelope.md).

## browser_evaluate { #browser_evaluate }

Evaluate a JavaScript expression on the active page and return its result.

**Signature**

```python
async def browser_evaluate(instance: str, expression: str, ref: str | None = None, selector: str | None = None) -> dict[str, Any]
```

**Parameters**

| Name         | Type          | Default | Description                                                                                                                                                                  |
| ------------ | ------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance`   | `str`         | —       | Instance name.                                                                                                                                                               |
| `expression` | `str`         | —       | JavaScript expression (not a statement) to evaluate. Arrow functions are supported.                                                                                          |
| `ref`        | `str \| None` | `None`  | Optional accessibility ref from `browser_snapshot`; runs the expression via `locator.evaluate()` with the element as the first argument. Mutually exclusive with `selector`. |
| `selector`   | `str \| None` | `None`  | Optional CSS/aria selector; same semantics as `ref`. Mutually exclusive with `ref`.                                                                                          |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "result": "Example Domain" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `invalid_params` — both `ref` and `selector` were provided
- `stale_ref` — ref no longer valid; take a fresh snapshot
- `modal_state_blocked` — a dialog or file-chooser is pending; resolve it first
- `evaluation_failed` — JS syntax error, runtime exception, or timeout
- `operation_timeout` — the overall instance operation deadline expired

**Example**

Request:

```json
{ "name": "browser_evaluate", "arguments": { "instance": "main", "expression": "document.title" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "result": "Example Domain" } }
```

**Notes** — When neither `ref` nor `selector` is provided, the expression runs at page scope. Non-serializable values (DOM nodes, functions) return `null`. Use `browser_run_code` for multi-step Python logic that needs Playwright's full async API.

If the expression opens a JavaScript dialog and remains pending, call `browser_handle_dialog` concurrently to resolve it. That recovery call has an independent lock.

## browser_run_code { #browser_run_code }

Execute a Python async code snippet with full Playwright access.

**Signature**

```python
async def browser_run_code(instance: str, code: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                                                                                                                                        |
| ---------- | ----- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `instance` | `str` | —       | Instance name.                                                                                                                                                     |
| `code`     | `str` | —       | Python code body. Runs as the body of an async function with `page`, `context` (Playwright BrowserContext), and `mgr` in scope. Use `return` to send a value back. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "result": "Task Complete" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked` — a dialog or file chooser is pending; resolve it first
- `evaluation_failed` — Python exception raised inside the snippet; error message includes the original traceback
- `operation_timeout` — a cooperative async wait exceeded the instance operation deadline
- `result_too_large` — the returned result exceeds the configured response limit

**Example**

Request:

```json
{
  "name": "browser_run_code",
  "arguments": {
    "instance": "main",
    "code": "await page.wait_for_selector('#done')\nreturn await page.title()"
  }
}
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "result": "Task Complete" } }
```

**Notes** — The snippet runs with `page`, `context` (the Playwright BrowserContext object), and `mgr` (InstanceManager, for advanced use) in scope. Return a JSON-compatible value. Ordinary Python exceptions return `evaluation_failed` with the original traceback included in the message.

This is intentional trusted code execution: imports, filesystem access, and process access use the server's permissions. Instance separation does not sandbox Python snippets. Use an external supervisor when the framework needs a hard execution limit or a separate process boundary.

The configured operation timeout bounds lock acquisition and cooperative async work. A synchronous infinite loop or blocking Python call can stall the event loop for every instance and cannot be interrupted by that cooperative timeout. Cancellation or a timeout also does not roll back actions already performed; use the returned operation metadata and inspect browser state before retrying.
