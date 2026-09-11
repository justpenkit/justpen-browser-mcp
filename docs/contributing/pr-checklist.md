# Pre-PR checklist { #_top }

Complete this checklist before opening a pull request.

## 1. Branch and commits { #1-branch-and-commits }

- Use `codex/short-description` for Codex branches, otherwise
    `type/short-description`. Never commit or push directly to `main`.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
    `type(scope): subject`, with optional scope, subject no longer than 72
    characters and no trailing period. The allowed types are `feat`, `fix`, `docs`,
    `chore`, `ci`, `refactor`, `test`, `style`, `build`, `perf`, and `revert`.
- Keep normal Git hooks enabled. Merge with a regular merge commit, never squash.

## 2. Local verification { #2-local-verification }

```bash
make check
make docs-build
```

`make check` covers lock consistency, Python and non-Python formatting, lint,
strict typing for Python 3.11–3.13 and the fast suite with coverage. The strict
MkDocs build validates local links and anchors as well as Python API references.
Run both gates before every PR; do not substitute direct tool invocations or
weaker flags.

## 3. Tests { #3-tests }

- Cover new behavior with focused tests and include regressions for bug fixes.
- Run `make test-e2e` locally when browser behavior changes. The fast gate
    excludes these tests and does not start Camoufox. See
    [End-to-end tests](getting-started.md#end-to-end-tests).
- If changing permission policy, run `make test-permissions` with an installed
    Codex CLI selected by `CODEX_TEST_BINARY`, following the
    [agent guide](agents.md#verify-and-troubleshoot).

## 4. Documentation { #4-documentation }

- Update the relevant product guides and tool references for user-facing behavior.
- Preserve existing page URLs and heading anchors when reorganizing content.
- Verify that versioned installation commands use the project's current version.
- Follow [Lint & typing](lint-typing.md) for formatting and the suppression policy.

## 5. Opening the PR { #5-opening-the-pr }

- Give the PR a Conventional Commit title.
- Explain the problem, resulting behavior and validation, with linked issues
    where relevant.
- Confirm that CI is green for the current PR revision before merging.
- For a release, follow the [release process](release-process.md): push the
    branch, merge the PR with a regular merge commit, then push the annotated tag.
