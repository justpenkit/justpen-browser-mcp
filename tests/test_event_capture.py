"""The native listener buffers and their request lookup share a bounded lifetime."""

from unittest.mock import MagicMock

from justpen_browser_mcp.config import BrowserServerConfig


async def test_listener_retention_bounds_request_index_and_preserves_updates(manager):
    manager._config = BrowserServerConfig(event_buffer_size=2)
    record = await manager.create("evidence")
    page = MagicMock()
    page.is_closed.return_value = False
    record.context.pages = [page]
    for event in record.context.on.call_args_list:
        if event.args[0] == "page":
            event.args[1](page)
    handlers = {event.args[0]: event.args[1] for event in page.on.call_args_list}
    requests = []
    for number in range(5):
        request = MagicMock(url=f"https://example.test/{number}", method="GET", resource_type="fetch")
        requests.append(request)
        handlers["request"](request)
        handlers["console"](MagicMock(type="log", text=str(number), location={}))
    assert len(record.state.network_requests) == 2
    assert len(record.state.network_request_index) == 2
    assert len(record.state.console_messages) == 2
    assert record.state.network_requests.dropped_count == 3
    before = record.state.network_requests.page()
    handlers["response"](MagicMock(request=requests[-1], status=201))
    handlers["requestfailed"](requests[0])  # An evicted request cannot re-enter the buffer.
    after = record.state.network_requests.page(after=before["next_cursor"])
    assert len(after["items"]) == 1
    entry = after["items"][0]
    assert entry["status"] == 201
    assert entry["request_id"]
    assert entry["page_id"] == manager.page_id("evidence", page)
    assert entry["timestamp"]
    assert len(record.state.network_request_index) == 2
    requests[-1].failure = "connection lost"
    handlers["requestfailed"](requests[-1])
    failed = record.state.network_requests.page(after=after["next_cursor"])["items"][0]
    assert failed["request_id"] == entry["request_id"]
    assert failed["failure"] == "connection lost"
