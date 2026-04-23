"""InstanceRecord, InstanceState, and launch_instance helper.

An InstanceRecord is a single isolated Camoufox process owned by the
server's InstanceManager. Each record carries an AsyncExitStack that
holds the underlying AsyncCamoufox context manager; closing the stack
tears the instance down cleanly.

launch_instance() normalizes Camoufox's two return shapes (Browser for
ephemeral, BrowserContext for persistent) into a single BrowserContext
so downstream code never branches on instance mode.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from camoufox.async_api import AsyncCamoufox

if TYPE_CHECKING:
    import asyncio
    from datetime import datetime

    from playwright.async_api import Browser, BrowserContext


@dataclass
class InstanceState:
    """Per-instance bookkeeping (console, network, modal state, active tab index)."""

    console_messages: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    network_requests: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    network_request_index: dict[int, dict[str, Any]] = field(default_factory=dict[int, dict[str, Any]])
    active_page_index: int = 0
    modal_states: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


@dataclass
class InstanceRecord:
    """Single live Camoufox instance owned by InstanceManager."""

    name: str
    stack: AsyncExitStack
    context: BrowserContext
    lock: asyncio.Lock
    state: InstanceState
    profile_dir: str | None
    created_at: datetime


async def launch_instance(
    *,
    profile_dir: str | None,
    headless: bool | Literal["virtual"],
    proxy: dict[str, str] | None,
    humanize: bool | float,
    window: tuple[int, int] | None,
) -> tuple[AsyncExitStack, BrowserContext]:
    """Launch a Camoufox instance and return its exit stack + normalized BrowserContext.

    The caller owns the returned stack and is responsible for calling aclose()
    when the instance is no longer needed. On exception during launch, the stack
    is closed internally before re-raising so no resources leak.
    """
    kwargs: dict[str, Any] = {
        "headless": headless,
        "humanize": humanize,
        "block_webrtc": True,
        "block_images": False,
        "disable_coop": True,
    }
    if proxy is not None:
        kwargs["proxy"] = proxy
        kwargs["geoip"] = True
    if window is not None:
        kwargs["window"] = window
    if profile_dir is not None:
        kwargs["persistent_context"] = True
        kwargs["user_data_dir"] = profile_dir

    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        obj = await stack.enter_async_context(AsyncCamoufox(**kwargs))
        if profile_dir is not None:
            ctx = cast("BrowserContext", obj)
        else:
            browser = cast("Browser", obj)
            ctx = await browser.new_context()
    except BaseException:
        await stack.aclose()
        raise
    return stack, ctx
