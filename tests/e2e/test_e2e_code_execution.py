"""End-to-end tests for the in-page code execution tools.

browser_evaluate runs a JS expression in an ISOLATED world, so only pure
expressions and DOM-backed reads (document.title, element text) cross the
boundary — never window.* globals set by page scripts. browser_run_code runs a
Python snippet with full Playwright access and returns via a `return` statement.
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_evaluate_pure_expression(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "x1"})
    await call(e2e_client, "browser_navigate", {"instance": "x1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_evaluate", {"instance": "x1", "expression": "1 + 2"})
    assert r["status"] == "success"
    assert r["data"]["result"] == 3


async def test_evaluate_reads_document_title(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "x2"})
    await call(e2e_client, "browser_navigate", {"instance": "x2", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_evaluate", {"instance": "x2", "expression": "document.title"})
    assert r["status"] == "success"
    assert r["data"]["result"] == "Index"


async def test_evaluate_syntax_error_is_evaluation_failed(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "x3"})
    await call(e2e_client, "browser_navigate", {"instance": "x3", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_evaluate", {"instance": "x3", "expression": "@@@ not valid @@@"})
    assert r["status"] == "error"
    assert r["error_type"] == "evaluation_failed"


async def test_run_code_multiline_returns_value(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "x4"})
    await call(e2e_client, "browser_navigate", {"instance": "x4", "url": f"{test_site}/index.html"})

    code = (
        "title = await page.title()\nheading = await page.locator('#title').inner_text()\nreturn f'{title}:{heading}'"
    )
    r = await call(e2e_client, "browser_run_code", {"instance": "x4", "code": code})
    assert r["status"] == "success"
    assert r["data"]["result"] == "Index:Home"


async def test_run_code_exception_is_evaluation_failed(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "x5"})
    await call(e2e_client, "browser_navigate", {"instance": "x5", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_run_code", {"instance": "x5", "code": "raise ValueError('boom')"})
    assert r["status"] == "error"
    assert r["error_type"] == "evaluation_failed"
    assert "boom" in r["message"]
