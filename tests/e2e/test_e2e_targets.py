"""Real cross-origin frame references and selection-independent page actions."""

import re

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]


async def test_explicit_pages_and_cross_origin_frames(e2e_client, test_site):
    client = e2e_client
    await call(client, "browser_create_instance", {"name": "target", "humanize": False})
    common = {"instance": "target"}
    first = await call(client, "browser_tabs", {**common, "action": "new", "url": f"{test_site}/frames.html"})
    aid = first["data"]["page_id"]
    second = await call(client, "browser_tabs", {**common, "action": "new", "url": f"{test_site}/frames.html"})
    bid = second["data"]["page_id"]
    await call(client, "browser_tabs", {**common, "action": "select", "page_id": aid})
    await call(
        client,
        "browser_run_code",
        {
            **common,
            "page_id": bid,
            "code": "await page.wait_for_function(\"document.querySelectorAll('iframe').length === 2\")\nawait page.frame(name='cross').wait_for_selector('iframe')",
        },
    )
    result = await call(client, "browser_frames", {**common, "page_id": bid})
    frames = result["data"]["frames"]
    assert len(frames) == 4
    child = next(f for f in frames if f["name"] == "cross")
    fid = child["frame_id"]
    scope = {**common, "page_id": bid, "frame_id": fid}
    snap = await call(client, "browser_snapshot", scope)
    assert snap["status"] == "success", snap
    assert snap["data"]["frame_id"] == fid
    email = re.search(r'textbox "Email" \[ref=(\w+)\]', snap["data"]["snapshot"])
    choice = re.search(r'combobox "Choice" \[ref=(\w+)\]', snap["data"]["snapshot"])
    submit = re.search(r'button "Submit" \[ref=(\w+)\]', snap["data"]["snapshot"])
    assert email is not None
    assert choice is not None
    assert submit is not None
    for tool, args in [
        ("browser_type", {"ref": email[1], "text": "explicit"}),
        ("browser_select_option", {"ref": choice[1], "value": "two"}),
        ("browser_verify_value", {"ref": email[1], "expected_value": "explicit"}),
        ("browser_click", {"ref": submit[1]}),
        ("browser_verify_text_visible", {"text": "Submitted"}),
        ("browser_generate_locator", {"ref": email[1]}),
    ]:
        response = await call(client, tool, {**scope, **args})
        assert response["status"] == "success", response
        assert response["operation"]["page_id"] == bid
        assert response["operation"]["frame_id"] == fid
    selected = await call(client, "browser_evaluate", {**common, "expression": "document.querySelector('input').value"})
    assert selected["operation"]["page_id"] == aid
    assert selected["data"]["result"] == "main"
    other = next(f for f in frames if f["name"] == "same")
    untouched = await call(
        client,
        "browser_evaluate",
        {**scope, "frame_id": other["frame_id"], "expression": "document.querySelector('input').value"},
    )
    assert untouched["data"]["result"] == ""
    wrong = await call(client, "browser_evaluate", {**scope, "page_id": aid, "expression": "1"})
    assert wrong["error_type"] == "frame_not_found"
    # Navigation retains the live Frame identity, while a detach invalidates it.
    await call(
        client,
        "browser_run_code",
        {
            **common,
            "page_id": bid,
            "code": "await page.frame(name='cross').goto(page.frame(name='cross').url + '?again')",
        },
    )
    refreshed = await call(client, "browser_snapshot", scope)
    assert refreshed["data"]["frame_id"] == fid
    await call(
        client,
        "browser_evaluate",
        {**common, "page_id": bid, "expression": "document.querySelector('iframe[name=cross]').remove()"},
    )
    detached = await call(client, "browser_snapshot", scope)
    assert detached["error_type"] == "frame_not_found"
    insertion = await call(
        client,
        "browser_run_code",
        {
            **common,
            "page_id": bid,
            "code": """
await page.evaluate("() => { const f=document.createElement('iframe'); f.name='replacement'; f.src='frame-form.html?nested'; document.body.append(f); }")
await page.frame_locator('iframe[name=replacement]').locator('input').wait_for()
""",
        },
    )
    assert insertion["status"] == "success", insertion
    replaced = await call(client, "browser_frames", {**common, "page_id": bid})
    replacement = next(f for f in replaced["data"]["frames"] if f["name"] == "replacement")
    assert replacement["frame_id"] != fid
    await call(client, "browser_create_instance", {"name": "foreign", "humanize": False})
    foreign = await call(client, "browser_snapshot", {"instance": "foreign", "page_id": bid})
    assert foreign["error_type"] == "page_not_found"
    await call(client, "browser_close", {**common, "page_id": bid})
    closed = await call(client, "browser_snapshot", {**common, "page_id": bid})
    assert closed["error_type"] == "page_not_found"
    missing = await call(client, "browser_snapshot", {**common, "page_id": "missing"})
    assert missing["error_type"] == "page_not_found"
    selected = await call(client, "browser_evaluate", {**common, "expression": "1"})
    assert selected["operation"]["page_id"] == aid
