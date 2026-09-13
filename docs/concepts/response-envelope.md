---
description: The success and error envelope shapes returned by every tool.
---

# Response envelope { #_top }

Every tool returns one of two envelope shapes, with additive `operation` metadata.
Tool-reference examples omit that shared metadata for readability. Argument-validation errors also include metadata while preserving MCP `isError`.

## Success { #success }

```json
{
  "status": "success",
  "instance": "<instance-name> | null",
  "data": {}
}
```

## Error { #error }

```json
{
  "status": "error",
  "instance": "<instance-name> | null",
  "error_type": "<type>",
  "message": "<human-readable description>"
}
```

`instance` is `null` for server-level tools (`browser_list_instances`, `browser_health`) that are not scoped to a specific instance.

### error_type values { #error_type-values }

| `error_type`              | Meaning                                                                                                                        |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `instance_not_found`      | No instance with the given name exists; call `browser_create_instance` first.                                                  |
| `instance_already_exists` | That name is reserved by a live instance, launch, or unfinished teardown.                                                      |
| `instance_limit_exceeded` | The `BROWSER_MCP_MAX_INSTANCES` cap has been reached; destroy an existing instance first.                                      |
| `instance_crashed`        | The browser disconnected; cleanup is scheduled. Check health and wait for its reservation to be released before recreating it. |
| `profile_dir_in_use`      | The requested profile is reserved by another live, launching, or closing instance.                                             |
| `binary_not_found`        | The latest Camoufox release could not be resolved, prepared, or verified.                                                      |
| `element_not_found`       | The element could not be found in the page's accessibility tree.                                                               |
| `stale_ref`               | The `ref` was valid in a previous snapshot but is no longer in the current accessibility tree.                                 |
| `navigation_failed`       | A network error, invalid URL, or page crash prevented navigation.                                                              |
| `navigation_timeout`      | The page did not finish loading within the timeout.                                                                            |
| `wait_timeout`            | A text or state wait condition did not resolve in time.                                                                        |
| `dialog_not_present`      | Reserved error type; current tools use `modal_state_blocked` when no matching modal is pending.                                |
| `evaluation_failed`       | A JavaScript expression or Python code snippet raised an exception.                                                            |
| `verification_failed`     | A verification tool found the element or text was not in the expected state.                                                   |
| `invalid_params`          | A parameter value was invalid or an incompatible combination was supplied.                                                     |
| `modal_state_blocked`     | A pending modal blocks the operation, or a dialog/upload handler was called without its matching pending modal.                |
| `internal_error`          | An unexpected tool or framework error without a more specific mapping.                                                         |
| `operation_timeout`       | A cooperative operation, including its lock wait, exceeded the server deadline.                                                |
| `result_too_large`        | The structured result exceeded the configured byte limit; the action may already have completed.                               |
| `unsupported_capability`  | The active browser backend cannot perform this operation (currently PDF rendering).                                            |
| `page_not_found`          | The requested page is not live in this instance.                                                                               |
| `frame_not_found`         | The requested frame is detached or belongs to a different page.                                                                |
| `observation_timeout`     | The action completed but its requested condition did not match before the deadline.                                            |
| `download_not_found`      | The download ID is foreign, evicted, or no longer retained.                                                                    |
| `download_failed`         | Download saving failed; a partial file may remain.                                                                             |

## Operation metadata

Every application envelope carries the same metadata object:

```json
{
  "operation": {
    "id": "request-uuid",
    "tool": "browser_navigate",
    "instance_id": "launch-uuid",
    "page_id": "tab-uuid",
    "frame_id": null,
    "started_at": "2026-09-12T10:00:00+00:00",
    "finished_at": "2026-09-12T10:00:00.250000+00:00",
    "duration_ms": 250.0,
    "outcome": "completed",
    "retry": "not_needed",
    "artifacts": []
  }
}
```

IDs are nullable when there is no target or it was not yet allocated. A recreated
instance and a new page always have new IDs. `duration_ms` includes queue waiting
and uses monotonic time; timestamps are UTC. The ID correlates a call, not a
persistent job or an idempotency key.

| Field value               | Meaning                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| `outcome: completed`      | The tool returned success; a later size-limit error can still prevent delivery of its data. |
| `outcome: not_started`    | The request was rejected before entering the instance operation.                            |
| `outcome: unknown`        | Execution began and failed; side effects may have happened.                                 |
| `retry: not_needed`       | The result succeeded.                                                                       |
| `retry: after_correction` | Correct the request or target state before retrying.                                        |
| `retry: read_only`        | The failed tool reads state; its next result can differ if the page changes.                |
| `retry: inspect_state`    | Inspect state before repeating a potentially completed action.                              |

The classification is conservative: entering the operation can mark an eventual
validation failure as `unknown` even if the browser was not changed. No mutation
is automatically retried. A cancelled call may have no response; server logs
record the operation ID and whether execution had started.

`artifacts` lists returned server-side `path`/`saved_to` references. These are not
uploads or integrity guarantees. If oversized references themselves prevent a
bounded error response, `references_omitted: true` is set, `artifacts` is empty,
and the display `instance` name is null; an oversized unknown tool name can also
be omitted. Stable target IDs are preserved.

`BROWSER_MCP_MAX_RESULT_BYTES` bounds the serialized structured envelope including
metadata. Large results return `result_too_large`; use smaller queries, event
pagination, or explicit file output. See [framework integration](../guides/framework-integration.md)
for recovery and evidence collection.
