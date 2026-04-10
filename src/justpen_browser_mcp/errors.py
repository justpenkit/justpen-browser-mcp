"""Custom exception types for the browser_mcp server.

Each exception class corresponds 1:1 with one of the standardized
error_type values returned in MCP tool error responses. Tool dispatch
catches BrowserMcpError instances and converts them to error_response()
envelopes; all other exceptions become 'internal_error'.
"""


class BrowserMcpError(Exception):
    """Base class for all browser_mcp internal exceptions.

    Subclasses must define a class-level `error_type` string matching
    one of the values in VALID_ERROR_TYPES.
    """

    error_type: str = "internal_error"


class ContextNotFoundError(BrowserMcpError):
    error_type = "context_not_found"


class ContextAlreadyExistsError(BrowserMcpError):
    error_type = "context_already_exists"


class InvalidStateFileError(BrowserMcpError):
    error_type = "invalid_state_file"


class StateFileNotFoundError(BrowserMcpError):
    error_type = "state_file_not_found"


class BrowserNotRunningError(BrowserMcpError):
    error_type = "browser_not_running"


class BinaryNotFoundError(BrowserMcpError):
    error_type = "binary_not_found"


class ElementNotFoundError(BrowserMcpError):
    error_type = "element_not_found"


class StaleRefError(BrowserMcpError):
    error_type = "stale_ref"


class NavigationFailedError(BrowserMcpError):
    error_type = "navigation_failed"


class NavigationTimeoutError(BrowserMcpError):
    error_type = "navigation_timeout"


class WaitTimeoutError(BrowserMcpError):
    error_type = "wait_timeout"


class DialogNotPresentError(BrowserMcpError):
    error_type = "dialog_not_present"


class EvaluationFailedError(BrowserMcpError):
    error_type = "evaluation_failed"


class VerificationFailedError(BrowserMcpError):
    error_type = "verification_failed"


class InvalidParamsError(BrowserMcpError):
    error_type = "invalid_params"


class InternalError(BrowserMcpError):
    error_type = "internal_error"


class ModalStateBlockedError(BrowserMcpError):
    error_type = "modal_state_blocked"


VALID_ERROR_TYPES = frozenset(
    {
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
)
