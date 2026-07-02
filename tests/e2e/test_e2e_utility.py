"""End-to-end tests for the utility tools.

Covers browser_resize, browser_tabs (list/new/select/close),
browser_generate_locator, and browser_pdf_save against the local e2e test site.
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


async def test_resize_applies_viewport(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "u1"})
    await call(e2e_client, "browser_navigate", {"instance": "u1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_resize", {"instance": "u1", "width": 800, "height": 600})
    assert r["status"] == "success"
    assert r["data"] == {"width": 800, "height": 600}

    # The new viewport is observable in the dimensions of a fresh screenshot.
    shot = await call(e2e_client, "browser_screenshot", {"instance": "u1"})
    assert shot["status"] == "success"
    assert shot["data"]["width"] == 800
    assert shot["data"]["height"] == 600


async def test_tabs_lifecycle(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "u2"})
    await call(e2e_client, "browser_navigate", {"instance": "u2", "url": f"{test_site}/index.html"})

    listed = await call(e2e_client, "browser_tabs", {"instance": "u2", "action": "list"})
    assert listed["status"] == "success"
    assert len(listed["data"]["tabs"]) == 1

    opened = await call(
        e2e_client,
        "browser_tabs",
        {"instance": "u2", "action": "new", "url": f"{test_site}/second.html"},
    )
    assert opened["status"] == "success"
    assert opened["data"]["index"] == 1

    listed2 = await call(e2e_client, "browser_tabs", {"instance": "u2", "action": "list"})
    assert len(listed2["data"]["tabs"]) == 2

    selected = await call(e2e_client, "browser_tabs", {"instance": "u2", "action": "select", "index": 0})
    assert selected["status"] == "success"
    assert selected["data"]["selected_index"] == 0

    closed = await call(e2e_client, "browser_tabs", {"instance": "u2", "action": "close", "index": 1})
    assert closed["status"] == "success"
    assert closed["data"]["closed_index"] == 1

    listed3 = await call(e2e_client, "browser_tabs", {"instance": "u2", "action": "list"})
    assert len(listed3["data"]["tabs"]) == 1


async def test_tabs_invalid_action(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "u3"})
    await call(e2e_client, "browser_navigate", {"instance": "u3", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_tabs", {"instance": "u3", "action": "teleport"})
    assert r["status"] == "error"
    assert r["error_type"] == "invalid_params"


async def test_generate_locator_from_ref(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "u4"})
    await call(e2e_client, "browser_navigate", {"instance": "u4", "url": f"{test_site}/index.html"})

    snap = await call(e2e_client, "browser_snapshot", {"instance": "u4"})
    ref = _ref_for(snap["data"]["snapshot"], 'link "Form"')

    r = await call(e2e_client, "browser_generate_locator", {"instance": "u4", "ref": ref})
    assert r["status"] == "success"
    assert r["data"]["ref"] == ref
    assert r["data"]["internal_selector"]
    # The "Form" link resolves to an ARIA role+name locator.
    assert 'get_by_role("link"' in r["data"]["python_syntax"]
    assert "Form" in r["data"]["python_syntax"]


async def test_pdf_save_unsupported_on_firefox(e2e_client, test_site, tmp_path):
    await call(e2e_client, "browser_create_instance", {"name": "u5"})
    await call(e2e_client, "browser_navigate", {"instance": "u5", "url": f"{test_site}/index.html"})

    out = str(tmp_path / "out.pdf")
    r = await call(e2e_client, "browser_pdf_save", {"instance": "u5", "file_path": out})
    # page.pdf() is a Chromium-only Playwright API; Camoufox runs Firefox, so
    # the tool surfaces the failure as an internal_error rather than a file.
    assert r["status"] == "error"
    assert r["error_type"] == "internal_error"
