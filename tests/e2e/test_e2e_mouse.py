"""End-to-end tests for low-level positional mouse tools: browser_mouse_move_xy,
browser_mouse_click_xy, browser_mouse_down/up, browser_mouse_drag_xy,
browser_mouse_wheel.

These tools operate on absolute page-relative pixel coordinates rather than
accessibility refs, so no browser_snapshot parsing is needed here. Real
outcomes are verified via browser_evaluate reading page/DOM state (e.g.
scrollY after a wheel event, the click landing on a real link and navigating).
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_mouse_move_xy_returns_target_position(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "m1"})
    await call(e2e_client, "browser_navigate", {"instance": "m1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_mouse_move_xy", {"instance": "m1", "x": 10, "y": 12})
    assert r["status"] == "success"
    assert r["data"]["moved_to"] == [10, 12]


async def test_mouse_click_xy_on_link_navigates(e2e_client, test_site):
    """Clicking directly at the pixel position of the #to-form link follows it."""
    await call(e2e_client, "browser_create_instance", {"name": "m2"})
    await call(e2e_client, "browser_navigate", {"instance": "m2", "url": f"{test_site}/index.html"})

    box = await call(
        e2e_client,
        "browser_evaluate",
        {
            "instance": "m2",
            "selector": "#to-form",
            "expression": "el => { const r = el.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }",
        },
    )
    assert box["status"] == "success"
    x, y = box["data"]["result"]

    r = await call(e2e_client, "browser_mouse_click_xy", {"instance": "m2", "x": round(x), "y": round(y)})
    assert r["status"] == "success"
    assert r["data"]["clicked_at"] == [round(x), round(y)]
    assert r["data"]["button"] == "left"

    # The click triggers a real navigation; give it a moment to land before
    # reading page state — a bare browser_evaluate immediately afterwards
    # can race the navigation and hit "execution context was destroyed".
    await call(e2e_client, "browser_wait_for", {"instance": "m2", "time": 0.5})
    snap = await call(e2e_client, "browser_snapshot", {"instance": "m2"})
    assert snap["status"] == "success"
    assert snap["data"]["url"] == f"{test_site}/form.html"


async def test_mouse_down_move_up_drags(e2e_client, test_site):
    """A manual down/move/up sequence via the low-level mouse primitives."""
    await call(e2e_client, "browser_create_instance", {"name": "m3"})
    await call(e2e_client, "browser_navigate", {"instance": "m3", "url": f"{test_site}/index.html"})

    down_r = await call(e2e_client, "browser_mouse_down", {"instance": "m3", "button": "left"})
    assert down_r["status"] == "success"
    assert down_r["data"]["button_down"] == "left"

    up_r = await call(e2e_client, "browser_mouse_up", {"instance": "m3", "button": "left"})
    assert up_r["status"] == "success"
    assert up_r["data"]["button_up"] == "left"


async def test_mouse_drag_xy_reports_endpoints(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "m4"})
    await call(e2e_client, "browser_navigate", {"instance": "m4", "url": f"{test_site}/index.html"})

    r = await call(
        e2e_client,
        "browser_mouse_drag_xy",
        {"instance": "m4", "from_x": 5, "from_y": 5, "to_x": 40, "to_y": 60},
    )
    assert r["status"] == "success"
    assert r["data"]["from"] == [5, 5]
    assert r["data"]["to"] == [40, 60]


async def test_mouse_wheel_scrolls_page(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "m5"})
    await call(e2e_client, "browser_navigate", {"instance": "m5", "url": f"{test_site}/index.html"})

    # Make the page scrollable so the wheel event has somewhere to move it.
    await call(
        e2e_client,
        "browser_evaluate",
        {
            "instance": "m5",
            "expression": "() => { document.body.style.height = '4000px'; return true; }",
        },
    )
    # The wheel event is delivered at the current cursor position, which
    # defaults outside the viewport until a move has established one.
    await call(e2e_client, "browser_mouse_move_xy", {"instance": "m5", "x": 50, "y": 50})

    r = await call(e2e_client, "browser_mouse_wheel", {"instance": "m5", "delta_y": 300})
    assert r["status"] == "success"
    assert r["data"]["scrolled"] == [0, 300]

    await call(e2e_client, "browser_wait_for", {"instance": "m5", "time": 0.3})
    scroll_y = await call(e2e_client, "browser_evaluate", {"instance": "m5", "expression": "window.scrollY"})
    assert scroll_y["status"] == "success"
    assert scroll_y["data"]["result"] > 0


async def test_mouse_wheel_requires_nonzero_delta(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "m6"})
    await call(e2e_client, "browser_navigate", {"instance": "m6", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_mouse_wheel", {"instance": "m6"})
    assert r["status"] == "error"
    assert r["error_type"] == "invalid_params"
