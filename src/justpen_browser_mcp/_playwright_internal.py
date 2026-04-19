"""Thin facade over Playwright private RPCs needed by browser_mcp.

Playwright does not expose `snapshotForAI` or `resolveSelector` through its
public Python API. This module centralises every `_impl_obj._channel.send(...)`
access so the suppression and upstream-issue reference live in one place.

See: https://github.com/microsoft/playwright-python/issues/2867
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page


async def snapshot_for_ai(page: Page, timeout_ms: int) -> str:
    """Invoke Playwright's internal snapshotForAI RPC on the page.

    Returns the aria snapshot YAML string with [ref=eN] annotations.
    """
    return await page._impl_obj._channel.send(  # type: ignore[reportPrivateUsage]  # noqa: SLF001
        "snapshotForAI",
        None,
        {"timeout": timeout_ms},
    )


async def resolve_selector(page: Page, ref: str) -> str:
    """Invoke Playwright's internal resolveSelector RPC via the main frame.

    Returns the stable internal Playwright selector string.
    """
    return await page._impl_obj.main_frame._channel.send(  # type: ignore[reportPrivateUsage]  # noqa: SLF001
        "resolveSelector",
        None,
        {"selector": f"aria-ref={ref}"},
    )
