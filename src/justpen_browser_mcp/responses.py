"""Standard response envelope builders for browser_mcp tools.

Every tool returns either a success or error envelope. The shape is fixed
and validated at construction time so bugs surface early.
"""

from .errors import VALID_ERROR_TYPES


def success_response(context: str | None, data: dict | None = None) -> dict:
    """Build a success envelope.

    Args:
        context: The context name the tool operated on. None for server-level
            tools (browser_status, browser_list_contexts) that are not
            context-scoped.
        data: Tool-specific payload. Defaults to {}.

    Returns:
        {"status": "success", "context": <name>, "data": {...}}
    """
    return {
        "status": "success",
        "context": context,
        "data": data if data is not None else {},
    }


def error_response(context: str | None, error_type: str, message: str) -> dict:
    """Build an error envelope.

    Args:
        context: The context the failed call referenced. None if the call
            was a server-level tool.
        error_type: One of the standardized values in VALID_ERROR_TYPES.
            Unknown values raise ValueError to catch typos at dev time.
        message: Action-oriented human-readable description of the failure.

    Returns:
        {"status": "error", "context": <name>, "error_type": <type>, "message": <msg>}
    """
    if error_type not in VALID_ERROR_TYPES:
        raise ValueError(f"Unknown error_type '{error_type}'. Valid: {', '.join(sorted(VALID_ERROR_TYPES))}")
    return {
        "status": "error",
        "context": context,
        "error_type": error_type,
        "message": message,
    }
