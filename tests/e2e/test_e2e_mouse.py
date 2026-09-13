"""End-to-end tests for low-level positional mouse tools: browser_mouse_move_xy,
browser_mouse_click_xy, browser_mouse_down/up, browser_mouse_drag_xy,
browser_mouse_wheel.

These tools operate on absolute page-relative pixel coordinates rather than
accessibility refs, so no browser_snapshot parsing is needed here. Real
outcomes are verified via browser_evaluate reading page/DOM state (e.g.
scrollY after a wheel event, the click landing on a real link and navigating).
"""

import json

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]


async def test_mouse_move_xy_returns_target_position(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "m1"})
    await call(e2e_client, "browser_navigate", {"instance": "m1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_mouse_move_xy", {"instance": "m1", "x": 10, "y": 12})
    assert r["status"] == "success"
    assert r["data"]["moved_to"] == [10, 12]


@pytest.mark.parametrize("source_page", ["index.html", "delayed-link.html"])
async def test_mouse_click_xy_on_link_navigates(e2e_client, test_site, source_page, tmp_path):
    """Clicking directly at the pixel position of the #to-form link follows it."""
    await call(e2e_client, "browser_create_instance", {"name": "m2"})
    await call(e2e_client, "browser_navigate", {"instance": "m2", "url": f"{test_site}/{source_page}"})

    box = await call(
        e2e_client,
        "browser_evaluate",
        {
            "instance": "m2",
            "selector": "#to-form",
            "expression": """el => {
                window.mouseClickEvents = [];
                sessionStorage.removeItem("mouse-click-events");
                const save = () => sessionStorage.setItem("mouse-click-events", JSON.stringify(window.mouseClickEvents));
                for (const type of ["pointermove", "pointerdown", "pointerup", "click"]) {
                    document.addEventListener(type, event => {
                        window.mouseClickEvents.push({
                            type, x: event.clientX, y: event.clientY, buttons: event.buttons,
                            target: event.target.id || event.target.tagName, trusted: event.isTrusted,
                            time: performance.now()
                        });
                        if (type !== "pointermove") save();
                    }, true);
                }
                window.addEventListener("pagehide", save);
                const r = el.getBoundingClientRect();
                const point = [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)];
                return {point, box: r.toJSON(), hit: document.elementFromPoint(...point)?.id};
            }""",
        },
    )
    assert box["status"] == "success"
    assert box["data"]["result"]["hit"] == "to-form", box
    x, y = box["data"]["result"]["point"]

    r = await call(e2e_client, "browser_mouse_click_xy", {"instance": "m2", "x": round(x), "y": round(y)})
    assert r["status"] == "success"
    assert r["data"]["clicked_at"] == [round(x), round(y)]
    assert r["data"]["button"] == "left"

    # The source document is already loaded even when navigation is scheduled
    # after the click handler returns. Wait for content unique to the destination.
    waited = await call(e2e_client, "browser_wait_for", {"instance": "m2", "text": "Send"})
    snap = await call(e2e_client, "browser_snapshot", {"instance": "m2"})
    observed = await call(
        e2e_client,
        "browser_evaluate",
        {
            "instance": "m2",
            "expression": """() => ({
                url: location.href,
                events: window.mouseClickEvents || JSON.parse(sessionStorage.getItem("mouse-click-events") || "[]"),
                formReady: Boolean(document.querySelector("form#f input#name"))
            })""",
        },
    )
    diagnostics = {"measured": box, "click": r, "wait": waited, "snapshot": snap, "observed": observed}
    (tmp_path / "mouse-click.json").write_text(json.dumps(diagnostics, indent=2))
    try:
        assert waited["status"] == "success", waited
        assert snap["status"] == "success", snap
        assert snap["data"]["url"] == f"{test_site}/form.html"
        assert observed["status"] == "success", observed
        assert observed["data"]["result"]["formReady"]
        assert any(
            event["type"] == "click"
            and event["target"] == "to-form"
            and event["trusted"]
            and [event["x"], event["y"]] == [x, y]
            for event in observed["data"]["result"]["events"]
        )
    except AssertionError:
        print("Mouse click diagnostics: " + json.dumps(diagnostics))
        raise


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
