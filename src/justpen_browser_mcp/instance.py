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

import asyncio
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from camoufox import DefaultAddons
from camoufox.async_api import AsyncCamoufox

from .events import EventBuffer

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.async_api import Browser, BrowserContext, Page


def _utcnow() -> datetime:
    """Zero-arg factory for dataclass default_factory (datetime.now needs tz kwarg)."""
    return datetime.now(tz=UTC)


@dataclass
class InstanceState:
    """Per-instance bookkeeping (console, network, modal state, active tab index)."""

    console_messages: EventBuffer = field(default_factory=EventBuffer)
    network_requests: EventBuffer = field(default_factory=EventBuffer)
    network_request_index: dict[int, dict[str, Any]] = field(default_factory=dict[int, dict[str, Any]])
    active_page_index: int = 0
    active_page: Page | None = None
    page_ids: dict[Page, str] = field(default_factory=dict["Page", str])
    modal_states: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    status: Literal["live", "crashed", "closing", "close_failed"] = "live"
    last_used_at: datetime = field(default_factory=_utcnow)
    last_used_monotonic: float = field(default_factory=time.monotonic)


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
    browser: Browser | None
    instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    modal_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    operation_tasks: set[asyncio.Task[Any]] = field(default_factory=set[asyncio.Task[Any]])
    close_task: asyncio.Task[None] | None = None
    close_error: str | None = None


T = TypeVar("T")


def _set_optional(
    kwargs: dict[str, Any],
    key: str,
    value: T | None,
    *,
    transform: Callable[[T], object] | None = None,
    require_truthy: bool = False,
) -> None:
    """Set kwargs[key] = value (optionally transformed) when value is present.

    "Present" means non-None by default, or truthy when require_truthy is set
    (used for values, like empty dicts/tuples, whose falsy state should also
    be treated as "not overridden").
    """
    if value is None:
        return
    if require_truthy and not value:
        return
    kwargs[key] = transform(value) if transform is not None else value


async def launch_instance(
    *,
    stack: AsyncExitStack | None = None,
    profile_dir: str | None,
    headless: bool | Literal["virtual"],
    proxy: dict[str, str] | None,
    humanize: bool | float,
    window: tuple[int, int] | None,
    block_images: bool | None = None,
    block_webrtc: bool | None = None,
    block_webgl: bool | None = None,
    camoufox_os: tuple[str, ...] | None = None,
    locale: str | None = None,
    geoip: bool | None = None,
    firefox_user_prefs: dict[str, Any] | None = None,
    camoufox_args: tuple[str, ...] | None = None,
    enable_cache: bool | None = None,
    ff_version: int | None = None,
) -> tuple[AsyncExitStack, BrowserContext, Browser | None]:
    """Launch a Camoufox instance and return its exit stack + normalized BrowserContext.

    The caller owns the returned stack and is responsible for calling aclose()
    when the instance is no longer needed. A supplied stack remains caller-owned
    even when launch raises, allowing the manager to bound rollback and retain
    failed teardown reservations. Without a supplied stack, rollback is internal. The third
    element is the Browser handle for ephemeral mode (used to wire up
    "disconnected" crash detection) or None for persistent mode, where Camoufox
    hands back a BrowserContext directly with no separate Browser object.
    """
    kwargs: dict[str, Any] = {
        "headless": headless,
        # Camoufox treats bool as a numeric duration. Pass its native 1.5-second
        # default explicitly so True is not serialized into a double property.
        "humanize": 1.5 if humanize is True else humanize,
        "block_webrtc": True,
        "block_images": False,
        "disable_coop": True,
        # uBlock's startup request handler can leave navigations suspended.
        "exclude_addons": [DefaultAddons.UBO],
    }
    if proxy is not None:
        kwargs["proxy"] = proxy
        kwargs["geoip"] = True
    if window is not None:
        kwargs["window"] = window
    if profile_dir is not None:
        kwargs["persistent_context"] = True
        kwargs["user_data_dir"] = profile_dir
    _set_optional(kwargs, "block_images", block_images)
    _set_optional(kwargs, "block_webrtc", block_webrtc)
    _set_optional(kwargs, "block_webgl", block_webgl)
    _set_optional(kwargs, "os", camoufox_os, transform=list)
    _set_optional(kwargs, "locale", locale)
    _set_optional(kwargs, "geoip", geoip)
    _set_optional(kwargs, "firefox_user_prefs", firefox_user_prefs, transform=dict, require_truthy=True)
    _set_optional(kwargs, "args", camoufox_args, transform=list, require_truthy=True)
    _set_optional(kwargs, "enable_cache", enable_cache)
    _set_optional(kwargs, "ff_version", ff_version)

    owns_stack = stack is None
    stack = stack if stack is not None else AsyncExitStack()
    await stack.__aenter__()
    browser_handle: Browser | None = None
    try:
        obj = await stack.enter_async_context(AsyncCamoufox(**kwargs))
        if profile_dir is not None:
            ctx = cast("BrowserContext", obj)
        else:
            browser_handle = cast("Browser", obj)
            ctx = await browser_handle.new_context()
    except BaseException:
        if owns_stack:
            await stack.aclose()
        raise
    return stack, ctx, browser_handle
