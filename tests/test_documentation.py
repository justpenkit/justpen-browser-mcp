"""Exercise product documentation, version injection and strict link validation."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tomllib
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    sys.version_info[:2] != (3, 13), reason="Documentation builds are validated on Python 3.13"
)


@pytest.fixture
def documentation_project(tmp_path):
    for name in ("mkdocs.yml", "pyproject.toml"):
        shutil.copy2(ROOT / name, tmp_path / name)
    for name in ("docs", "src"):
        shutil.copytree(ROOT / name, tmp_path / name)
    hook = ROOT / "scripts" / "docs_version.py"
    (tmp_path / "scripts").mkdir()
    shutil.copy2(hook, tmp_path / "scripts" / hook.name)
    return tmp_path


def build_documentation(project):
    return subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


@pytest.fixture
def built_documentation(documentation_project):
    result = build_documentation(documentation_project)
    assert result.returncode == 0, result.stdout + result.stderr
    return documentation_project / "site"


def test_documentation_builds_strictly(built_documentation):
    assert (built_documentation / "index.html").is_file()


def test_product_notes_render_as_admonitions(built_documentation):
    server = (built_documentation / "getting-started" / "run-server" / "index.html").read_text()
    instances = (built_documentation / "concepts" / "instances-isolation" / "index.html").read_text()
    assert 'class="admonition warning"' in server
    assert "No built-in authentication" in server
    assert 'class="admonition note"' in instances
    assert "Fingerprint re-roll on restart" in instances


@pytest.mark.parametrize("target", ["missing-guide.md", "index.md#missing-anchor"])
def test_documentation_rejects_broken_internal_links(documentation_project, target):
    index = documentation_project / "docs" / "index.md"
    index.write_text(index.read_text() + f"\n[Broken link]({target})\n")
    result = build_documentation(documentation_project)
    assert result.returncode != 0, result.stdout + result.stderr
    assert target in result.stdout + result.stderr


@pytest.mark.parametrize("version", [None, "7.8.9"])
def test_install_commands_use_project_version(documentation_project, version):
    metadata = documentation_project / "pyproject.toml"
    current = tomllib.loads(metadata.read_text())["project"]["version"]
    if version is not None:
        metadata.write_text(metadata.read_text().replace(f'version = "{current}"', f'version = "{version}"', 1))
    expected = current if version is None else version
    preserved = (
        "Historical release: justpen-browser-mcp@v0.3.0",
        f"Historical source: https://github.com/justpenkit/justpen-browser-mcp@v{current}",
        "Other package: other-justpen-browser-mcp @ "
        f"git+https://github.com/example/other-justpen-browser-mcp@v{current}",
        f"Prerelease: justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v{current}-rc1",
    )
    index = documentation_project / "docs/index.md"
    index.write_text(index.read_text() + "\n\n" + "\n\n".join(preserved) + "\n")
    archived_install = (
        f'uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v{current}"'
    )
    history = documentation_project / "docs/guides/template-updates.md"
    history.write_text(history.read_text() + f"\n```bash\n{archived_install}\n```\n")
    result = build_documentation(documentation_project)
    assert result.returncode == 0, result.stdout + result.stderr
    for relative in ("index.html", "getting-started/install/index.html"):
        html = (documentation_project / "site" / relative).read_text()
        text = unescape(re.sub(r"<[^>]+>", "", html))
        assert f"git+https://github.com/justpenkit/justpen-browser-mcp@v{expected}" in text
        assert "{{ project_version }}" not in text
        assert "import.meta.env" not in text
        if relative == "index.html":
            for reference in preserved:
                assert reference in text
    history_html = (documentation_project / "site/guides/template-updates/index.html").read_text()
    assert archived_install in unescape(re.sub(r"<[^>]+>", "", history_html))


@pytest.mark.parametrize("relative", ["README.md", "docs/index.md", "docs/getting-started/install.md"])
def test_raw_install_commands_use_current_project_pin(relative):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    markdown = (ROOT / relative).read_text()
    assert (
        f'uv add "{project["name"]} @ git+https://github.com/justpenkit/{project["name"]}@v{project["version"]}"'
        in markdown
    )
    assert "{{ project_version }}" not in markdown


@pytest.mark.parametrize("relative", ["docs/guides/template-updates.md", "docs/contributing/release-process.md"])
def test_raw_version_guidance_needs_no_template_rendering(relative):
    markdown = (ROOT / relative).read_text()
    assert "{{ project_version }}" not in markdown
    assert "make version" in markdown


def test_tool_reference_matches_registered_browser_tools(built_documentation):
    documented = set()
    pages = sorted((ROOT / "docs" / "tools-reference").glob("*.md"))
    assert len(pages) == 10
    for page in pages:
        names = re.findall(r"^## (browser_\w+)", page.read_text(), flags=re.MULTILINE)
        html = (built_documentation / "tools-reference" / page.stem / "index.html").read_text()
        for name in names:
            assert f'id="{name}"' in html
        documented.update(names)
    registered = set()
    for module in (ROOT / "src" / "justpen_browser_mcp" / "tools").glob("*.py"):
        for node in ast.walk(ast.parse(module.read_text())):
            if isinstance(node, ast.AsyncFunctionDef) and any(
                isinstance(decorator, ast.Attribute)
                and isinstance(decorator.value, ast.Name)
                and decorator.value.id == "mcp"
                and decorator.attr == "tool"
                for decorator in node.decorator_list
            ):
                registered.add(node.name)
    assert len(documented) == 43
    assert documented == registered


def test_original_product_pages_and_anchors_are_preserved(built_documentation):
    navigation = (ROOT / "mkdocs.yml").read_text()
    assert len(LEGACY_ANCHORS) == 24
    for source, anchors in LEGACY_ANCHORS.items():
        assert source in navigation
        output = Path("index.html") if source == "index.md" else Path(source).with_suffix("") / "index.html"
        html = (built_documentation / output).read_text()
        for anchor in ["_top", *anchors]:
            assert f'id="{anchor}"' in html, (source, anchor)
    for asset in ("assets/logo.svg", "assets/favicon.svg", "assets/custom.css", "favicon.svg"):
        assert (built_documentation / asset).is_file()


# Published Starlight page paths and heading IDs retained by the MkDocs migration.
LEGACY_ANCHORS = {
    "client-setup/claude-code.md": [
        "prerequisites",
        "registration",
        "running-outside-the-install-venv",
        "sanity-check",
        "common-pitfalls",
        "reference",
    ],
    "client-setup/copilot-cli.md": [
        "prerequisites",
        "registration",
        "running-outside-the-install-venv",
        "sanity-check",
        "common-pitfalls",
        "reference",
    ],
    "client-setup/gemini-cli.md": [
        "prerequisites",
        "registration",
        "running-outside-the-install-venv",
        "sanity-check",
        "common-pitfalls",
        "reference",
    ],
    "concepts/instances-isolation.md": [
        "why-instances-matter",
        "isolation-boundaries",
        "naming",
        "ephemeral-vs-persistent",
        "instance-cap",
        "crash-detection",
        "idle-reaper",
        "why-this-is-stronger-than-a-shared-process-model",
        "lifecycle-tools",
        "single-active-page-assumption",
    ],
    "concepts/modal-state.md": [
        "how-modal-state-is-tracked",
        "recovering-from-unexpected-modals",
        "gotcha-a-dialog-triggering-click-can-hold-the-lock-for-30s",
    ],
    "concepts/refs-snapshots.md": [
        "how-a-ref-is-captured",
        "how-a-ref-is-resolved-back-to-an-element",
        "resolving-a-ref-to-a-durable-selector",
        "iframe--child-frame-refs",
        "when-tools-require-a-ref",
        "why-aria-refs-instead-of-css-selectors",
        "recovering-from-stale-refs",
    ],
    "concepts/response-envelope.md": ["success", "error", "error_type-values"],
    "contributing/getting-started.md": [
        "prerequisites",
        "clone-and-set-up",
        "the-dev-gate",
        "end-to-end-tests",
        "make-a-change",
    ],
    "contributing/lint-typing.md": ["suppressions", "git-hooks"],
    "contributing/pr-checklist.md": [
        "1-branch-and-commits",
        "2-local-verification",
        "3-tests",
        "4-documentation",
        "5-opening-the-pr",
    ],
    "getting-started/configuration.md": [
        "environment-variables-and-cli-flags",
        "precedence",
        "instance-cap",
        "log-level",
    ],
    "getting-started/install.md": ["prerequisites", "install-from-git", "install-from-a-clone-contributors", "verify"],
    "getting-started/run-server.md": [
        "invocation-forms",
        "transport",
        "server-identity",
        "running-outside-the-install-venv",
        "logs",
        "next-steps",
    ],
    "index.md": ["60-second-quickstart", "where-to-go-next"],
    "tools-reference/code-execution.md": ["browser_evaluate", "browser_run_code"],
    "tools-reference/cookies.md": [
        "browser_get_cookies",
        "browser_set_cookies",
        "browser_clear_cookies",
        "browser_get_local_storage",
        "browser_set_local_storage",
        "browser_clear_local_storage",
    ],
    "tools-reference/inspection.md": [
        "browser_snapshot",
        "browser_screenshot",
        "browser_console_messages",
        "browser_network_requests",
    ],
    "tools-reference/interaction.md": [
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_select_option",
        "browser_hover",
        "browser_drag",
        "browser_press_key",
        "browser_file_upload",
        "browser_handle_dialog",
    ],
    "tools-reference/lifecycle.md": [
        "browser_create_instance",
        "browser_destroy_instance",
        "browser_list_instances",
        "browser_health",
    ],
    "tools-reference/mouse.md": [
        "browser_mouse_click_xy",
        "browser_mouse_move_xy",
        "browser_mouse_down",
        "browser_mouse_up",
        "browser_mouse_drag_xy",
        "browser_mouse_wheel",
    ],
    "tools-reference/navigation.md": ["browser_navigate", "browser_navigate_back", "browser_wait_for"],
    "tools-reference/page.md": ["browser_close"],
    "tools-reference/utility.md": ["browser_resize", "browser_pdf_save", "browser_generate_locator", "browser_tabs"],
    "tools-reference/verification.md": [
        "browser_verify_element_visible",
        "browser_verify_list_visible",
        "browser_verify_text_visible",
        "browser_verify_value",
    ],
}


@pytest.mark.parametrize("metadata", [None, '[project]\nversion = ""\n'])
def test_documentation_rejects_missing_or_empty_version(documentation_project, metadata):
    project_file = documentation_project / "pyproject.toml"
    if metadata is None:
        project_file.unlink()
    else:
        project_file.write_text(metadata)
    result = build_documentation(documentation_project)
    assert result.returncode != 0, result.stdout + result.stderr
