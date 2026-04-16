"""Tests for justpen_browser_mcp.responses — success/error envelopes."""

import pytest

from justpen_browser_mcp.responses import error_response, success_response


class TestSuccessResponse:
    def test_minimal_success(self):
        resp = success_response(context="admin")
        assert resp == {
            "status": "success",
            "context": "admin",
            "data": {},
        }

    def test_success_with_data(self):
        resp = success_response(context="admin", data={"url": "https://x.com"})
        assert resp == {
            "status": "success",
            "context": "admin",
            "data": {"url": "https://x.com"},
        }

    def test_status_is_first_key(self):
        resp = success_response(context="admin", data={"foo": "bar"})
        keys = list(resp.keys())
        assert keys[0] == "status"

    def test_context_none_for_server_tools(self):
        resp = success_response(context=None, data={"alive": True})
        assert resp == {
            "status": "success",
            "context": None,
            "data": {"alive": True},
        }


class TestErrorResponse:
    def test_minimal_error(self):
        resp = error_response(
            context="admin",
            error_type="context_not_found",
            message="Context 'admin' does not exist",
        )
        assert resp == {
            "status": "error",
            "context": "admin",
            "error_type": "context_not_found",
            "message": "Context 'admin' does not exist",
        }

    def test_unknown_error_type_raises(self):
        with pytest.raises(ValueError, match="Unknown error_type"):
            error_response(
                context="admin",
                error_type="some_made_up_type",
                message="...",
            )

    def test_all_valid_error_types_accepted(self):
        from justpen_browser_mcp.errors import VALID_ERROR_TYPES

        for et in VALID_ERROR_TYPES:
            resp = error_response(context="admin", error_type=et, message="msg")
            assert resp["error_type"] == et
