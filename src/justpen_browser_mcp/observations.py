"""Request-local event observers armed before a browser action executes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal

from playwright.async_api import Error as PlaywrightError

from .observation_models import ElementWait, ResponseWait, TextWait, UrlWait
from .responses import success_response

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from playwright.async_api import Download, Frame, Page, Request, Response

    from .instance_manager import InstanceManager
    from .observation_models import WaitForSpec


PageEvent = Literal["close", "crash", "request", "response", "requestfailed", "framenavigated", "popup", "download"]


class ObservationTerminatedError(Exception):
    """The selected page closed or crashed before observation completed."""


class DownloadUnavailableError(Exception):
    """The emitted download could not be retained."""


class ActionObserver:
    """Capture only relevant events during one action and its bounded wait."""

    def __init__(
        self,
        page: Page,
        scope: Frame,
        spec: WaitForSpec,
        manager: InstanceManager,
        instance: str,
        *,
        explicit_frame: bool,
    ) -> None:
        """Bind an observation to an already validated page and frame."""
        self.page = page
        self.scope = scope
        self.spec = spec
        self.manager = manager
        self.instance = instance
        self.explicit_frame = explicit_frame
        self._listeners: list[tuple[PageEvent, Callable[..., None]]] = []
        self._requests: dict[int, Request] = {}
        self._future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiter: asyncio.Task[dict[str, Any]] | None = None
        self._closed = False

    def _listen(self, event: PageEvent, callback: Callable[..., None]) -> None:
        self.page.on(event, callback)
        self._listeners.append((event, callback))

    def arm(self) -> None:
        """Synchronously subscribe before any action side effect."""
        self._listen("close", self._terminated)
        self._listen("crash", self._terminated)
        if self.spec.kind == "response":
            self._listen("request", self._request)
            self._listen("response", self._response)
            self._listen("requestfailed", self._request_failed)
        elif self.spec.kind == "url":
            self._listen("framenavigated", self._navigation)
        elif self.spec.kind == "popup":
            self._listen("popup", self._popup)
        elif self.spec.kind == "download":
            self._listen("download", self._download)

    def _finish(self, facts: dict[str, Any]) -> None:
        if not self._closed and not self._future.done():
            self._future.set_result({"kind": self.spec.kind, "matched": True, **facts})

    def _terminated(self, _page: Page) -> None:
        if not self._closed and not self._future.done():
            self._future.set_exception(ObservationTerminatedError("Observed page closed or crashed"))

    def _request(self, request: Request) -> None:
        spec = self.spec
        if self._closed or self._future.done() or not isinstance(spec, ResponseWait):
            return
        if request.url != spec.url or (spec.method is not None and request.method.upper() != spec.method):
            return
        try:
            frame = request.frame
        except PlaywrightError:
            return
        if frame.page is self.page and (not self.explicit_frame or frame is self.scope):
            self._requests[id(request)] = request

    def _request_failed(self, request: Request) -> None:
        self._requests.pop(id(request), None)

    def _response(self, response: Response) -> None:
        request = self._requests.pop(id(response.request), None)
        spec = self.spec
        if request is None or not isinstance(spec, ResponseWait):
            return
        if response.url != spec.url or (spec.status is not None and response.status != spec.status):
            return
        entry = self.manager.state(self.instance).network_request_index.get(id(request))
        self._finish(
            {
                "url": response.url,
                "method": request.method,
                "status": response.status,
                "page_id": self.manager.page_id(self.instance, self.page),
                "frame_id": self.manager.frame_id(self.instance, request.frame),
                "request_id": entry["request_id"] if entry is not None else None,
            }
        )

    def _navigation(self, frame: Frame) -> None:
        if isinstance(self.spec, UrlWait) and frame is self.scope and frame.url == self.spec.url:
            self._finish(
                {
                    "url": frame.url,
                    "page_id": self.manager.page_id(self.instance, self.page),
                    "frame_id": self.manager.frame_id(self.instance, frame),
                }
            )

    def _popup(self, page: Page) -> None:
        if not self._closed and not self._future.done():
            self._finish({"page_id": self.manager.page_id(self.instance, page)})

    def _download(self, download: Download) -> None:
        if self._closed or self._future.done():
            return
        download_id = self.manager.state(self.instance).downloads.id_for(download)
        if download_id is None:
            self._future.set_exception(DownloadUnavailableError("Download handle is unavailable"))
        else:
            self._finish({"download_id": download_id, "suggested_filename": download.suggested_filename})

    async def _postcondition(self) -> dict[str, Any]:
        spec = self.spec
        if isinstance(spec, ElementWait):
            await self.scope.locator(spec.selector).wait_for(state=spec.state, timeout=0)
            return {"kind": spec.kind, "matched": True, "selector": spec.selector, "state": spec.state}
        if isinstance(spec, TextWait):
            visible = self.scope.get_by_text(spec.text).filter(visible=True)
            await visible.first.wait_for(state="visible" if spec.state == "visible" else "hidden", timeout=0)
            return {"kind": spec.kind, "matched": True, "text": spec.text, "state": spec.state}
        raise TypeError("Expected an element or text postcondition")

    async def wait(self) -> dict[str, Any]:
        """Start state-based waits only after the action has returned."""
        if isinstance(self.spec, (ElementWait, TextWait)):
            self._waiter = asyncio.create_task(self._postcondition())
            await asyncio.wait((self._waiter, self._future), return_when=asyncio.FIRST_COMPLETED)
            if self._future.done():
                return self._future.result()
            return self._waiter.result()
        return await self._future

    async def aclose(self) -> None:
        """Detach listeners, release request references, and drain owned tasks."""
        self._closed = True
        for event, callback in self._listeners:
            self.page.remove_listener(event, callback)
        self._listeners.clear()
        self._requests.clear()
        if self._waiter is not None:
            self._waiter.cancel()
            await asyncio.gather(self._waiter, return_exceptions=True)
        if self._future.done() and not self._future.cancelled():
            self._future.exception()
        else:
            self._future.cancel()


async def run_observed_action(
    instance: str,
    manager: InstanceManager,
    page: Page,
    scope: Frame,
    action: Callable[[], Awaitable[dict[str, Any]]],
    wait_for: WaitForSpec | None,
    *,
    explicit_frame: bool = False,
    on_action_completed: Callable[[dict[str, Any], str], None] | None = None,
) -> dict[str, Any]:
    """Run the existing action once and append truthful completion facts."""
    if wait_for is None:
        return success_response(instance, await action())
    observer = ActionObserver(page, scope, wait_for, manager, instance, explicit_frame=explicit_frame)
    try:
        observer.arm()
        result = await action()
        if on_action_completed is not None:
            on_action_completed(result, wait_for.kind)
        data = {**result, "action_completed": True}
        try:
            async with asyncio.timeout(wait_for.timeout_ms / 1000):
                data["observation"] = await observer.wait()
        except (TimeoutError, ObservationTerminatedError, DownloadUnavailableError) as error:
            error_type = (
                "observation_timeout"
                if isinstance(error, TimeoutError)
                else "download_not_found"
                if isinstance(error, DownloadUnavailableError)
                else "internal_error"
            )
            data["observation"] = {"kind": wait_for.kind, "matched": False}
            return {
                "status": "error",
                "instance": instance,
                "error_type": error_type,
                "message": str(error) or "Action completed but its observation timed out",
                "data": data,
            }
        return success_response(instance, data)
    finally:
        await observer.aclose()
