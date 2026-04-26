---
title: Navigation
description: Navigate, reload, go back/forward, and open URLs.
---

Navigation tools control where the active page points and how long the agent waits before proceeding. Use `browser_navigate` to load a URL into the current tab, `browser_navigate_back` to step back through browser history, and `browser_wait_for` to pause until a piece of text appears, disappears, or a fixed delay expires. Reach for these tools any time you need to move between pages, handle redirect flows, or synchronise with dynamic content that takes time to render.

## browser_navigate

Navigate the active page in the given instance to a URL.

**Signature**

```python
async def browser_navigate(instance: str, url: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description      |
| ---------- | ----- | ------- | ---------------- |
| `instance` | `str` | —       | Instance name.   |
| `url`      | `str` | —       | Destination URL. |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "url": "https://example.com/page", "title": "Page Title" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `navigation_failed`
- `navigation_timeout`

**Example**

Request:

```json
{ "name": "browser_navigate", "arguments": { "instance": "main", "url": "https://example.com" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": { "url": "https://example.com/", "title": "Example Domain" }
}
```

**Notes** — URL normalisation: `localhost[:PORT]` and bare IPv4 addresses receive an `http://` scheme; schemeless hostnames containing a dot receive `https://`. When a download is triggered instead of a page load, the response data includes an extra `"download": true` field alongside `url` and `title`. After any successful navigation, refs obtained from `browser_snapshot` are invalidated — take a fresh snapshot before referencing page elements.

## browser_navigate_back

Navigate back one step in the browser history for the active page.

**Signature**

```python
async def browser_navigate_back(instance: str) -> dict[str, Any]
```

**Parameters**

| Name       | Type  | Default | Description    |
| ---------- | ----- | ------- | -------------- |
| `instance` | `str` | —       | Instance name. |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "url": "https://example.com/" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `navigation_failed`
- `navigation_timeout`

**Example**

Request:

```json
{ "name": "browser_navigate_back", "arguments": { "instance": "main" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "url": "https://example.com/" } }
```

**Notes** — If there is no history entry to go back to, the page stays where it is and the returned `url` reflects the current location. After a successful back-navigation, previous snapshot refs are invalidated.

## browser_wait_for

Wait for text to appear, text to disappear, or a fixed duration.

**Signature**

```python
async def browser_wait_for(
    instance: str,
    text: str | None = None,
    text_gone: str | None = None,
    time: float | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name        | Type            | Default | Description                                     |
| ----------- | --------------- | ------- | ----------------------------------------------- |
| `instance`  | `str`           | —       | Instance name.                                  |
| `text`      | `str \| None`   | `None`  | Wait until this string is visible on the page.  |
| `text_gone` | `str \| None`   | `None`  | Wait until this string is hidden on the page.   |
| `time`      | `float \| None` | `None`  | Seconds to wait unconditionally (capped at 30). |

**Returns** — see [response envelope](/concepts/response-envelope/). `data` shape:

```json
{ "waited_for": "2.0s, text='Dashboard'" }
```

**Errors** — emits `error_type` codes (see [envelope error codes](/concepts/response-envelope/#error_type-values)):

- `instance_not_found`
- `modal_state_blocked`
- `invalid_params`
- `wait_timeout`

**Example**

Request:

```json
{ "name": "browser_wait_for", "arguments": { "instance": "main", "text": "Dashboard" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": { "waited_for": "text='Dashboard'" } }
```

**Notes** — At least one of `text`, `text_gone`, or `time` must be provided; omitting all three returns an `invalid_params` error immediately. When multiple conditions are given they are evaluated in order: `time` first, then `text_gone`, then `text`.
