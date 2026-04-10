"""Shared value coercion helpers for browser_mcp tools."""

from .errors import InvalidParamsError

_TRUTHY = {"true", "1", "checked", "yes"}
_FALSY = {"false", "0", "unchecked", "no", ""}


def coerce_bool(value) -> bool:
    """Coerce a user-supplied value to a strict bool.

    Accepts: real bool, or strings like "true"/"false"/"1"/"0"/"checked"/
    "unchecked"/"yes"/"no" (case-insensitive, surrounding whitespace
    ignored). Raises InvalidParamsError on anything else (including
    ints/floats other than the literal accepted strings).
    """
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    raise InvalidParamsError(f"cannot interpret {value!r} as boolean")
