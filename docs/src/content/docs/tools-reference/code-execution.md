---
title: Code execution
description: Evaluate JavaScript inside the page context.
---

Execute JavaScript or Python code against the active page. Use `browser_evaluate` for single JavaScript expressions; use `browser_run_code` for multi-step Python logic that needs Playwright's full async API.

## browser_evaluate

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

## browser_run_code

Execute a Python async code snippet with full Playwright access.

**Signature**

```python
async def browser_run_code(instance: str, code: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description                                                                                                                                                            |
| ---------- | ----- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `instance` | `str` | —       | Instance name.                                                                                                                                                         |
| `code`     | `str` | —       | Python code body. Runs as the body of an async function with `page`, `context` (Playwright BrowserContext), and `ctx_mgr` in scope. Use `return` to send a value back. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{ "result": "Task Complete" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found`
- `modal_state_blocked` — a dialog or file chooser is pending; resolve it first
- `evaluation_failed` — Python exception raised inside the snippet; error message includes the original traceback

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

**Notes** — The snippet runs with `page`, `context` (the Playwright BrowserContext object), and `ctx_mgr` (InstanceManager, for advanced use) in scope. Any exception raised is caught and returned as `evaluation_failed` with the original traceback included in the message.
