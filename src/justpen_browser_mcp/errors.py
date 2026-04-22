"""Custom exception types for the browser_mcp server.

Each exception class corresponds 1:1 with one of the standardized
error_type values returned in MCP tool error responses. Tool dispatch
catches BrowserMcpError instances and converts them to error_response()
envelopes; all other exceptions become 'internal_error'.
"""


class BrowserMcpError(Exception):
    """Base class for all browser_mcp internal exceptions."""

    error_type: str = "internal_error"


class InstanceNotFoundError(BrowserMcpError):
    """Raised when a named instance does not exist in the registry."""

    error_type = "instance_not_found"


class InstanceAlreadyExistsError(BrowserMcpError):
    """Raised when creating an instance with a name that is already taken."""

    error_type = "instance_already_exists"


class InstanceLimitExceededError(BrowserMcpError):
    """Raised when create_instance is called but max_instances is already reached."""

    error_type = "instance_limit_exceeded"


class ProfileDirInUseError(BrowserMcpError):
    """Raised when a persistent profile_dir is already held by another live instance."""

    error_type = "profile_dir_in_use"


class BinaryNotFoundError(BrowserMcpError):
    """Raised when the Camoufox binary cannot be located or fetched."""

    error_type = "binary_not_found"


class ElementNotFoundError(BrowserMcpError):
    """Raised when a locator query resolves to zero elements."""

    error_type = "element_not_found"


class StaleRefError(BrowserMcpError):
    """Raised when an aria-ref no longer matches any element in the current snapshot."""

    error_type = "stale_ref"


class NavigationFailedError(BrowserMcpError):
    """Raised when a navigation attempt fails (network error, invalid URL, etc.)."""

    error_type = "navigation_failed"


class NavigationTimeoutError(BrowserMcpError):
    """Raised when a navigation does not complete within the timeout window."""

    error_type = "navigation_timeout"


class WaitTimeoutError(BrowserMcpError):
    """Raised when a wait condition is not satisfied before the timeout elapses."""

    error_type = "wait_timeout"


class DialogNotPresentError(BrowserMcpError):
    """Raised when a dialog operation runs but no dialog is currently open."""

    error_type = "dialog_not_present"


class EvaluationFailedError(BrowserMcpError):
    """Raised when evaluating user-supplied JS in the page throws."""

    error_type = "evaluation_failed"


class VerificationFailedError(BrowserMcpError):
    """Raised when a verify_* tool's assertion does not hold."""

    error_type = "verification_failed"


class InvalidParamsError(BrowserMcpError):
    """Raised when tool input fails validation (bad shape, out-of-range, etc.)."""

    error_type = "invalid_params"


class InternalError(BrowserMcpError):
    """Raised for unexpected internal failures not covered by a more specific type."""

    error_type = "internal_error"


class ModalStateBlockedError(BrowserMcpError):
    """Raised when a tool call is blocked because a dialog or file chooser is open."""

    error_type = "modal_state_blocked"


VALID_ERROR_TYPES = frozenset(
    {
        "instance_not_found",
        "instance_already_exists",
        "instance_limit_exceeded",
        "profile_dir_in_use",
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
