"""Tests for error_type registry and exception class → error_type mapping."""

from justpen_browser_mcp.errors import (
    VALID_ERROR_TYPES,
    BrowserMcpError,
    InstanceAlreadyExistsError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    ProfileDirInUseError,
)


def test_valid_error_types_contains_new_instance_types():
    assert "instance_not_found" in VALID_ERROR_TYPES
    assert "instance_already_exists" in VALID_ERROR_TYPES
    assert "instance_limit_exceeded" in VALID_ERROR_TYPES
    assert "profile_dir_in_use" in VALID_ERROR_TYPES


def test_valid_error_types_drops_deprecated():
    assert "context_not_found" not in VALID_ERROR_TYPES
    assert "context_already_exists" not in VALID_ERROR_TYPES
    assert "browser_not_running" not in VALID_ERROR_TYPES
    assert "invalid_state_file" not in VALID_ERROR_TYPES
    assert "state_file_not_found" not in VALID_ERROR_TYPES


def test_instance_not_found_mapping():
    err = InstanceNotFoundError("missing 'alice'")
    assert isinstance(err, BrowserMcpError)
    assert err.error_type == "instance_not_found"


def test_instance_already_exists_mapping():
    err = InstanceAlreadyExistsError("'alice' already registered")
    assert err.error_type == "instance_already_exists"


def test_instance_limit_exceeded_mapping():
    err = InstanceLimitExceededError("limit 10 reached")
    assert err.error_type == "instance_limit_exceeded"


def test_profile_dir_in_use_mapping():
    err = ProfileDirInUseError("profile /foo held by 'bob'")
    assert err.error_type == "profile_dir_in_use"


def test_valid_error_types_has_expected_count():
    # 15 active + 1 new profile_dir_in_use = 16
    assert len(VALID_ERROR_TYPES) == 16
