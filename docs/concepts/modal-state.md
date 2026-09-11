---
description: Detecting and handling modal dialogs across tools.
---

# Modal state { #_top }

Pending JS dialogs (`alert`, `confirm`, `prompt`) and native file-choosers are captured by event listeners on the context and tracked as "modal state". Most tools check for pending modal state before running and return `modal_state_blocked` if one is present.

To unblock:

- JS dialog: call `browser_handle_dialog`.
- File chooser: call `browser_file_upload`.

## How modal state is tracked { #how-modal-state-is-tracked }

Modal state is **not** embedded in `browser_snapshot` output — the server
never reads snapshot data to detect a pending modal. Instead, each instance
wires page-level `dialog` and `filechooser` event listeners at creation time;
when a native JS dialog or file-chooser fires, the listener appends an entry
to that instance's in-memory `modal_states` list, capturing the underlying
Playwright `Dialog`/`FileChooser` object plus the page it fired on.

Before touching the page, almost every tool (including `browser_snapshot`
itself) checks for pending modals after acquiring its action lock. If any modal state
is pending, the tool short-circuits and returns `modal_state_blocked` instead
of running — `browser_snapshot` never gets far enough to capture a snapshot,
so there is no "modal type" field to read out of one.

To unblock:

- JS dialog: call `browser_handle_dialog`, which pops the oldest pending
    `dialog` entry, calls `.accept()` or `.dismiss()` on it, and consumes it
    from the pending list.
- File chooser: call `browser_file_upload`, which pops the oldest pending
    `filechooser` entry and sets the requested file paths on it.

Resolution uses a separate per-instance recovery lock, so it can run while a
click is blocked by the dialog. A successful resolution consumes one matching
entry. Recoverable failures or cancellation retain the entry while its page is
alive. A definitive already-handled dialog error discards that irrecoverable
cached object and returns an error; inspect the page before continuing. If no
matching modal is pending, both tools return `modal_state_blocked` themselves.

## Recovering from unexpected modals { #recovering-from-unexpected-modals }

If a tool call fails with a modal-related `error_type`, dismiss the modal
first (via the appropriate interaction tool), inspect page state, and check the
[operation outcome](response-envelope.md#operation-metadata) before retrying. Swallowing the error
and retrying blindly will often hang.

## Resolving a dialog while an action waits { #gotcha-a-dialog-triggering-click-can-hold-the-lock-for-30s }

A click that opens `alert`, `confirm`, or `prompt` may wait for the dialog to be
resolved. `browser_handle_dialog` and `browser_file_upload` use the independent
modal recovery lock; they do not wait behind the action lock held by that click.
An orchestrator capable of concurrent MCP calls can issue the recovery call while
the original action remains pending. A sequential client may instead see the
action time out first, then resolve the modal and inspect the page before retrying.

Queued actions recheck modal state after acquiring their lock. This catches a
modal that appeared while they waited. Recoverable resolution failures keep the pending object available for recovery;
entries belonging to closed pages and definitively already-handled dialogs are
discarded. A discarded object is not evidence that the original action succeeded.
