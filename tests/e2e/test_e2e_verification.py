"""End-to-end tests for the DOM verification tools.

Covers browser_verify_text_visible, browser_verify_element_visible,
browser_verify_list_visible, and browser_verify_value against index.html and
form.html served by the local e2e test site.
"""

import re

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


def _ref_for(snapshot: str, needle: str) -> str:
    """Return the [ref=eN] token of the first snapshot line containing needle."""
    for line in snapshot.splitlines():
        if needle in line:
            m = re.search(r"\[ref=(e\d+)\]", line)
            if m:
                return m.group(1)
    raise AssertionError(f"no ref for {needle!r} in snapshot:\n{snapshot}")


async def test_verify_text_visible_and_failure(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "v1"})
    await call(e2e_client, "browser_navigate", {"instance": "v1", "url": f"{test_site}/index.html"})

    ok = await call(e2e_client, "browser_verify_text_visible", {"instance": "v1", "text": "Home"})
    assert ok["status"] == "success"
    assert ok["data"] == {"text": "Home", "visible": True}

    bad = await call(e2e_client, "browser_verify_text_visible", {"instance": "v1", "text": "Nonexistent Zzz"})
    assert bad["status"] == "error"
    assert bad["error_type"] == "verification_failed"


async def test_verify_element_visible_by_ref(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "v2"})
    await call(e2e_client, "browser_navigate", {"instance": "v2", "url": f"{test_site}/index.html"})

    snap = await call(e2e_client, "browser_snapshot", {"instance": "v2"})
    ref = _ref_for(snap["data"]["snapshot"], 'link "Form"')

    r = await call(e2e_client, "browser_verify_element_visible", {"instance": "v2", "ref": ref})
    assert r["status"] == "success"
    assert r["data"] == {"visible": True, "ref": ref}


async def test_verify_element_visible_stale_ref(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "v3"})
    await call(e2e_client, "browser_navigate", {"instance": "v3", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_verify_element_visible", {"instance": "v3", "ref": "e999"})
    assert r["status"] == "error"
    assert r["error_type"] == "stale_ref"


async def test_verify_list_visible_refs_mode(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "v4"})
    await call(e2e_client, "browser_navigate", {"instance": "v4", "url": f"{test_site}/index.html"})

    snap = await call(e2e_client, "browser_snapshot", {"instance": "v4"})
    snapshot = snap["data"]["snapshot"]
    ref_form = _ref_for(snapshot, 'link "Form"')
    ref_tab = _ref_for(snapshot, 'link "New Tab"')

    r = await call(e2e_client, "browser_verify_list_visible", {"instance": "v4", "refs": [ref_form, ref_tab]})
    assert r["status"] == "success"
    assert r["data"]["visible_refs"] == [ref_form, ref_tab]


async def test_verify_value_reads_select_default(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "v5"})
    await call(e2e_client, "browser_navigate", {"instance": "v5", "url": f"{test_site}/form.html"})

    snap = await call(e2e_client, "browser_snapshot", {"instance": "v5"})
    ref = _ref_for(snap["data"]["snapshot"], "combobox")

    # The <select id="color"> defaults to its first <option value="red">.
    ok = await call(
        e2e_client,
        "browser_verify_value",
        {"instance": "v5", "ref": ref, "expected_value": "red"},
    )
    assert ok["status"] == "success"
    assert ok["data"] == {"ref": ref, "value": "red", "element_type": "text"}

    bad = await call(
        e2e_client,
        "browser_verify_value",
        {"instance": "v5", "ref": ref, "expected_value": "green"},
    )
    assert bad["status"] == "error"
    assert bad["error_type"] == "verification_failed"
