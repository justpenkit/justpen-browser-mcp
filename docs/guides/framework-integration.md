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

## Explicit targets and frame refs

Retain `instance_id`, `page_id`, and `frame_id` with your workflow state. Address a
page directly instead of selecting a tab before each action. Call `browser_frames`
to find the containing frame, capture its snapshot, and reuse both IDs with its
refs. Explicit targets do not change tab selection and never fall back to another
page or frame. Frame navigation retains the frame ID but requires a fresh snapshot.

## Action observations

Pass optional `wait_for` to click, type, fill-form, select-option, hover, drag,
press-key, and coordinate mouse click/drag/wheel. `WaitForSpec` in the signatures
means one JSON object selected by `kind`:

| `kind`     | Required fields | Optional fields                                                | Match                                                                                                    |
| ---------- | --------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `response` | `url`           | `method`, `status` (100–599)                                   | Exact response URL; its request must begin after observation is armed.                                   |
| `url`      | `url`           | —                                                              | A subsequent navigation of the resolved frame reaches the exact URL, including same-document navigation. |
| `element`  | `selector`      | `state`: `attached`, `detached`, `visible` (default), `hidden` | DOM condition after the action.                                                                          |
| `text`     | `text`          | `state`: `visible` (default), `hidden`                         | Literal text condition after the action.                                                                 |
| `popup`    | —               | —                                                              | A popup opened by the target page.                                                                       |
| `download` | —               | —                                                              | A download emitted by the target page.                                                                   |

All kinds accept positive integer `timeout_ms` (default 10000); unknown fields
are rejected. Response URLs are exact strings, not patterns. Method matching is
case-normalized. An explicit `frame_id` narrows response matching to that frame;
otherwise responses may originate in any frame of the target page. Element/text
conditions may already hold and do not imply a transition. A response match means
headers/status arrived, not that its response body finished downloading.

The observer is armed before the action executes, so an event during the action
can satisfy it. The timeout starts after the action, and both share the existing
overall operation deadline. The action executes once. No retry, compound condition,
or automatic business-success inference is performed. When supplied, the explicit
observation replaces type/Enter's extra best-effort page-load wait.

```json
{
  "name": "browser_click",
  "arguments": {
    "instance": "checkout", "page_id": "page-uuid", "frame_id": "frame-uuid",
    "ref": "e12",
    "wait_for": {"kind": "response", "url": "https://example.com/orders", "method": "POST", "status": 201, "timeout_ms": 10000}
  }
}
```

Success retains existing action keys and adds `data.observation` with `kind`,
`matched: true`, and observed facts. Popup observations return the popup's
`page_id` without selecting it. Downloads return a `download_id` for explicit saving.
A completed action whose condition times out returns `observation_timeout` with
`data.action_completed: true`, its action result and an unmatched observation.
An outer operation deadline can return `operation_timeout` with the same completion
marker if it expired during observation. Outcome remains `unknown` and retry advice
is `inspect_state`; do not repeat a possibly successful submission automatically.
This is temporal association, not proof that the action caused a particular request.

## Original screenshots and retained downloads

For original screenshot files, supply `original: true` and an explicit `path`.
The saved bytes come directly from Playwright, while `original: false` preserves
the 1568px preview behavior. `source_width`/`source_height` describe source pixels;
`width`/`height` describe the delivered image. Original output is file-only, though
Playwright still allocates the bytes in memory. Paths name server files that your
framework must collect.

Downloads are retained per instance with stable IDs, including those triggered by
navigation or an action observation. Use `browser_downloads` to inspect availability
and `browser_download_save` to choose a destination explicitly. Save before bounded
retention evicts the handle; neither suggested names nor response URLs are file
paths. Failures and cancellation can leave partial files, and teardown ends access
to browser-managed temporary files.

## Automatic HTTP identity headers

The server enables three generated headers by default:

| Header                                   | Value                                                                    |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| `Justpen-Browser-Metadata-Instance-Name` | Percent-encoded UTF-8 instance name; decode once when displaying it.     |
| `Justpen-Browser-Metadata-Instance-ID`   | Current launch UUID, equal to MCP `instance_id`.                         |
| `Justpen-Browser-Metadata-Page-ID`       | Containing page UUID, equal to MCP `page_id`, including iframe requests. |

Instance headers are installed at context creation; Page-ID is installed on the
actual page, with controlled page creation waiting for setup before navigation.
Native popup or restored-page startup traffic can begin before the Page object is
available, so the server cannot guarantee Page-ID on that earliest traffic.
On Camoufox 152.0.4-beta.30 with Playwright 1.61, the HTTP receiver observed both
instance headers on the first popup request and no Page-ID. The next controlled
popup navigation carried its own Page-ID. The server does not substitute the
opener's ID or intercept the first request.
Page-ID stays stable through navigation and independent of selected-tab changes.
Persistent profile reopen creates fresh instance/page IDs; header configuration
is not stored in the profile. This uses extra-header APIs, not request interception.

Set `BROWSER_MCP_METADATA_HEADERS_ENABLED=false` to disable these automatic headers
at server startup. Network evidence retains its ordinary request IDs/timestamps;
no Request-ID or Timestamp HTTP header is generated. External systems own traffic
scope, proxy processing, retention, and correlation. Treat IDs as correlation
metadata, not authentication or proof of request causation.
