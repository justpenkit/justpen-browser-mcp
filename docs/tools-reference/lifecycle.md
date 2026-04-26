# Lifecycle tools

Lifecycle tools manage the full lifespan of browser instances — creating isolated sessions, querying what is alive, and tearing sessions down cleanly. Reach for these tools at the boundaries of a workflow: `browser_create_instance` to open a session, `browser_list_instances` to inspect what is currently active, and `browser_destroy_instance` to shut everything down when the work is done.

## browser_create_instance

Create a new isolated Camoufox browser instance with its own process and BrowserForge fingerprint.

**Signature**

```python
async def browser_create_instance(
    name: str,
    *,
    profile_dir: str | None = None,
    headless: bool | Literal["virtual"] = True,
    proxy: dict[str, str] | None = None,
    humanize: bool | float = True,
    window: tuple[int, int] | None = None,
) -> dict[str, Any]
```

**Parameters**

| Name          | Type                      | Default | Description                                                                                                                                                                                                      |
| ------------- | ------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`        | `str`                     | —       | Name for the new instance. Case-sensitive, must be unique across live instances.                                                                                                                                 |
| `profile_dir` | `str \| None`             | `None`  | Path to a persistent profile directory. `None` (default) creates an ephemeral instance with no on-disk trace. When a path is given and the directory already exists, Camoufox loads it; otherwise it is created. |
| `headless`    | `bool \| "virtual"`       | `True`  | `True` for headless mode (no visible window). `False` for a visible window. `"virtual"` uses a virtual framebuffer (Xvfb) on Linux.                                                                              |
| `proxy`       | `dict[str, str] \| None`  | `None`  | Proxy configuration dict. Accepted keys: `server` (required, e.g. `"socks5://host:port"`), `username`, `password`, `bypass`.                                                                                     |
| `humanize`    | `bool \| float`           | `True`  | Camoufox humanization level. `True` enables default humanization; `False` disables it; a float sets the delay factor directly.                                                                                   |
| `window`      | `tuple[int, int] \| None` | `None`  | Initial viewport size as `(width, height)`. `None` uses Camoufox defaults.                                                                                                                                       |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "name": "main",
  "mode": "ephemeral",
  "profile_dir": null,
  "page_count": 0,
  "active_url": null,
  "created_at": "2026-04-22T10:00:00+00:00"
}
```

`mode` is `"ephemeral"` when `profile_dir` is `None`, `"persistent"` otherwise.

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_already_exists` — an instance with that name is already live.
- `instance_limit_exceeded` — the `BROWSER_MCP_MAX_INSTANCES` cap has been reached; destroy an existing instance first.
- `profile_dir_in_use` — another live instance is already using the requested `profile_dir`.

**Example**

Request:

```json
{ "name": "browser_create_instance", "arguments": { "name": "main" } }
```

Response:

```json
{
  "status": "success",
  "instance": "main",
  "data": {
    "name": "main",
    "mode": "ephemeral",
    "profile_dir": null,
    "page_count": 0,
    "active_url": null,
    "created_at": "2026-04-22T10:00:00+00:00"
  }
}
```

**Notes** — No pages exist immediately after creation. The first tool that needs a page (e.g. `browser_navigate`) creates one implicitly. For persistent instances, BrowserForge rolls a fresh fingerprint on each launch even when reusing an existing `profile_dir` — stored cookies and localStorage are preserved, but the fingerprint signals change. See [Instances & isolation](../concepts/instances-isolation.md) for a full discussion of ephemeral vs. persistent modes.

## browser_destroy_instance

Shut down an instance and free all its resources.

**Signature**

```python
async def browser_destroy_instance(name: str) -> dict[str, Any]
```

**Parameters**

| Name   | Type  | Default | Description    |
| ------ | ----- | ------- | -------------- |
| `name` | `str` | —       | Instance name. |

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` is an empty object (`{}`).

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `instance_not_found` — no instance with that name is currently live.

**Example**

Request:

```json
{ "name": "browser_destroy_instance", "arguments": { "name": "main" } }
```

Response:

```json
{ "status": "success", "instance": "main", "data": {} }
```

**Notes** — Camoufox is terminated and all in-memory browser state is discarded. If the instance was created with a `profile_dir`, that directory and its contents are left intact on disk — the profile survives for the next `browser_create_instance` call. To close a single tab while keeping the instance alive, use `browser_close` instead.

## browser_list_instances

Return summaries of all currently live instances.

**Signature**

```python
async def browser_list_instances() -> dict[str, Any]
```

**Parameters**

_No parameters._

**Returns** — see [response envelope](../concepts/response-envelope.md). `data` shape:

```json
{
  "instances": [
    {
      "name": "main",
      "mode": "ephemeral",
      "profile_dir": null,
      "page_count": 1,
      "active_url": "https://example.com",
      "created_at": "2026-04-22T10:00:00+00:00"
    }
  ]
}
```

Each entry in `instances` has:

| Field         | Type          | Description                                                                |
| ------------- | ------------- | -------------------------------------------------------------------------- |
| `name`        | `str`         | Instance name.                                                             |
| `mode`        | `str`         | `"ephemeral"` or `"persistent"`.                                           |
| `profile_dir` | `str \| null` | Absolute path to the profile directory, or `null` for ephemeral instances. |
| `page_count`  | `int`         | Number of open tabs in the instance.                                       |
| `active_url`  | `str \| null` | URL of the currently active page, or `null` when no pages are open.        |
| `created_at`  | `str`         | ISO 8601 timestamp (UTC) of when the instance was created.                 |

**Errors** — emits `error_type` codes (see [envelope error codes](../concepts/response-envelope.md#error_type-values)):

- `internal_error`

**Example**

Request:

```json
{ "name": "browser_list_instances", "arguments": {} }
```

Response:

```json
{
  "status": "success",
  "instance": null,
  "data": {
    "instances": [
      {
        "name": "main",
        "mode": "ephemeral",
        "profile_dir": null,
        "page_count": 2,
        "active_url": "https://example.com",
        "created_at": "2026-04-22T10:00:00+00:00"
      }
    ]
  }
}
```

**Notes** — Never raises a domain error — if no instances exist the list is empty. `instance` in the envelope is `null` because this is a server-level tool that does not target a specific instance.
