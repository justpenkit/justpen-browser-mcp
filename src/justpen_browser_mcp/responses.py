"""Standard response envelope builders for browser_mcp tools."""

from typing import Any

from .errors import VALID_ERROR_TYPES


def success_response(instance: str | None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a success envelope.

    Args:
        instance: The instance name the tool operated on. None for server-level
            tools (e.g. browser_list_instances) that are not instance-scoped.
        data: Tool-specific payload. Defaults to {}.

    Returns:
        {"status": "success", "instance": <name>, "data": {...}}
    """
    return {
        "status": "success",
        "instance": instance,
        "data": data if data is not None else {},
    }


def error_response(instance: str | None, error_type: str, message: str) -> dict[str, Any]:
    """Build an error envelope.

    Args:
        instance: The instance the failed call referenced. None for server-level tools.
        error_type: One of the standardized values in VALID_ERROR_TYPES.
        message: Action-oriented human-readable description of the failure.

    Returns:
        {"status": "error", "instance": <name>, "error_type": <type>, "message": <msg>}
    """
    if error_type not in VALID_ERROR_TYPES:
        raise ValueError(f"Unknown error_type '{error_type}'. Valid: {', '.join(sorted(VALID_ERROR_TYPES))}")
    return {
        "status": "error",
        "instance": instance,
        "error_type": error_type,
        "message": message,
    }
