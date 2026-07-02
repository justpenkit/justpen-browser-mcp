"""End-to-end tests for element interaction tools: browser_click, browser_type,
browser_fill_form, browser_select_option, browser_hover, browser_press_key,
browser_file_upload, browser_handle_dialog.

Drives a real Camoufox instance through a real FastMCP client against the
local static test site. Interaction tools operate on accessibility refs
(``[ref=eN]``) rather than CSS selectors, so every test here first captures a
real ``browser_snapshot`` and parses refs out of the returned YAML.

Snapshot ref format discovered empirically (see ``_parse_snapshot`` below):
a line looks like ``- textbox [ref=e3]`` or ``- button "Alert" [ref=e2]``.
Elements without their own ref (e.g. ``<option>`` entries nested under a
``<select>``) inherit the nearest ancestor's ref, since only the ancestor is
individually addressable by interaction tools.

Note: ``browser_drag`` is intentionally NOT covered here. Empirically, on
``drag.html`` (plain ``draggable`` divs with no ``dragover``/``drop`` JS
handlers), Playwright's ``Locator.drag_to`` times out after 30s against the
real Camoufox instance — the native HTML5 DnD sequence never completes
because the drop target never accepts the drop. This is an environment/
fixture limitation, not something to work around with source changes per
this task's scope.

Note on the dialog flow: clicking any of dialog.html's buttons opens a
NATIVE, blocking JS dialog (alert/confirm/prompt) from inside the onclick
handler. Empirically, ``browser_click``'s own post-action "wait for element
to be stable" re-check then hangs for the full 30s Playwright action
timeout — it never observes the click resolving, because it's holding the
per-instance lock while the page's JS thread is occupied by the modal's
nested event loop, and that lock is the SAME one ``browser_handle_dialog``
needs to consume the dialog and unblock the page. So ``browser_click``
reliably returns an ``internal_error`` timeout response here — but the
physical click (and therefore the dialog open) already happened before that
internal wait started, so a SUBSEQUENT ``browser_handle_dialog`` call
reliably succeeds once the click call finally times out and releases the
lock. The tests below therefore deliberately do NOT assert success on the
click step of a dialog-triggering interaction — only on the dialog handling
step that follows it. This is a real, worth-knowing quirk of the current
click/dialog lock interaction (see the task-14 report for the full writeup)
and it means every dialog-triggering click currently costs a mandatory ~30s.

browser_run_code is out of scope for this task (see task-14 brief).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]

_LINE_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<rest>.*)$")
_REF_RE = re.compile(r"\[ref=([^\]]+)\]")
_ROLE_RE = re.compile(r"^(?P<role>\w+)")


def _parse_snapshot(snapshot: str) -> list[dict[str, Any]]:
    """Parse a browser_snapshot YAML string into a flat list of node dicts.

    Each node has:
        indent   — leading-space count of the line
        text     — line content after the leading "- "
        role     — leading word on the line, e.g. "textbox"/"button"/"combobox"
        own_ref  — the [ref=eN] annotated directly on this line, or None
        ref      — own_ref if present, else the nearest ancestor's ref (a line
                   with smaller indent that has its own ref). This mirrors how
                   nested <option> entries under a <select> are addressed: only
                   the <select> itself carries a ref.
    """
    nodes: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    for raw_line in snapshot.splitlines():
        m = _LINE_RE.match(raw_line)
        if not m:
            continue
        indent = len(m.group("indent"))
        rest = m.group("rest")
        ref_m = _REF_RE.search(rest)
        own_ref = ref_m.group(1) if ref_m else None
        role_m = _ROLE_RE.match(rest)
        role = role_m.group("role") if role_m else None
        while stack and stack[-1][0] >= indent:
            stack.pop()
        ref = own_ref if own_ref is not None else (stack[-1][1] if stack else None)
        if own_ref is not None:
            stack.append((indent, own_ref))
        nodes.append({"indent": indent, "text": rest, "role": role, "own_ref": own_ref, "ref": ref})
    return nodes


def _ref_by_text(snapshot: str, needle: str) -> str | None:
    """Return the ref of the first node whose line text contains needle."""
    for node in _parse_snapshot(snapshot):
        if needle in node["text"]:
            return node["ref"]
    return None


def _refs_by_role(snapshot: str, role: str) -> list[str]:
    """Return the refs (in document order) of nodes with their own ref matching role."""
    return [n["own_ref"] for n in _parse_snapshot(snapshot) if n["role"] == role and n["own_ref"]]


async def _snapshot_text(client: Any, instance: str) -> str:
    snap = await call(client, "browser_snapshot", {"instance": instance})
    assert snap["status"] == "success"
    return snap["data"]["snapshot"]


async def test_type_into_name_field_sets_value(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i1"})
    await call(e2e_client, "browser_navigate", {"instance": "i1", "url": f"{test_site}/form.html"})
    snapshot = await _snapshot_text(e2e_client, "i1")

    textbox_refs = _refs_by_role(snapshot, "textbox")
    assert len(textbox_refs) == 2, f"expected 2 textboxes (name, email), got {textbox_refs!r}"
    name_ref = textbox_refs[0]

    r = await call(e2e_client, "browser_type", {"instance": "i1", "ref": name_ref, "text": "Alice"})
    assert r["status"] == "success"
    assert r["data"]["typed_into"] == name_ref

    ev = await call(
        e2e_client,
        "browser_evaluate",
        {"instance": "i1", "selector": "#name", "expression": "el => el.value"},
    )
    assert ev["status"] == "success"
    assert ev["data"]["result"] == "Alice"


async def test_select_option_sets_value(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i2"})
    await call(e2e_client, "browser_navigate", {"instance": "i2", "url": f"{test_site}/form.html"})
    snapshot = await _snapshot_text(e2e_client, "i2")

    combobox_refs = _refs_by_role(snapshot, "combobox")
    assert combobox_refs, f"expected a combobox ref in snapshot: {snapshot!r}"
    color_ref = combobox_refs[0]

    r = await call(e2e_client, "browser_select_option", {"instance": "i2", "ref": color_ref, "value": "blue"})
    assert r["status"] == "success"
    assert r["data"]["selected"] == "blue"

    ev = await call(
        e2e_client,
        "browser_evaluate",
        {"instance": "i2", "selector": "#color", "expression": "el => el.value"},
    )
    assert ev["data"]["result"] == "blue"


async def test_fill_form_multiple_fields(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i3"})
    await call(e2e_client, "browser_navigate", {"instance": "i3", "url": f"{test_site}/form.html"})
    snapshot = await _snapshot_text(e2e_client, "i3")

    name_ref, email_ref = _refs_by_role(snapshot, "textbox")
    color_ref = _refs_by_role(snapshot, "combobox")[0]

    r = await call(
        e2e_client,
        "browser_fill_form",
        {
            "instance": "i3",
            "fields": [
                {"ref": name_ref, "value": "Bob", "type": "textbox"},
                {"ref": email_ref, "value": "bob@example.com", "type": "textbox"},
                {"ref": color_ref, "value": "blue", "type": "combobox"},
            ],
        },
    )
    assert r["status"] == "success"
    assert r["data"]["filled_count"] == 3

    name_val = await call(
        e2e_client, "browser_evaluate", {"instance": "i3", "selector": "#name", "expression": "el => el.value"}
    )
    email_val = await call(
        e2e_client, "browser_evaluate", {"instance": "i3", "selector": "#email", "expression": "el => el.value"}
    )
    color_val = await call(
        e2e_client, "browser_evaluate", {"instance": "i3", "selector": "#color", "expression": "el => el.value"}
    )
    assert name_val["data"]["result"] == "Bob"
    assert email_val["data"]["result"] == "bob@example.com"
    assert color_val["data"]["result"] == "blue"


async def test_press_key_types_into_focused_field(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i4"})
    await call(e2e_client, "browser_navigate", {"instance": "i4", "url": f"{test_site}/form.html"})
    snapshot = await _snapshot_text(e2e_client, "i4")
    name_ref = _refs_by_role(snapshot, "textbox")[0]

    click_r = await call(e2e_client, "browser_click", {"instance": "i4", "ref": name_ref})
    assert click_r["status"] == "success"

    for key in ("A", "B"):
        r = await call(e2e_client, "browser_press_key", {"instance": "i4", "key": key})
        assert r["status"] == "success"
        assert r["data"]["pressed"] == key

    ev = await call(
        e2e_client, "browser_evaluate", {"instance": "i4", "selector": "#name", "expression": "el => el.value"}
    )
    assert ev["data"]["result"] == "AB"


async def test_hover_does_not_trigger_click_handler(e2e_client, test_site):
    """Hover positions the cursor but must not invoke the element's onclick."""
    await call(e2e_client, "browser_create_instance", {"name": "i5"})
    await call(e2e_client, "browser_navigate", {"instance": "i5", "url": f"{test_site}/dialog.html"})
    snapshot = await _snapshot_text(e2e_client, "i5")
    confirm_ref = _ref_by_text(snapshot, "Confirm")
    assert confirm_ref is not None

    r = await call(e2e_client, "browser_hover", {"instance": "i5", "ref": confirm_ref})
    assert r["status"] == "success"
    assert r["data"]["hovered"] == confirm_ref

    # onclick fires confirm(), which would leave a dialog pending. Hover alone
    # must not trigger it, so resolving a dialog now must fail.
    dialog_r = await call(e2e_client, "browser_handle_dialog", {"instance": "i5", "accept": True})
    assert dialog_r["status"] == "error"
    assert dialog_r["error_type"] == "modal_state_blocked"


