"""End-to-end hardening tests: crash eviction, idle reaper, config passthrough.

Unlike the ``e2e_client`` fixture tests, these build their own
``InstanceManager`` directly so they can set ``idle_ttl_seconds``, kill the
browser process, and inspect manager internals (crashed records, reaper
eviction). ``test_site`` from ``conftest`` supplies a URL to navigate to.

Requires a real Camoufox binary.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import InstanceCrashedError, InstanceNotFoundError
from justpen_browser_mcp.instance_manager import InstanceManager

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_crash_marks_and_evicts(test_site: str) -> None:
    """A disconnected browser is marked crashed, then evicted on first get().

    Forcibly closing the ephemeral Browser handle (or persistent context) fires
    the wired "disconnected"/"close" callback, which flips state.status to
    "crashed". The first get() sees the crash, evicts the record, and raises
    InstanceCrashedError; the second get() finds nothing and raises
    InstanceNotFoundError.
    """
    mgr = InstanceManager(BrowserServerConfig(max_instances=3))
    try:
        rec = await mgr.create("k1")
        page = await mgr.active_page("k1")
        await page.goto(f"{test_site}/index.html")

        # Kill the browser: closing the browser/context triggers the crash handler.
        if rec.browser is not None:
            await rec.browser.close()
        else:
            await rec.context.close()

        # Allow the event loop to deliver the disconnect callback.
        await asyncio.sleep(0.5)

        raw = mgr._get_raw("k1")
        assert raw is not None
        assert raw.state.status == "crashed"

        with pytest.raises(InstanceCrashedError):
            mgr.get("k1")
        # Now evicted: a second lookup finds nothing.
        with pytest.raises(InstanceNotFoundError):
            mgr.get("k1")
    finally:
        await mgr.shutdown_all()


async def test_reap_once_evicts_idle(test_site: str) -> None:
    """reap_once evicts an instance idle past idle_ttl_seconds (clock injected).

    Deterministic variant: back-date last_used_at, then drive reap_once with an
    explicit ``now`` rather than waiting on the background loop's wall clock. The
    reaped name is returned and the record is gone from the registry.
    """
    mgr = InstanceManager(BrowserServerConfig(max_instances=3, idle_ttl_seconds=1, reaper_interval_seconds=1))
    try:
        await mgr.create("r1")
        rec = mgr._get_raw("r1")
        assert rec is not None
        rec.state.last_used_at = datetime.now(tz=UTC) - timedelta(seconds=10)

        evicted = await mgr.reap_once(datetime.now(tz=UTC))
        assert evicted == ["r1"]
        assert mgr._get_raw("r1") is None
    finally:
        await mgr.shutdown_all()


async def test_reaper_evicts_idle(test_site: str) -> None:
    """The background reaper task evicts an idle instance on its own timer.

    Wall-clock variant proving start_reaper actually schedules the loop: create
    an instance, back-date it well past the 1s TTL, start the reaper, and wait
    long enough for one interval to fire and evict it.
    """
    mgr = InstanceManager(BrowserServerConfig(max_instances=3, idle_ttl_seconds=1, reaper_interval_seconds=1))
    try:
        await mgr.create("r2")
        rec = mgr._get_raw("r2")
        assert rec is not None
        rec.state.last_used_at = datetime.now(tz=UTC) - timedelta(seconds=10)

        mgr.start_reaper()
        await asyncio.sleep(2.5)
        assert mgr._get_raw("r2") is None
    finally:
        await mgr.stop_reaper()
        await mgr.shutdown_all()


async def test_server_locale_default_applied(test_site: str) -> None:
    """A server-level ``locale`` default is applied to a new instance's fingerprint.

    The instance is created WITHOUT a per-call locale override, so it inherits
    the manager's ``locale="fr-FR"`` default. Observable surface: navigator's
    reported language. Empirically verified in this Camoufox build that
    ``page.evaluate("navigator.language")`` DOES reflect the configured locale
    (Camoufox patches the fingerprint at the browser level, so the value is
    visible even from page.evaluate's isolated JS world) rather than the host's
    system locale.
    """
    mgr = InstanceManager(BrowserServerConfig(max_instances=2, locale="fr-FR"))
    try:
        await mgr.create("cfg1")
        page = await mgr.active_page("cfg1")
        await page.goto(f"{test_site}/index.html")

        lang = await page.evaluate("navigator.language")
        assert isinstance(lang, str)
        assert lang.lower().startswith("fr")

        languages = await page.evaluate("navigator.languages")
        assert isinstance(languages, list)
        assert any(isinstance(item, str) and item.lower().startswith("fr") for item in languages)
    finally:
        await mgr.shutdown_all()
