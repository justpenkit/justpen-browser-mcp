---
title: Modal state
description: Detecting and handling modal dialogs across tools.
---

Pending JS dialogs (`alert`, `confirm`, `prompt`) and native file-choosers are captured by event listeners on the context and tracked as "modal state". Most tools check for pending modal state before running and return `modal_state_blocked` if one is present.

To unblock:

- JS dialog: call `browser_handle_dialog`.
- File chooser: call `browser_file_upload`.

## How modal state is tracked

Modal state is **not** embedded in `browser_snapshot` output — the server
never reads snapshot data to detect a pending modal. Instead, each instance
wires page-level `dialog` and `filechooser` event listeners at creation time;
when a native JS dialog or file-chooser fires, the listener appends an entry
to that instance's in-memory `modal_states` list, capturing the underlying
Playwright `Dialog`/`FileChooser` object plus the page it fired on.

Before touching the page, almost every tool (including `browser_snapshot`
itself) calls an internal `assert_no_modal` check first. If any modal state
is pending, the tool short-circuits and returns `modal_state_blocked` instead
of running — `browser_snapshot` never gets far enough to capture a snapshot,
so there is no "modal type" field to read out of one.

To unblock:

- JS dialog: call `browser_handle_dialog`, which pops the oldest pending
  `dialog` entry, calls `.accept()` or `.dismiss()` on it, and consumes it
  from the pending list.
- File chooser: call `browser_file_upload`, which pops the oldest pending
  `filechooser` entry and sets the requested file paths on it.

Each resolution call consumes exactly one modal state entry of the matching
kind; if none is pending, both tools return `modal_state_blocked` themselves.

## Recovering from unexpected modals

If a tool call fails with a modal-related `error_type`, dismiss the modal
first (via the appropriate interaction tool) and retry. Swallowing the error
and retrying blindly will often hang.

## Gotcha: a dialog-triggering click can hold the lock for ~30s

Every tool operation on an instance serializes on that instance's per-instance
lock (`InstanceManager.lock_for`). If `browser_click` targets an element whose
`onclick` handler opens a native JS dialog (e.g. `alert(...)`), Playwright's
`locator.click()` call does not return until the click action resolves — and
with no dialog handler pre-registered, the browser-side dialog blocks that
resolution until it is dismissed. `browser_click` is still holding the
instance lock while it waits, up to Playwright's default 30-second action
timeout. Meanwhile `browser_handle_dialog` needs that same lock to consume
the pending dialog and can't acquire it until the click's call returns (by
resolving or by timing out). In practice this means a click that pops a
dialog can appear to hang for up to ~30 seconds before either the click times
out or you have a window to call `browser_handle_dialog` — this is a known
interaction gotcha, not a bug to work around by retrying.
