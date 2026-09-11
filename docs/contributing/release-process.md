# Release process

This project releases from `main`. Create a version bump on a feature branch,
merge its PR, then create and push the annotated tag to create the GitHub Release.
The sequence is identical for patch, minor and major bumps.

## Versioning policy

We follow [Semantic Versioning 2.0](https://semver.org/). Run `make version` to read
the current application version. During `0.x`, minor bumps may include breaking
changes, as SemVer permits for initial development. The template has its own
version; adopting or updating its framework does not bump or reset this server.

## Tooling

Use `make changelog` to generate `CHANGELOG.md` from Conventional Commits with
Commitizen. This established application retains its actual `0.1.0` through
`0.4.0` release history. Its changelog boundary follows the real application
history; the later Copier enrollment is not the application's first release.
Preserve that boundary and the existing tags during template updates.
The explicit `changelog_start_rev = ""` setting under `[tool.commitizen]` keeps
the full genuine application history; do not replace it with the enrollment commit.

Each `make bump-{patch,minor,major}` target:

1. Requires a clean working tree on a feature branch, not `main`, `master` or a
    detached checkout.
2. Calls `uv version --bump <segment>` to update `pyproject.toml` and `uv.lock`.
3. Updates the installation pins in `README.md`, `docs/index.md`, and
    `docs/getting-started/install.md`, generates the changelog with Commitizen,
    and formats `CHANGELOG.md` with mdformat. The website reads the version from
    project metadata during its MkDocs build.
4. Commits the release changes with the normal Git hooks enabled.
5. Leaves tag creation to `make release-tag` after the reviewed PR merges.

Every failed step stops the command. Inspect the reported error and working
tree before retrying; formatting and hook changes are not silently discarded.
The command never pushes tags or publishes to PyPI.

For coding agents, ordinary uv-managed version changes remain allowed. The
complete release operation also commits and eventually tags, so it requires release
authorization and is not an automatic dependency-management exemption.

## Step-by-step flow

Start with a clean working tree and an up-to-date `main`.

### 1. Create the release branch

```bash
git switch main
git pull
git switch -c chore/bump-v<new-version>
```

Choose `<new-version>` from the current version (`make version`) and intended
segment. Codex uses `codex/bump-v<new-version>` for its feature branch.

### 2. Bump

```bash
make bump-patch     # or bump-minor, or bump-major
```

Review the resulting metadata, lockfile and changelog. The command creates the
bump commit locally. If you chose the wrong segment, inspect the unpushed commit
and agree on a correction before changing history.

### 3. Push the branch only

```bash
git push -u origin chore/bump-v<new-version>
```

Use the branch name you created. Create the tag after the PR merges so it includes
all changes made during review. An early tag is rejected if unmerged or if its
contents differ from the reviewed merge.

### 4. Open and merge the PR

- Title: `chore: bump version to v<new-version>`.
- Complete the [PR checklist](pr-checklist.md), including `make check` and
    `make docs-build`.
- Review the changelog as the exact notes that will accompany this release.
- Merge with a regular merge commit, never squash. Release finalization tags this
    reviewed merge, including corrections committed after the version bump.

### 5. Create and push the reviewed tag

Once the PR is merged and its checks have passed, update `main` to the release
merge and finalize the tag before starting the next release:

```bash
git switch main
git pull --ff-only
make release-tag
git push origin v<new-version>
```

`make release-tag` requires a clean `main` at the same commit as `origin/main`,
a regular merge commit, a matching changelog section, and an unused tag name.
It never moves an existing tag or publishes anything itself. If more work has
already landed on main, inspect the intended release contents before finalizing.

### 6. Automatic GitHub Release

The tag-triggered workflow verifies that the tag is annotated, matches the
version in `pyproject.toml`, and points to a commit contained in `origin/main`.
A tag on a feature-branch commit is accepted only when its tree is identical to
its first reviewed integration into main; this preserves valid historical tags
while rejecting tags that omit PR review corrections.
It takes the corresponding section from `CHANGELOG.md` and creates the GitHub
Release. A rerun keeps an already-created release instead of duplicating it.

Inspect the workflow result in Actions and the release notes in GitHub Releases.
This automation creates the GitHub Release only; package-index publishing is
not configured.
