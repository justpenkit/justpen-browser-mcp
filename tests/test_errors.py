"""Tests for justpen_browser_mcp.errors — exception types and registry."""

import pytest

from justpen_browser_mcp.errors import (
    BrowserMcpError,
    ContextNotFoundError,
    ContextAlreadyExistsError,
    InvalidStateFileError,
    StateFileNotFoundError,
    BrowserNotRunningError,
    BinaryNotFoundError,
    ElementNotFoundError,
    StaleRefError,
    NavigationFailedError,
    NavigationTimeoutError,
    WaitTimeoutError,
    DialogNotPresentError,
    EvaluationFailedError,
    VerificationFailedError,
    InvalidParamsError,
    InternalError,
    ModalStateBlockedError,
    VALID_ERROR_TYPES,
)


class TestErrorTypeRegistry:
    def test_all_17_error_types_registered(self):
        assert len(VALID_ERROR_TYPES) == 17

    def test_expected_error_types_present(self):
        expected = {
            "context_not_found",
            "context_already_exists",
            "invalid_state_file",
            "state_file_not_found",
            "browser_not_running",
            "binary_not_found",
            "element_not_found",
            "stale_ref",
            "navigation_failed",
            "navigation_timeout",
            "wait_timeout",
            "dialog_not_present",
            "evaluation_failed",
            "verification_failed",
            "invalid_params",
            "internal_error",
            "modal_state_blocked",
        }
        assert set(VALID_ERROR_TYPES) == expected


class TestExceptionHierarchy:
    def test_all_subclass_browser_mcp_error(self):
        for cls in [
            ContextNotFoundError,
            ContextAlreadyExistsError,
            InvalidStateFileError,
            StateFileNotFoundError,
            BrowserNotRunningError,
            BinaryNotFoundError,
            ElementNotFoundError,
            StaleRefError,
            NavigationFailedError,
            NavigationTimeoutError,
            WaitTimeoutError,
            DialogNotPresentError,
            EvaluationFailedError,
            VerificationFailedError,
            InvalidParamsError,
            InternalError,
            ModalStateBlockedError,
        ]:
            assert issubclass(cls, BrowserMcpError)

    def test_each_class_has_distinct_error_type(self):
        classes = [
            (ContextNotFoundError, "context_not_found"),
            (ContextAlreadyExistsError, "context_already_exists"),
            (InvalidStateFileError, "invalid_state_file"),
            (StateFileNotFoundError, "state_file_not_found"),
            (BrowserNotRunningError, "browser_not_running"),
            (BinaryNotFoundError, "binary_not_found"),
            (ElementNotFoundError, "element_not_found"),
            (StaleRefError, "stale_ref"),
            (NavigationFailedError, "navigation_failed"),
            (NavigationTimeoutError, "navigation_timeout"),
            (WaitTimeoutError, "wait_timeout"),
            (DialogNotPresentError, "dialog_not_present"),
            (EvaluationFailedError, "evaluation_failed"),
            (VerificationFailedError, "verification_failed"),
            (InvalidParamsError, "invalid_params"),
            (InternalError, "internal_error"),
            (ModalStateBlockedError, "modal_state_blocked"),
        ]
        for cls, expected_type in classes:
            assert cls.error_type == expected_type, f"{cls.__name__}.error_type"

    def test_exception_carries_message(self):
        e = ContextNotFoundError("Context 'foo' does not exist")
        assert str(e) == "Context 'foo' does not exist"
        assert e.error_type == "context_not_found"

    def test_can_raise_and_catch_as_base(self):
        with pytest.raises(BrowserMcpError) as exc_info:
            raise ElementNotFoundError("ref e2 missing")
        assert exc_info.value.error_type == "element_not_found"
