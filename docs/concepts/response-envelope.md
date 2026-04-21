# Response envelope

Every tool returns one of two envelope shapes.

## Success

```json
{
  "status": "success",
  "context": "<context-name> | null",
  "data": {}
}
```

## Error

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
