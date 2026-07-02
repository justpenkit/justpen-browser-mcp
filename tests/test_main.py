from justpen_browser_mcp.__main__ import _run_kwargs
from justpen_browser_mcp.config import BrowserServerConfig


def test_run_kwargs_stdio_is_empty():
    assert _run_kwargs(BrowserServerConfig(transport="stdio")) == {}


def test_run_kwargs_http_includes_host_port():
    cfg = BrowserServerConfig(transport="http", host="127.0.0.1", port=8931)
    assert _run_kwargs(cfg) == {"transport": "http", "host": "127.0.0.1", "port": 8931}
