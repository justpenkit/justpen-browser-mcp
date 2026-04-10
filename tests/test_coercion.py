"""Tests for justpen_browser_mcp.coercion.coerce_bool."""

import pytest

from justpen_browser_mcp.coercion import coerce_bool
from justpen_browser_mcp.errors import InvalidParamsError


@pytest.mark.parametrize(
    "value",
    [True, "true", "1", "checked", "yes", "TRUE", " True ", "YES", "Checked"],
)
def test_coerce_bool_true_variants(value):
    assert coerce_bool(value) is True


@pytest.mark.parametrize(
    "value",
    [False, "false", "0", "unchecked", "no", "", "FALSE", " No ", "Unchecked"],
)
def test_coerce_bool_false_variants(value):
    assert coerce_bool(value) is False


@pytest.mark.parametrize("value", ["bogus", "maybe", 2.5, 2, "2"])
def test_coerce_bool_invalid(value):
    with pytest.raises(InvalidParamsError):
        coerce_bool(value)
