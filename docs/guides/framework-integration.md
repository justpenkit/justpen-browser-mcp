---
description: Integrating instance ownership, bounded execution, recovery, and evidence into an orchestrator.
---

# Framework integration

This server owns browser instances and browser actions. Your framework owns job
scheduling, authorization and target scope, credentials, retry decisions, durable
evidence, and process supervision. The browser server does not schedule pentests
or decide which targets a job may access.

## Instance ownership

Assign an instance name to a workflow and record the returned `instance_id`.
Keep related cookies and storage in that instance; use separate instances for
different sessions. Ephemeral sessions disappear at teardown. A persistent
`profile_dir` survives and remains reserved until its browser has closed.

Use `browser_tabs` to obtain stable `page_id` values when your workflow targets
multiple tabs. Select or close by `page_id` when an index may have moved. Most
tools act on the currently selected page. After a crash/recreation, treat the
new `instance_id` as a new session and reconcile workflow state explicitly.

## Execution and retries

Store each result's `operation.id`, target identities, timestamps, and outcome
with your job record. These IDs correlate calls; they are not idempotency keys
and the server does not deduplicate repeated calls.

- `completed`: the tool returned successfully, even if its result was too large
    to send inline. Check `error_type` as well as the operation outcome.
- `not_started`: execution did not enter the instance operation. Correct the
    request or instance state before retrying.
- `unknown`: execution started but failed before confirming the result. A click,
    submission, navigation, cookie write, or file write may already have happened.

Follow the [retry metadata](../concepts/response-envelope.md#operation-metadata).
Inspect the page, application state, and evidence before repeating a mutation.
Cancellation or a disconnected client may receive no response at all; reconcile
state after reconnecting instead of assuming the action never ran. Server logs
include operation IDs for diagnosis, but are not a durable job journal.

Actions serialize per instance. Modal recovery calls use their own lock and can
unblock an in-flight click if your MCP client supports concurrent requests. See
[modal recovery](../concepts/modal-state.md).

## Evidence collection

Console and network streams retain the latest configured number of entries per
instance. Poll with `limit` and `after`; persist the returned `next_cursor` with
the same filters. Check `retention_lost`, `dropped_count`, and `truncated_fields`.
A network response or failure advances its sequence while keeping `request_id`;
upsert by that ID to update the previously observed pending request.

Use `path` on console/network queries to export that retained page as JSON, or
on screenshots to save the image. Exports do not recover evicted data or reverse
field truncation. Paths refer to the server's filesystem; the tool does not upload
them to the client. Your framework must collect the artifacts, establish retention
and access rules, and record any integrity hashes it needs.

The structured result size is bounded. For `result_too_large`, reduce page size
or scope, or request file output. Check `operation.outcome` before repeating the
original action. `browser_pdf_save` returns `unsupported_capability` because this
Firefox backend does not support Playwright PDF rendering.

## Process supervision

The operation deadline bounds cooperative asynchronous work and lock waiting.
Trusted `browser_run_code` has normal Python capabilities in the server process;
synchronous CPU loops or blocking system calls can prevent the event loop from
enforcing a deadline. Async cancellation is also cooperative. Use an external
supervisor with a wall-clock deadline and process/container resource limits
when your framework requires a hard stop.

Separate Camoufox processes isolate browser session state, but share the host
and Python server. Strong isolation between untrusted workloads needs an external
boundary. The HTTP transport has no built-in authentication; apply the deployment
controls described in [running the server](../getting-started/run-server.md).

On teardown failure, `browser_health` retains `close_failed` entries or failed
launch cleanup records and the corresponding reservations. Investigate and stop
surviving browser processes before restarting the server. Reusing the same profile
while its previous browser is alive is unsafe.
