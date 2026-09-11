"""Shared value coercion helpers for browser_mcp tools."""

from .errors import InvalidParamsError

_TRUTHY = {"true", "1", "checked", "yes"}
_FALSY = {"false", "0", "unchecked", "no", ""}


def coerce_bool(value: object) -> bool:
    """Coerce a user-supplied value to a strict bool.

    Accepts real bools directly. Other values are converted to strings and
    matched against "true"/"false"/"1"/"0"/"checked"/"unchecked"/"yes"/"no"
    or the empty string, ignoring case and surrounding whitespace. This
    includes integers 0 and 1; floats 0.0 and 1.0 do not match.
    Raises InvalidParamsError when the converted string is unrecognized.
    """
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    raise InvalidParamsError(f"cannot interpret {value!r} as boolean")
