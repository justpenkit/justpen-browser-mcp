# Release process

This project ships versioned releases from `main` with a local tag that is
pushed after the release PR merges. The flow is identical for every segment
(patch, minor, major); only the segment name changes.

## Versioning policy

We follow [Semantic Versioning 2.0](https://semver.org/) once the project is
past `0.x`. During `0.x` we still use the same segment names but reserve the
right to break minor-to-minor, which SemVer allows for initial development.

- **patch** — bug fixes and docs-only changes that do not affect the public
  API or tool schema.
- **minor** — new tools, new options on existing tools, or behaviour changes
  that remain backwards compatible.
- **major** — removing a tool, renaming a tool parameter, or any change that
  an existing MCP client would notice as a breaking change.

## Tooling

Version bumps go through the `bump-*` Make targets. Each target:

1. Calls `uv version --bump <segment>`, which rewrites `version = "…"` in
   `pyproject.toml` and updates `uv.lock`.
2. Commits the change on the current branch.
3. Creates an annotated tag `v<new-version>` locally.
4. Prints the exact push commands you need to run next.

The tag is **not** pushed automatically — that is the final step of the
release flow, and only happens after the bump PR is merged into `main`.

## Step-by-step flow

All steps below assume a clean working tree and that `main` is up to date.

### 1. Create the release branch

```bash
git switch main
git pull
git switch -c chore/bump-v<new-version>
```

Pick `<new-version>` by knowing the current version (`make version`) and
the segment you intend to bump.

### 2. Bump

```bash
make bump-patch     # or bump-minor, or bump-major
```

This creates both the bump commit and the `v<new-version>` tag locally. The
target prints the next commands you need to run — follow them.

If something is wrong (e.g. you picked the wrong segment), you can still
fix it before pushing by resetting the branch and deleting the local tag:

```bash
git reset --hard HEAD~1
git tag -d v<wrong-version>
```

Then re-run the correct `make bump-*`.

### 3. Push the branch only

```bash
git push -u origin chore/bump-v<new-version>
```

Do **not** push the tag yet. Pushing the tag before the branch is merged
would create a tag that points at a commit on a feature branch — if the
branch gets rebased or the merge commit changes SHAs, the tag becomes
orphaned.

### 4. Open and merge the PR

- Title: `chore: bump version to v<new-version>`.
- Walk the [PR checklist](pr-checklist.md). `make check` and
  `make docs-build` must pass.
- Merge with a regular merge commit (never squash). Squashing changes the
  bump-commit SHA and orphans the local `v<new-version>` tag.

### 5. Push the tag

Once the PR is merged and `main` contains the bump commit:

```bash
git switch main
git pull
git push origin v<new-version>
```

Pushing the tag is what makes the release "real" — downstream tooling keys
off tags, not off the commit.

### 6. Create the GitHub Release (manual)

Go to **Releases → Draft a new release**, pick the tag you just pushed, and
fill in the release notes. For now we write these by hand from the commits
in the bump range (`git log v<prev>..v<new> --oneline`). A future change
may automate this step — see issue tracker.

## Why so many steps?

Each constraint exists because an earlier, simpler version of the process
bit us:

- **Tag after merge**, not before, because tags on pre-merge commits end up
  pointing at SHAs that no longer exist after a force-push or rebase.
- **Regular merge, not squash**, because squashing rewrites the bump commit
  SHA and orphans the locally-created tag.
- **Separate bump PR**, not bundled with feature work, because code review
  on a version bump should be a five-second affair — bundling it hides the
  bump under unrelated diffs and risks accidentally cutting a release off
  of unreviewed code.
