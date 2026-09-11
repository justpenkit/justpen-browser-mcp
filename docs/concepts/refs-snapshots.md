---
description: Session-scoped refs from accessibility snapshots and how they are invalidated.
---

# Refs & snapshots { #_top }

Most interaction tools consume a `ref` string (e.g. `"e12"`) obtained from `browser_snapshot`. Refs are annotated in the snapshot YAML as `[ref=eN]` on each interactive element, for example:

```
button "Submit" [ref=e12]
textbox "Email" [ref=e7]
```

They are session-scoped and invalidated by any navigation or page reload — always take a fresh snapshot after navigating.

When `browser_snapshot` is called with `selector=<css-or-aria>`, it returns a scoped aria YAML **without** ref annotations (using `Locator.aria_snapshot`). Use the default `selector=None` mode when you need refs for subsequent interaction tools — **selector-scoped snapshots omit refs entirely**, so they are for read-only inspection of a known subtree, not for driving follow-up interactions.

## How a ref is captured { #how-a-ref-is-captured }

The full-page (`selector=None`) snapshot uses Playwright's internal
`Frame.ariaSnapshot` protocol method with `mode="ai"` on the main frame.
The pinned Playwright 1.59 driver exposes this AI mode through its private
protocol, so `_playwright_internal.py` centralizes the channel access.
`ref_resolver.py` calls that facade to obtain the ref-annotated YAML.

## How a ref is resolved back to an element { #how-a-ref-is-resolved-back-to-an-element }

Interaction tools resolve a `ref` to a Playwright `Locator` via
`page.locator(f"aria-ref={ref}")` — the standard, public `aria-ref` selector
engine, which is unaffected by the private snapshot call above. If the
ref no longer matches any element (stale — see below), resolution raises
`StaleRefError`.

## Resolving a ref to a durable selector { #resolving-a-ref-to-a-durable-selector }

`browser_generate_locator` converts an ephemeral ref into a reusable selector, using Playwright's `resolveSelector` protocol method.
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
Complex selectors retain every filter, index and frame boundary using a lossless
`locator(...)` expression when a simpler Python call cannot represent them. Reuse
still depends on the page structure and accessible attributes remaining compatible.
See [`browser_generate_locator`](../tools-reference/utility.md#browser_generate_locator)
for the full parameter and error reference.

## iframe / child-frame refs { #iframe--child-frame-refs }

Snapshot refs may include a frame-qualified prefix, such as `f1e2`. The pinned
Playwright driver's `aria-ref` engine can resolve these refs through child frames;
ordinary interaction tools therefore work with native frame-qualified refs too.
Verification also includes a child-frame fallback for a ref that is not found by
the main-frame path. Keep the complete ref string returned by the snapshot.

Generated selectors preserve `internal:control=enter-frame` segments. The Python
representation retains that full selector when translating individual components
would lose frame boundaries or other selection constraints. A reusable selector
still needs matching frames and DOM structure in the future session.

## When tools require a ref { #when-tools-require-a-ref }

Interaction tools (click, hover, fill, drag) operate on **refs** — opaque
identifiers returned by inspection tools (see
[Inspection tools](../tools-reference/inspection.md)). A ref is valid for the
lifetime of the snapshot it came from; re-snapshot if the page mutates.

## Why aria-refs instead of CSS selectors { #why-aria-refs-instead-of-css-selectors }

- CSS selectors break on DOM churn; aria-refs target accessibility tree nodes.
- LLM clients produce more reliable calls against role + accessible-name than
    against brittle class hashes.

## Recovering from stale refs { #recovering-from-stale-refs }

If a tool returns `error_type: "stale_ref"`, re-run the relevant inspection
tool and retry with the new ref.
