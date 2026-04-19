"""Aria-snapshot-with-refs and ref→Locator resolution.

Microsoft Playwright MCP exposes element references via YAML aria
snapshots with [ref=eN] annotations. Playwright's bundled server
implements the `snapshotForAI` protocol method that emits these refs,
but the Python high-level API does NOT expose it (as of playwright 1.58).

We work around this by calling the underlying protocol channel directly
via `page._impl_obj._channel.send("snapshotForAI", ...)`. See
https://github.com/microsoft/playwright-python/issues/2867 for the
upstream tracking issue and discussion of this workaround.

The ref resolution side is unaffected — `page.locator("aria-ref=eN")`
uses the standard public Playwright selector engine which is registered
server-side.

This module exists to:
  - Centralize the protocol-channel hack so it has exactly one call site
  - Centralize the locator construction
  - Translate Playwright's "ref not found" errors into our StaleRefError
"""

import logging
import re

from playwright.async_api import Error as PlaywrightError, Locator, Page

from .errors import StaleRefError

logger = logging.getLogger(__name__)

# Default timeout for snapshotForAI protocol calls (milliseconds).
SNAPSHOT_TIMEOUT_MS = 5000


async def capture_snapshot(page: Page) -> str:
    """Capture an aria snapshot with [ref=eN] annotations. Returns YAML string.

    Calls Playwright's `snapshotForAI` protocol method via the raw channel
    because the high-level Python API does not expose it.
    See https://github.com/microsoft/playwright-python/issues/2867
    """
    return await page._impl_obj._channel.send(  # noqa: SLF001  # type: ignore[reportPrivateUsage]  # Playwright has no public API for snapshotForAI; see github.com/microsoft/playwright-python/issues/2867
        "snapshotForAI",
        None,
        {"timeout": SNAPSHOT_TIMEOUT_MS},
    )


def locator_for_ref(page: Page, ref: str) -> Locator:
    """Build a Locator for a previously captured ref."""
    return page.locator(f"aria-ref={ref}")


async def resolve_ref(page: Page, ref: str, timeout_ms: int = 1000) -> Locator:
    """Get a Locator for a ref, raising StaleRefError if missing/stale."""
    locator = locator_for_ref(page, ref)
    try:
        await locator.wait_for(state="attached", timeout=timeout_ms)
    except PlaywrightError as e:
        msg = str(e).lower()
        if "aria-ref" in msg or "no element" in msg or "not found" in msg or "resolved to no element" in msg:
            raise StaleRefError(
                f"Ref '{ref}' not found in current page snapshot. Capture a new snapshot with browser_snapshot."
            ) from e
        raise
    return locator


# Playwright internal selector regex parsers, used by internal_to_python.
# The internal selectors come from the server's generateSelectorSimple(),
# documented in the research notes for browser_generate_locator.
#
# The inner quoted-string pattern `(?:[^"\\]|\\.)*` matches any char that is
# not a quote or backslash, OR a backslash followed by any char — i.e. it
# correctly handles escaped quotes like `\"` inside the captured value.
_QUOTED = r'(?:[^"\\]|\\.)*'
_TESTID_RE = re.compile(rf'^internal:testid=\[([^=]+)="({_QUOTED})"(s?)\]$')
_ROLE_RE = re.compile(r"^internal:role=(\w+)(.*)$")
_ROLE_NAME_RE = re.compile(rf'\[name="({_QUOTED})"(s|i)\]')


def _unescape(text: str) -> str:
    """Unescape a Playwright internal-selector quoted string.

    Playwright escapes backslashes and double quotes inside these strings
    (``\\\\`` and ``\\"``); everything else is literal.
    """
    return text.replace("\\\\", "\\").replace('\\"', '"')


def internal_to_python(sel: str) -> str:
    """Convert a Playwright internal selector (from resolveSelector) to a
    Python API call string.

    Example inputs → outputs:
        internal:testid=[data-testid="submit-btn"s]
            → "get_by_test_id('submit-btn')"
        internal:role=button[name="Cancel"i]
            → 'get_by_role("button", name=\\'Cancel\\')'
        internal:label="Password"s
            → "get_by_label('Password', exact=True)"

    Captured string arguments are unescaped and then formatted with
    ``repr()``, which guarantees a valid Python string literal even when
    the content contains quotes, backslashes, or other special characters.

    Unknown shapes fall back to ``locator(<raw>)``.
    """
    # Frame chains (nested iframes)
    if " >> internal:control=enter-frame >> " in sel:
        parts = sel.split(" >> internal:control=enter-frame >> ")
        return ".content_frame.".join(internal_to_python(p) for p in parts)

    # Test ID (highest priority)
    m = _TESTID_RE.match(sel)
    if m:
        test_id = _unescape(m.group(2))
        return f"get_by_test_id({test_id!r})"

    # ARIA role (with or without name)
    m = _ROLE_RE.match(sel)
    if m:
        role = m.group(1)
        rest = m.group(2)
        name_m = _ROLE_NAME_RE.search(rest)
        if name_m:
            name = _unescape(name_m.group(1))
            exact = name_m.group(2) == "s"
            suffix = ", exact=True" if exact else ""
            return f'get_by_role("{role}", name={name!r}{suffix})'
        return f'get_by_role("{role}")'

    # Label, placeholder, alt, title, text — fallback order matches score priority
    for pattern, method in [
        (rf'^internal:label="({_QUOTED})"(s|i)?$', "get_by_label"),
        (
            rf'^internal:attr=\[placeholder="({_QUOTED})"(s|i)?\]$',
            "get_by_placeholder",
        ),
        (rf'^internal:attr=\[alt="({_QUOTED})"(s|i)?\]$', "get_by_alt_text"),
        (rf'^internal:attr=\[title="({_QUOTED})"(s|i)?\]$', "get_by_title"),
        (rf'^internal:text="({_QUOTED})"(s|i)?$', "get_by_text"),
    ]:
        m = re.match(pattern, sel)
        if m:
            text = _unescape(m.group(1))
            exact = (m.group(2) == "s") if m.group(2) else False
            suffix = ", exact=True" if exact else ""
            return f"{method}({text!r}{suffix})"

    # CSS / complex fallback — repr() gives a valid Python string literal.
    return f"locator({sel!r})"


async def resolve_selector_to_stable(page: Page, ref: str) -> dict[str, str]:
    """Given an aria-ref from a snapshotForAI snapshot, return both the
    stable internal Playwright selector and its Python-syntax equivalent.

    The internal selector is usable directly: page.locator(internal_selector)
    is a durable, navigation-safe locator that survives snapshot churn.

    The python_syntax field is for codegen / test file output, e.g.
    saving a login flow as a reusable pytest fixture.

    Raises StaleRefError if the ref is not found in the current page state.
    """
    try:
        internal = await page._impl_obj.main_frame._channel.send(  # noqa: SLF001  # type: ignore[reportPrivateUsage]  # Playwright has no public API for resolveSelector; see github.com/microsoft/playwright-python/issues/2867
            "resolveSelector",
            None,
            {"selector": f"aria-ref={ref}"},
        )
    except PlaywrightError as e:
        msg = str(e).lower()
        if "aria-ref" in msg or "no element" in msg or "not found" in msg or "resolved to no element" in msg:
            raise StaleRefError(
                f"Ref '{ref}' not found in current page snapshot. Capture a new snapshot with browser_snapshot."
            ) from e
        raise

    return {
        "internal_selector": internal,
        "python_syntax": internal_to_python(internal),
    }
