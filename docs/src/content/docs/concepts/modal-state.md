---
title: Modal state
description: Detecting and handling modal dialogs across tools.
---

Pending JS dialogs (`alert`, `confirm`, `prompt`) and native file-choosers are captured by event listeners on the context and tracked as "modal state". Most tools check for pending modal state before running and return `modal_state_blocked` if one is present.

To unblock:

- JS dialog: call `browser_handle_dialog`.
- File chooser: call `browser_file_upload`.

## Detecting modal state

Inspection tools surface modal state as part of their snapshot output. A page
in modal state reports which modal type is active (dialog, alert, file picker,
etc.) so the caller knows which tools are safe to invoke.

## Recovering from unexpected modals

If a tool call fails with a modal-related `error_type`, dismiss the modal
first (via the appropriate interaction tool) and retry. Swallowing the error
and retrying blindly will often hang.