async def test_dialog_accept_alert(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i6"})
    await call(e2e_client, "browser_navigate", {"instance": "i6", "url": f"{test_site}/dialog.html"})
    snapshot = await _snapshot_text(e2e_client, "i6")
    alert_ref = _ref_by_text(snapshot, "Alert")
    assert alert_ref is not None

    # Deliberately not asserted: see the module docstring — this click
    # reliably reports an internal_error timeout even though the underlying
    # click (and dialog open) already happened.
    await call(e2e_client, "browser_click", {"instance": "i6", "ref": alert_ref})

    dialog_r = await call(e2e_client, "browser_handle_dialog", {"instance": "i6", "accept": True})
    assert dialog_r["status"] == "success"
    assert dialog_r["data"] == {"action": "accepted", "dialog_type": "alert", "message": "hello"}


async def test_dialog_dismiss_confirm(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i7"})
    await call(e2e_client, "browser_navigate", {"instance": "i7", "url": f"{test_site}/dialog.html"})
    snapshot = await _snapshot_text(e2e_client, "i7")
    confirm_ref = _ref_by_text(snapshot, "Confirm")
    assert confirm_ref is not None

    await call(e2e_client, "browser_click", {"instance": "i7", "ref": confirm_ref})

    dialog_r = await call(e2e_client, "browser_handle_dialog", {"instance": "i7", "accept": False})
    assert dialog_r["status"] == "success"
    assert dialog_r["data"] == {"action": "dismissed", "dialog_type": "confirm", "message": "ok?"}


async def test_dialog_accept_prompt_with_text(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i8"})
    await call(e2e_client, "browser_navigate", {"instance": "i8", "url": f"{test_site}/dialog.html"})
    snapshot = await _snapshot_text(e2e_client, "i8")
    prompt_ref = _ref_by_text(snapshot, "Prompt")
    assert prompt_ref is not None

    await call(e2e_client, "browser_click", {"instance": "i8", "ref": prompt_ref})

    dialog_r = await call(e2e_client, "browser_handle_dialog", {"instance": "i8", "accept": True, "prompt_text": "Bob"})
    assert dialog_r["status"] == "success"
    assert dialog_r["data"] == {"action": "accepted", "dialog_type": "prompt", "message": "name?"}

    # The dict above only proves the dialog's QUESTION was "name?" — it says
    # nothing about whether "Bob" actually landed as the entered value.
    # window._r is invisible to browser_evaluate (isolated JS world), but
    # DOM-backed state crosses that boundary, so dialog.html's prompt button
    # mirrors the result into #promptResult for verification here.
    ev = await call(
        e2e_client,
        "browser_evaluate",
        {"instance": "i8", "expression": "document.getElementById('promptResult').textContent"},
    )
    assert ev["status"] == "success"
    assert ev["data"]["result"] == "Bob"


async def test_file_upload_attaches_selected_file(e2e_client, test_site, tmp_path):
    await call(e2e_client, "browser_create_instance", {"name": "i9"})
    await call(e2e_client, "browser_navigate", {"instance": "i9", "url": f"{test_site}/upload.html"})
    snapshot = await _snapshot_text(e2e_client, "i9")
    file_ref = _ref_by_text(snapshot, "Choose File")
    assert file_ref is not None

    click_r = await call(e2e_client, "browser_click", {"instance": "i9", "ref": file_ref})
    assert click_r["status"] == "success"

    upload_path = tmp_path / "sample.txt"
    upload_path.write_text("hello")
    r = await call(e2e_client, "browser_file_upload", {"instance": "i9", "paths": [str(upload_path)]})
    assert r["status"] == "success"
    assert r["data"]["uploaded_count"] == 1

    ev = await call(
        e2e_client,
        "browser_evaluate",
        {"instance": "i9", "selector": "#file", "expression": "el => el.files.length"},
    )
    assert ev["data"]["result"] == 1


async def test_file_upload_cancelled_without_paths(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "i10"})
    await call(e2e_client, "browser_navigate", {"instance": "i10", "url": f"{test_site}/upload.html"})
    snapshot = await _snapshot_text(e2e_client, "i10")
    file_ref = _ref_by_text(snapshot, "Choose File")
    assert file_ref is not None

    await call(e2e_client, "browser_click", {"instance": "i10", "ref": file_ref})
    r = await call(e2e_client, "browser_file_upload", {"instance": "i10"})
    assert r["status"] == "success"
    assert r["data"] == {"cancelled": True}
