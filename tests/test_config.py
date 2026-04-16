"""Tests for justpen_browser_mcp.config."""

from justpen_browser_mcp.config import BrowserServerConfig


class TestBrowserServerConfig:
    def test_defaults(self):
        cfg = BrowserServerConfig.from_env({})
        assert cfg.headless is True
        assert cfg.log_level == "INFO"

    def test_headless_false_via_env(self):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_HEADLESS": "false"})
        assert cfg.headless is False

    def test_headless_true_via_env(self):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_HEADLESS": "true"})
        assert cfg.headless is True

    def test_headless_case_insensitive(self):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_HEADLESS": "FALSE"})
        assert cfg.headless is False

    def test_log_level_from_env(self):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_LOG_LEVEL": "DEBUG"})
        assert cfg.log_level == "DEBUG"

    def test_unknown_env_vars_ignored(self):
        cfg = BrowserServerConfig.from_env({"FOO": "bar", "BROWSER_MCP_HEADLESS": "true"})
        assert cfg.headless is True
