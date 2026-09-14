"""Tool-level tests for listing and saving retained downloads."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Error as PlaywrightError

from justpen_browser_mcp.downloads import DownloadRegistry

pytestmark = pytest.mark.integration


def add_download(mock_mgr, *, page_id: str = "page-origin") -> tuple[str, MagicMock]:
    registry = DownloadRegistry(4)
    item = MagicMock(
        url="https://example.test/report",
        suggested_filename="report.bin",
        save_as=AsyncMock(),
    )
    download_id = registry.register(item, page_id)
    assert download_id is not None
    mock_mgr.state.return_value.downloads = registry
    mock_mgr.get.return_value.instance_id = "instance-id"
    return download_id, item


async def test_list_filters_closed_origin_without_resolving_page(mcp_client, mock_mgr) -> None:
    download_id, _ = add_download(mock_mgr)

    result = await mcp_client.call_tool("browser_downloads", {"instance": "browser", "page_id": "page-origin"})

    assert result.data["status"] == "success"
    assert [item["download_id"] for item in result.data["data"]["downloads"]] == [download_id]
    assert result.data["data"]["has_more"] is False
    mock_mgr.active_page.assert_not_awaited()


async def test_save_pins_for_copy_then_records_explicit_path(mcp_client, mock_mgr, tmp_path) -> None:
    download_id, item = add_download(mock_mgr)
    destination = str(tmp_path / "chosen.bin")

    result = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": download_id, "path": destination},
    )

    assert result.data == {
        "status": "success",
        "instance": "browser",
        "data": {"download_id": download_id, "path": destination},
    }
    item.save_as.assert_awaited_once_with(destination)
    metadata = mock_mgr.state.return_value.downloads.page()["items"][0]
    assert metadata["status"] == "saved"
    assert metadata["path"] == destination


async def test_saved_handle_can_be_copied_again_to_another_explicit_path(mcp_client, mock_mgr, tmp_path) -> None:
    download_id, item = add_download(mock_mgr)
    first_path = str(tmp_path / "first.bin")
    second_path = str(tmp_path / "second.bin")

    first = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": download_id, "path": first_path},
    )
    second = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": download_id, "path": second_path},
    )

    assert first.data["status"] == "success"
    assert second.data["status"] == "success"
    assert item.save_as.await_count == 2
    metadata = mock_mgr.state.return_value.downloads.page()["items"][0]
    assert metadata["status"] == "saved"
    assert metadata["path"] == second_path


async def test_missing_download_fails_before_copy(mcp_client, mock_mgr, tmp_path) -> None:
    add_download(mock_mgr)

    result = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": "foreign", "path": str(tmp_path / "out")},
    )

    assert result.data["error_type"] == "download_not_found"


async def test_playwright_save_failure_is_recorded_and_pin_is_released(mcp_client, mock_mgr) -> None:
    download_id, item = add_download(mock_mgr)
    item.save_as.side_effect = PlaywrightError("transfer failed")

    result = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": download_id, "path": "/missing/out"},
    )

    assert result.data["error_type"] == "download_failed"
    registry = mock_mgr.state.return_value.downloads
    assert registry.pin(download_id).status == "saving"
    registry.unpin(download_id)


async def test_concurrent_save_of_pinned_handle_is_rejected(mcp_client, mock_mgr, tmp_path) -> None:
    download_id, item = add_download(mock_mgr)
    registry = mock_mgr.state.return_value.downloads
    registry.pin(download_id)

    result = await mcp_client.call_tool(
        "browser_download_save",
        {"instance": "browser", "download_id": download_id, "path": str(tmp_path / "out")},
    )

    assert result.data["error_type"] == "download_failed"
    item.save_as.assert_not_awaited()
