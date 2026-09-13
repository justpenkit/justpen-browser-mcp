"""Real-browser coverage for original screenshots and retained downloads."""

from __future__ import annotations

import asyncio
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anyio
import pytest
from PIL import Image
from typing_extensions import override

from .conftest import call

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]

DOWNLOAD_BYTES = (b"browser-download-evidence\n" * 4096) + b"complete"


@pytest.fixture
def artifact_site():
    release = threading.Event()
    transfer_started = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/file")
                self.end_headers()
                return
            if self.path == "/":
                body = b'<html><body><a href="/file">Download evidence</a></body></html>'
                self._send(body, "text/html")
                return
            if self.path == "/tall":
                body = (
                    b'<html><body style="margin:0"><div style="height:3100px;'
                    b'background:repeating-linear-gradient(#f00 0 3px,#00f 3px 6px)"></div></body></html>'
                )
                self._send(body, "text/html")
                return
            if self.path == "/delayed":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="delayed.bin"')
                self.send_header("Content-Length", str(len(DOWNLOAD_BYTES)))
                self.end_headers()
                split = len(DOWNLOAD_BYTES) // 2
                self.wfile.write(DOWNLOAD_BYTES[:split])
                self.wfile.flush()
                transfer_started.set()
                release.wait(timeout=15)
                self.wfile.write(DOWNLOAD_BYTES[split:])
                return
            if self.path == "/broken":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="broken.bin"')
                self.send_header("Content-Length", str(len(DOWNLOAD_BYTES)))
                self.end_headers()
                self.wfile.write(DOWNLOAD_BYTES[:100])
                self.wfile.flush()
                self.connection.shutdown(1)
                return
            self._send(DOWNLOAD_BYTES, "application/octet-stream", attachment="evidence.bin")

        def _send(self, body: bytes, content_type: str, attachment: str | None = None):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if attachment is not None:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(body)

        @override
        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", transfer_started, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("image_format", ["png", "jpeg"])
async def test_original_screenshot_preserves_tall_capture_and_preview_stays_bounded(
    e2e_client, artifact_site, tmp_path, image_format
):
    site, _, _ = artifact_site
    await call(e2e_client, "browser_create_instance", {"name": f"shot-{image_format}"})
    await call(
        e2e_client,
        "browser_navigate",
        {"instance": f"shot-{image_format}", "url": f"{site}/tall"},
    )
    preview = await call(
        e2e_client,
        "browser_screenshot",
        {"instance": f"shot-{image_format}", "image_format": image_format, "full_page": True},
    )
    target = tmp_path / f"original.{image_format}"
    original = await call(
        e2e_client,
        "browser_screenshot",
        {
            "instance": f"shot-{image_format}",
            "image_format": image_format,
            "full_page": True,
            "path": str(target),
            "original": True,
        },
    )

    assert max(preview["data"]["width"], preview["data"]["height"]) == 1568
    assert original["status"] == "success"
    assert original["data"]["original"] is True
    assert original["data"]["path"] == str(target)
    with Image.open(target) as image:
        assert image.size == (original["data"]["width"], original["data"]["height"])
        assert image.height >= 3000
        assert len({image.getpixel((0, y)) for y in range(12)}) > 1


async def test_navigation_and_click_downloads_share_retained_ids_and_save_exact_bytes(
    e2e_client, artifact_site, tmp_path
):
    site, _, _ = artifact_site
    await call(e2e_client, "browser_create_instance", {"name": "downloads"})
    direct = await call(e2e_client, "browser_navigate", {"instance": "downloads", "url": f"{site}/redirect"})
    direct_id = direct["data"]["download_id"]
    listed = await call(e2e_client, "browser_downloads", {"instance": "downloads"})
    assert any(item["download_id"] == direct_id for item in listed["data"]["downloads"])
    direct_path = tmp_path / "direct.bin"
    saved = await call(
        e2e_client,
        "browser_download_save",
        {"instance": "downloads", "download_id": direct_id, "path": str(direct_path)},
    )
    assert direct_path.read_bytes() == DOWNLOAD_BYTES
    assert saved["operation"]["artifacts"] == [{"path": str(direct_path)}]

    await call(e2e_client, "browser_navigate", {"instance": "downloads", "url": site})
    snapshot = await call(e2e_client, "browser_snapshot", {"instance": "downloads"})
    match = re.search(r'link "Download evidence" \[ref=(\w+)\]', snapshot["data"]["snapshot"])
    assert match is not None
    evaluated = await call(
        e2e_client,
        "browser_evaluate",
        {
            "instance": "downloads",
            "ref": match.group(1),
            "expression": "element => element.click()",
        },
    )
    assert evaluated["status"] == "success"
    await call(e2e_client, "browser_wait_for", {"instance": "downloads", "time": 0.1})
    after_click = await call(e2e_client, "browser_downloads", {"instance": "downloads"})
    click_id = next(
        item["download_id"] for item in after_click["data"]["downloads"] if item["download_id"] != direct_id
    )
    assert click_id != direct_id
    click_path = tmp_path / "clicked.bin"
    await call(
        e2e_client,
        "browser_download_save",
        {"instance": "downloads", "download_id": click_id, "path": str(click_path)},
    )
    assert click_path.read_bytes() == DOWNLOAD_BYTES


async def test_save_waits_for_transfer_and_old_id_does_not_survive_instance_recreation(
    e2e_client, artifact_site, tmp_path
):
    site, transfer_started, release = artifact_site
    profile = tmp_path / "profile"
    await call(
        e2e_client,
        "browser_create_instance",
        {"name": "persistent", "profile_dir": str(profile)},
    )
    navigated = await call(e2e_client, "browser_navigate", {"instance": "persistent", "url": f"{site}/delayed"})
    download_id = navigated["data"]["download_id"]
    await anyio.to_thread.run_sync(transfer_started.wait, 5)
    destination = tmp_path / "persisted.bin"
    saving = asyncio.create_task(
        call(
            e2e_client,
            "browser_download_save",
            {"instance": "persistent", "download_id": download_id, "path": str(destination)},
        )
    )
    await asyncio.sleep(0.1)
    assert not saving.done()
    release.set()
    result = await saving
    assert result["status"] == "success"
    assert destination.read_bytes() == DOWNLOAD_BYTES

    await call(e2e_client, "browser_destroy_instance", {"name": "persistent"})
    await call(
        e2e_client,
        "browser_create_instance",
        {"name": "persistent", "profile_dir": str(profile)},
    )
    missing = await call(
        e2e_client,
        "browser_download_save",
        {"instance": "persistent", "download_id": download_id, "path": str(tmp_path / "again.bin")},
    )
    assert missing["error_type"] == "download_not_found"
    assert destination.read_bytes() == DOWNLOAD_BYTES
