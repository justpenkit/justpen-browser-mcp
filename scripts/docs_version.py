"""Render installation pins from the application's canonical project metadata."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.pages import Page


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Read the project version beside mkdocs.yml, including in preview copies."""
    metadata_path = Path(config.config_file_path).parent / "pyproject.toml"
    with metadata_path.open("rb") as metadata_file:
        project = tomllib.load(metadata_file)["project"]
    version = project["version"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("project.version must be a non-empty string")
    config.extra["project_version"] = version
    config.extra["project_name"] = project["name"]
    return config


def on_page_markdown(markdown: str, *, config: MkDocsConfig, page: Page, **_kwargs: object) -> str:
    """Render the two installation pages' concrete pins from project metadata."""
    if page.file.src_uri not in {"index.md", "getting-started/install.md"}:
        return markdown
    # on_config validates this value before MkDocs renders any pages.
    version = cast("str", config.extra["project_version"])
    name = re.escape(cast("str", config.extra["project_name"]))
    install_pin = rf"(?P<source>(?<![\w.-]){name} @ git\+\S+/{name}@v)\d+\.\d+\.\d+(?![\w.+-])"
    return re.sub(install_pin, lambda match: match["source"] + version, markdown)
