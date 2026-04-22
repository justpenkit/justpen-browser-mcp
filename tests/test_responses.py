"""Tests for success/error envelope builders."""

import pytest

from justpen_browser_mcp.responses import error_response, success_response


def test_success_envelope_uses_instance_field():
    env = success_response(instance="alice", data={"ok": True})
    assert env == {"status": "success", "instance": "alice", "data": {"ok": True}}


def test_success_envelope_none_instance():
    env = success_response(instance=None)
    assert env == {"status": "success", "instance": None, "data": {}}


def test_error_envelope_uses_instance_field():
    env = error_response(instance="alice", error_type="instance_not_found", message="nope")
    assert env == {
        "status": "error",
        "instance": "alice",
        "error_type": "instance_not_found",
        "message": "nope",
    }


def test_error_envelope_rejects_unknown_error_type():
    with pytest.raises(ValueError, match="Unknown error_type"):
        error_response(instance=None, error_type="bogus", message="x")
