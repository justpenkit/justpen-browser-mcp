# Pre-PR checklist

Run through this list before opening a pull request. The goal is to keep the
review cycle short: an hour spent on the checklist saves a day of back-and-forth.

## 1. Branch and commits

- Branch name follows `type/short-description` (e.g. `feat/foo-bar`).
- Each commit uses [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): subject`. **Scope** is optional and freeform; **type** is
  enforced (by `scripts/hooks/check_conventional_commit.py`) to one of:
  `feat`, `fix`, `docs`, `chore`, `ci`, `refactor`, `test`, `style`,
  `build`, `perf`, `revert`. Subject ≤72 chars, no trailing period.
- History is the shape you want merged (we use real merge commits, never
  squash). Rebase or `--amend` locally before opening the PR.

## 2. Local verification

```bash
make check       # ruff format-check + prettier --check + ruff check + pyright + pytest
make docs-build  # mkdocs build --strict (fails on broken links / nav)
```

`make check` is the minimum gate; covers Python (ruff) and non-Python
(prettier — md/yml/json/toml). If you touched anything under `docs/`,
also run `make docs-build`. The `--strict` flag will catch broken
cross-links and missing nav entries.

## 3. Tests

- New behaviour is covered by a test.
- Bugs come with a regression test that fails on the old code and passes
  on the new code.

## 4. Documentation

- Public-facing behaviour changes are reflected in the relevant doc under
  `docs/`.

## 5. Opening the PR

- PR title mirrors the Conventional Commit subject of the main change.
- Description covers: what changed, why, how it was tested, and any
  follow-ups being deliberately deferred.
- Linked issues / discussions are referenced.
- CI is green on the PR branch before requesting review.
