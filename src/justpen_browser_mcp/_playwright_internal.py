"""Thin facade over Playwright private RPCs needed by browser_mcp.

Playwright does not expose the AI aria-snapshot or `resolveSelector` through its
public Python API. This module centralises every `_impl_obj._channel.send(...)`
access so the suppression and upstream-issue reference live in one place.

Playwright 1.59 renamed the old `Page.snapshotForAI` RPC to `Frame.ariaSnapshot`
with a `mode` enum (``"ai"`` yields the same ``[ref=eN]``-annotated YAML). The
call below tracks that rename. (The project pins ``playwright<1.60`` because
1.60's Firefox driver crashes on uncaught page errors — see pyproject.) If a
future release changes this RPC again, the e2e suite's snapshot-based tests are
what catch it; unit tests mock the browser.

See: https://github.com/microsoft/playwright-python/issues/2867
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page


async def snapshot_for_ai(page: Page, timeout_ms: int) -> str:
    """Invoke Playwright's internal AI aria-snapshot RPC via the main frame.

    Returns the aria snapshot YAML string with [ref=eN] annotations.

    Uses the ``Frame.ariaSnapshot`` RPC with ``mode="ai"`` (Playwright >= 1.59);
    earlier releases exposed this as ``Page.snapshotForAI``.
    """
    return await page._impl_obj.main_frame._channel.send(  # type: ignore[reportPrivateUsage]  # noqa: SLF001
        "ariaSnapshot",
        None,
        {"mode": "ai", "timeout": float(timeout_ms)},
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
