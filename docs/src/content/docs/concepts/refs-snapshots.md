---
title: Refs & snapshots
description: Session-scoped refs from accessibility snapshots and how they are invalidated.
---

Most interaction tools consume a `ref` string (e.g. `"e12"`) obtained from `browser_snapshot`. Refs are annotated in the snapshot YAML as `[ref=eN]` on each interactive element, for example:

```
button "Submit" [ref=e12]
textbox "Email" [ref=e7]
```

They are session-scoped and invalidated by any navigation or page reload — always take a fresh snapshot after navigating.

When `browser_snapshot` is called with `selector=<css-or-aria>`, it returns a scoped aria YAML **without** ref annotations (using `Locator.aria_snapshot`). Use the default `selector=None` mode when you need refs for subsequent interaction tools — **selector-scoped snapshots omit refs entirely**, so they are for read-only inspection of a known subtree, not for driving follow-up interactions.

## How a ref is captured

The full-page (`selector=None`) snapshot is captured via Playwright's internal
`snapshotForAI` protocol method. The Python high-level API does not expose
this method (as of Playwright 1.58), so the server calls the underlying
protocol channel directly (`page._impl_obj._channel.send("snapshotForAI", ...)`)
— see [microsoft/playwright-python#2867](https://github.com/microsoft/playwright-python/issues/2867)
for the upstream tracking issue. This workaround lives in one place
(`ref_resolver.py`) rather than being scattered across tools.

## How a ref is resolved back to an element

Interaction tools resolve a `ref` to a Playwright `Locator` via
`page.locator(f"aria-ref={ref}")` — the standard, public `aria-ref` selector
engine, which is unaffected by the `snapshotForAI` workaround above. If the
ref no longer matches any element (stale — see below), resolution raises
`StaleRefError`.

## Resolving a ref to a durable selector

`browser_generate_locator` converts an ephemeral ref into a selector that
survives navigation, using Playwright's `resolveSelector` protocol method.
The resolution follows a priority ladder (`ref_resolver._internal_to_python`
mirrors this order when producing the Python-syntax form):

1. `data-testid` (highest priority)
2. ARIA role + accessible name
3. Label
4. Placeholder
5. Alt text
6. Title
7. Text content
8. CSS selector (fallback when nothing more specific matches)

The tool returns two representations: `internal_selector` (a raw Playwright
engine selector, e.g. `internal:role=button[name="Submit"i]`, usable directly
with `page.locator()`) and `python_syntax` (the equivalent Python API call,
e.g. `get_by_role("button", name='Submit')`, intended for codegen/test output).
See [`browser_generate_locator`](/tools-reference/utility/#browser_generate_locator)
for the full parameter and error reference.

## iframe / child-frame refs

Plain `resolve_ref` (used by `browser_click`, `browser_evaluate`, etc.) builds
its locator via `page.locator(f"aria-ref={ref}")`, which only searches the
main frame's selector-engine path — it does not descend into `<iframe>`
content on its own.

Verification tools go further: `_resolve_ref_in_any_frame` first tries the
main frame and, if that raises `StaleRefError`, falls back to trying
`frame.locator(f"aria-ref={ref}")` against each child frame of the page in
turn, only raising `StaleRefError` itself if no frame (main or child)
resolves the ref. This is what lets `verify_element_visible`,
`verify_text_visible`, and similar checks work against elements inside
iframes without extra caller-side frame bookkeeping.

Separately, when `browser_generate_locator` resolves a ref that lives inside
a nested iframe, the underlying `resolveSelector` protocol call can return an
internal selector containing `... >> internal:control=enter-frame >> ...`
segments — one per frame boundary crossed. `_internal_to_python` recognizes
this shape and translates it into chained `.content_frame.` calls in the
`python_syntax` output, so a saved locator still resolves correctly through
the same frame chain when replayed in a future session.

## When tools require a ref

Interaction tools (click, hover, fill, drag) operate on **refs** — opaque
identifiers returned by inspection tools (see
[Inspection tools](/tools-reference/inspection/)). A ref is valid for the
lifetime of the snapshot it came from; re-snapshot if the page mutates.

## Why aria-refs instead of CSS selectors

- CSS selectors break on DOM churn; aria-refs target accessibility tree nodes.
- LLM clients produce more reliable calls against role + accessible-name than
  against brittle class hashes.

## Recovering from stale refs

If a tool returns `error_type: "stale_ref"`, re-run the relevant inspection
tool and retry with the new ref.
