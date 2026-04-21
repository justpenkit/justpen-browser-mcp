# Pre-PR checklist

Run through this list before opening a pull request. The goal is to keep the
review cycle short: an hour spent on the checklist saves a day of back-and-forth.

## 1. Branch and commits

- [ ] Branch name follows `type/short-description`. The `type` uses the same
      set as commit types below.
- [ ] Each commit subject uses [Conventional Commits](https://www.conventionalcommits.org/):
      `type(scope): subject`. Scope is optional when the change is cross-cutting.
      Allowed types (enforced by `scripts/hooks/check_conventional_commit.py`):
      `feat`, `fix`, `docs`, `chore`, `ci`, `refactor`, `test`, `style`,
      `build`, `perf`, `revert`. Subject ≤72 characters, no trailing period.
- [ ] History is already the shape you want merged. We merge with real merge
      commits (never squash), so the SHAs on the feature branch are what lands
      on `main`. Rebase or `git commit --amend` locally before opening the PR if
      needed.

## 2. Local verification

All of these must pass on the branch tip.

```bash
make check       # ruff format-check + ruff check + pyright + pytest
make docs-build  # mkdocs build --strict (fails on broken links / nav)
```

`make check` is the minimum gate. If you touched anything under `docs/`,
also run `make docs-build` — the strict flag will catch broken cross-links
and missing nav entries.

If a tool reports something you think is a false positive, open an issue or
add a targeted suppression with a comment explaining why (see
[lint-typing.md](lint-typing.md) for the suppression protocol).

## 3. Tests

- [ ] New behaviour is covered by a test.
- [ ] Bugs fixed come with a regression test that fails on the old code and
      passes on the new code.
- [ ] `pytest -m "not e2e"` (which `make check` runs) is green.
- [ ] If the change interacts with a real browser, `make test-e2e` has been
      run locally at least once.

## 4. Documentation

- [ ] Public-facing behaviour changes are reflected in the relevant doc under
      `docs/`.
- [ ] If the change touches the release or contribution flow itself, the docs
      here (`pr-checklist.md`, `release-process.md`) and `CLAUDE.md` are in
      sync with reality.

## 5. Opening the PR

- [ ] PR title mirrors the Conventional Commit subject of the main change.
- [ ] Description covers: what changed, why, how it was tested, and any
      follow-ups being deliberately deferred.
- [ ] Linked issues / discussions are referenced.
- [ ] CI is green on the PR branch before requesting review.

## 6. Merging

- [ ] Use the **Create a merge commit** button — never **Squash and merge**.
      We preserve individual commit SHAs so any locally-created tags on the
      branch (e.g. version bump tags) stay valid after the merge.
