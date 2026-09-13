"""Static instance/page headers generated from existing MCP identities."""

from urllib.parse import quote


def instance_headers(name: str, instance_id: str) -> dict[str, str]:
    """Build context headers with an HTTP-safe reversible instance name."""
    return {
        "Justpen-Browser-Metadata-Instance-Name": quote(name, safe="-._~"),
        "Justpen-Browser-Metadata-Instance-ID": instance_id,
    }


def page_headers(page_id: str) -> dict[str, str]:
    """Build page-specific headers; Playwright merges these with context headers."""
    return {"Justpen-Browser-Metadata-Page-ID": page_id}
