"""Tests for launch_instance helper — Camoufox mocked."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp.instance import launch_instance


@pytest.fixture
def mock_camoufox(monkeypatch):
    """Patch AsyncCamoufox so its __aenter__ returns a configurable object."""
    captured: dict[str, Any] = {}
    browser = MagicMock()
    ctx = MagicMock()
    browser.new_context = AsyncMock(return_value=ctx)

    class FakeCamoufox:
        def __init__(self, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs
            captured["self"] = self

        async def __aenter__(self) -> Any:
            return browser if captured["kwargs"].get("persistent_context") is not True else ctx

        async def __aexit__(self, *_: Any) -> None:
            pass

    monkeypatch.setattr("justpen_browser_mcp.instance.AsyncCamoufox", FakeCamoufox)
    return {"captured": captured, "browser": browser, "ctx": ctx}


@pytest.mark.asyncio
async def test_launch_persistent_sets_user_data_dir(mock_camoufox, tmp_path):
    stack, ctx = await launch_instance(
        profile_dir=str(tmp_path),
        headless=True,
        proxy=None,
        humanize=True,
        window=None,
    )
    assert mock_camoufox["captured"]["kwargs"]["persistent_context"] is True
    assert mock_camoufox["captured"]["kwargs"]["user_data_dir"] == str(tmp_path)
    assert ctx is mock_camoufox["ctx"]
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_ephemeral_calls_new_context(mock_camoufox):
    stack, ctx = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy=None,
        humanize=True,
        window=None,
    )
    assert "persistent_context" not in mock_camoufox["captured"]["kwargs"]
    mock_camoufox["browser"].new_context.assert_awaited_once()
    assert ctx is mock_camoufox["ctx"]
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_proxy_enables_geoip(mock_camoufox):
    stack, _ = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy={"server": "http://proxy:3128"},
        humanize=True,
        window=None,
    )
    kwargs = mock_camoufox["captured"]["kwargs"]
    assert kwargs["proxy"] == {"server": "http://proxy:3128"}
    assert kwargs["geoip"] is True
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_no_proxy_no_geoip(mock_camoufox):
    stack, _ = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy=None,
        humanize=True,
        window=None,
    )
    kwargs = mock_camoufox["captured"]["kwargs"]
    assert "proxy" not in kwargs
    assert "geoip" not in kwargs
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_hardcoded_defaults(mock_camoufox):
    stack, _ = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy=None,
        humanize=True,
        window=None,
    )
    kwargs = mock_camoufox["captured"]["kwargs"]
    assert kwargs["block_webrtc"] is True
    assert kwargs["block_images"] is False
    assert kwargs["disable_coop"] is True
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_window_passthrough(mock_camoufox):
    stack, _ = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy=None,
        humanize=True,
        window=(1280, 800),
    )
    assert mock_camoufox["captured"]["kwargs"]["window"] == (1280, 800)
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_window_none_omitted(mock_camoufox):
    stack, _ = await launch_instance(
        profile_dir=None,
        headless=True,
        proxy=None,
        humanize=True,
        window=None,
    )
    assert "window" not in mock_camoufox["captured"]["kwargs"]
    await stack.aclose()


@pytest.mark.asyncio
async def test_launch_rolls_back_stack_on_failure(monkeypatch):
    aexit_called = False

    class BoomCamoufox:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            raise RuntimeError("boom")

        async def __aexit__(self, *_: Any) -> None:
            nonlocal aexit_called
            aexit_called = True

    monkeypatch.setattr("justpen_browser_mcp.instance.AsyncCamoufox", BoomCamoufox)
    with pytest.raises(RuntimeError, match="boom"):
        await launch_instance(
            profile_dir=None,
            headless=True,
            proxy=None,
            humanize=True,
            window=None,
        )
