# Response envelope

Every tool returns one of two envelope shapes.

## Success

```json
{
  "status": "success",
  "instance": "<instance-name> | null",
  "data": {}
}
```

## Error

```json
{
  "status": "error",
  "instance": "<instance-name> | null",
  "error_type": "<type>",
  "message": "<human-readable description>"
}
```

`instance` is `null` for server-level tools (`browser_list_instances`) that are not scoped to a specific instance.

### error_type values

| `error_type` | Meaning |
|---|---|
| `instance_not_found` | No instance with the given name exists; call `browser_create_instance` first. |
| `instance_already_exists` | An instance with that name is already registered. |
| `instance_limit_exceeded` | The `BROWSER_MCP_MAX_INSTANCES` cap has been reached; destroy an existing instance first. |
| `profile_dir_in_use` | The requested `profile_dir` is already locked by another live instance. |
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
