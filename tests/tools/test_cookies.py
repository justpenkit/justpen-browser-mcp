"""Tests for tools/cookies.py — 6 cookie + localStorage tools."""

from unittest.mock import AsyncMock, MagicMock

from justpen_browser_mcp.errors import InstanceNotFoundError


def make_ctx_with_page(mock_ctx_mgr, cookies=None, eval_result=None):
    """Wire mock_ctx_mgr.get to return a mock InstanceRecord with a mock active page."""
    page = MagicMock()
    page.url = "about:blank"
    page.evaluate = AsyncMock(return_value=eval_result if eval_result is not None else {})

    async def _goto_side_effect(url):
        page.url = url

    page.goto = AsyncMock(side_effect=_goto_side_effect)
    page.close = AsyncMock()

    ctx = MagicMock()
    ctx.cookies = AsyncMock(return_value=cookies or [])
    ctx.add_cookies = AsyncMock()
    ctx.clear_cookies = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.pages = [page]

    rec = MagicMock()
    rec.context = ctx
    mock_ctx_mgr.get.return_value = rec
    mock_ctx_mgr.active_page.return_value = page
    return ctx, page


class TestBrowserGetCookies:
    async def test_returns_all_cookies(self, mcp_client, mock_ctx_mgr):
        make_ctx_with_page(
            mock_ctx_mgr,
            cookies=[
                {"name": "session", "value": "abc"},
                {"name": "csrf", "value": "xyz"},
            ],
        )
        result = await mcp_client.call_tool("browser_get_cookies", {"instance": "admin"})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["cookies"]) == 2

    async def test_get_cookies_name_filter(self, mcp_client, mock_ctx_mgr):
        make_ctx_with_page(
            mock_ctx_mgr,
            cookies=[
                {"name": "foo", "value": "1"},
                {"name": "bar", "value": "2"},
                {"name": "baz", "value": "3"},
            ],
        )
        result = await mcp_client.call_tool("browser_get_cookies", {"instance": "admin", "name": "bar"})
        assert result.data["status"] == "success"
        cookies = result.data["data"]["cookies"]
        assert len(cookies) == 1
        assert cookies[0]["name"] == "bar"

    async def test_filtered_by_urls(self, mcp_client, mock_ctx_mgr):
        ctx, _ = make_ctx_with_page(mock_ctx_mgr, cookies=[{"name": "x", "value": "1"}])
        result = await mcp_client.call_tool(
            "browser_get_cookies",
            {"instance": "admin", "urls": ["https://app.example.com"]},
        )
        ctx.cookies.assert_awaited_once_with(["https://app.example.com"])
        assert result.data["status"] == "success"

    async def test_unknown_instance(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.get.side_effect = InstanceNotFoundError("not here")
        result = await mcp_client.call_tool("browser_get_cookies", {"instance": "admin"})
        assert result.data["error_type"] == "instance_not_found"


class TestBrowserSetCookies:
    async def test_sets_cookies(self, mcp_client, mock_ctx_mgr):
        ctx, page = make_ctx_with_page(mock_ctx_mgr)
        page.url = "https://example.com/"
        result = await mcp_client.call_tool(
            "browser_set_cookies",
            {
                "instance": "admin",
                "cookies": [{"name": "x", "value": "1", "domain": "example.com", "path": "/"}],
            },
        )
        assert result.data["status"] == "success"
        ctx.add_cookies.assert_awaited_once()

    async def test_set_cookies_default_domain_from_active_page(self, mcp_client, mock_ctx_mgr):
        ctx, page = make_ctx_with_page(mock_ctx_mgr)
        page.url = "https://example.com/x"
        result = await mcp_client.call_tool(
            "browser_set_cookies",
            {
                "instance": "admin",
                "cookies": [{"name": "session", "value": "abc"}],
            },
        )
        assert result.data["status"] == "success"
        ctx.add_cookies.assert_awaited_once()
        sent = ctx.add_cookies.call_args[0][0]
        assert sent[0]["domain"] == "example.com"
        assert sent[0]["name"] == "session"

    async def test_set_cookies_default_domain_uses_active_page(self, mcp_client, mock_ctx_mgr):
        ctx, _ = make_ctx_with_page(mock_ctx_mgr)
        page0 = MagicMock(url="https://a.example/x")
        page1 = MagicMock(url="https://b.example/path")
        ctx.pages = [page0, page1]
        mock_ctx_mgr.active_page = AsyncMock(return_value=page1)
        result = await mcp_client.call_tool(
            "browser_set_cookies",
            {
                "instance": "admin",
                "cookies": [{"name": "session", "value": "abc"}],
            },
        )
        assert result.data["status"] == "success"
        ctx.add_cookies.assert_awaited_once()
        sent = ctx.add_cookies.call_args[0][0]
        assert sent[0]["domain"] == "b.example"

    async def test_set_cookies_no_domain_no_page(self, mcp_client, mock_ctx_mgr):
        ctx, _ = make_ctx_with_page(mock_ctx_mgr)
        ctx.pages = []
        result = await mcp_client.call_tool(
            "browser_set_cookies",
            {
                "instance": "admin",
                "cookies": [{"name": "session", "value": "abc"}],
            },
        )
        assert result.data["error_type"] == "invalid_params"
        assert "neither domain nor url" in result.data["message"]

    async def test_set_cookies_with_url_field_passes_through(self, mcp_client, mock_ctx_mgr):
        ctx, _ = make_ctx_with_page(mock_ctx_mgr)
        ctx.pages = []
        cookie = {"name": "session", "value": "abc", "url": "https://x.com"}
        result = await mcp_client.call_tool(
            "browser_set_cookies",
            {"instance": "admin", "cookies": [cookie]},
        )
        assert result.data["status"] == "success"
        ctx.add_cookies.assert_awaited_once()
        sent = ctx.add_cookies.call_args[0][0]
        assert sent[0] == cookie
        assert sent[0]["url"] == "https://x.com"
        assert "domain" not in sent[0]


class TestBrowserClearCookies:
    async def test_clears(self, mcp_client, mock_ctx_mgr):
        ctx, _ = make_ctx_with_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_clear_cookies", {"instance": "admin"})
        assert result.data["status"] == "success"
        ctx.clear_cookies.assert_awaited_once()


class TestBrowserGetLocalStorage:
    async def test_reads_local_storage_for_origin(self, mcp_client, mock_ctx_mgr):
        _ctx, page = make_ctx_with_page(
            mock_ctx_mgr,
            eval_result={"auth_token": "xyz", "theme": "dark"},
        )
        result = await mcp_client.call_tool(
            "browser_get_local_storage",
            {"instance": "admin", "origin": "https://app.example.com"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["items"] == {"auth_token": "xyz", "theme": "dark"}
        page.goto.assert_awaited_once_with("https://app.example.com")

    async def test_get_local_storage_key(self, mcp_client, mock_ctx_mgr):
        _ctx, page = make_ctx_with_page(mock_ctx_mgr, eval_result="dark")
        result = await mcp_client.call_tool(
            "browser_get_local_storage",
            {
                "instance": "admin",
                "origin": "https://app.example.com",
                "key": "theme",
            },
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["key"] == "theme"
        assert result.data["data"]["value"] == "dark"
        assert result.data["data"]["origin"] == "https://app.example.com"
        page.evaluate.assert_awaited_once_with("(k) => localStorage.getItem(k)", "theme")


class TestBrowserSetLocalStorage:
    async def test_sets_items(self, mcp_client, mock_ctx_mgr):
        _ctx, page = make_ctx_with_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_set_local_storage",
            {
                "instance": "admin",
                "origin": "https://app.example.com",
                "items": {"auth_token": "xyz"},
            },
        )
        assert result.data["status"] == "success"
        page.evaluate.assert_awaited_once()

    async def test_set_local_storage_safe_eval(self, mcp_client, mock_ctx_mgr):
        _ctx, page = make_ctx_with_page(mock_ctx_mgr)
        items = {"auth_token": "xyz", "theme": "dark"}
        result = await mcp_client.call_tool(
            "browser_set_local_storage",
            {
                "instance": "admin",
                "origin": "https://app.example.com",
                "items": items,
            },
        )
        assert result.data["status"] == "success"
        call_args = page.evaluate.call_args
        js = call_args[0][0]
        arg = call_args[0][1]
        assert "(items)" in js
        assert "localStorage.setItem" in js
        # items must be passed as second arg, NOT interpolated into JS source
        assert arg == items
        assert "auth_token" not in js
        assert "xyz" not in js


class TestBrowserClearLocalStorage:
    async def test_clears_specific_origin(self, mcp_client, mock_ctx_mgr):
        _ctx, page = make_ctx_with_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_clear_local_storage",
            {"instance": "admin", "origin": "https://app.example.com"},
        )
        assert result.data["status"] == "success"
        page.goto.assert_awaited_once_with("https://app.example.com")
        page.evaluate.assert_awaited_once()
        eval_arg = page.evaluate.call_args[0][0]
        assert "localStorage.clear" in eval_arg

    async def test_clear_local_storage_no_origin(self, mcp_client, mock_ctx_mgr):
        ctx, page = make_ctx_with_page(mock_ctx_mgr)
        page.url = "https://already-here.example.com/"
        result = await mcp_client.call_tool(
            "browser_clear_local_storage",
            {"instance": "admin"},
        )
        assert result.data["status"] == "success"
        # Should NOT have opened a new page
        ctx.new_page.assert_not_awaited()
        page.evaluate.assert_awaited_once()
        eval_arg = page.evaluate.call_args[0][0]
        assert "localStorage.clear" in eval_arg
        assert result.data["data"]["origin"] == "https://already-here.example.com/"
