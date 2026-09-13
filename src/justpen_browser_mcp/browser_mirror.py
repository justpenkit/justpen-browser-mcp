"""Temporary, unchanged official beta.31 CI assets hosted by Justpen.

Remove this manifest once a fixed upstream release is generally available. The
runtime always prefers an equal/newer official release without a package update.
"""

from camoufox.pkgman import ARCH_MAP, OS_MAP, AvailableVersion, RepoConfig, Version

UPSTREAM_COMMIT = "eb5dc3bc5b917d1e6c71d9cacfecdddb55fbfc4a"
UPSTREAM_RUN = "https://github.com/daijro/camoufox/actions/runs/34003878009"
MIRROR_REPOSITORY = "justpenkit/justpen-browser-mcp"
MIRROR_TAG = "camoufox-ci-152.0.4-beta.31-eb5dc3b"
MIRROR_VERSION = Version(version="152.0.4", build="beta.31")
ASSETS: dict[str, tuple[str, int]] = {
    "lin.arm64": ("921792c6e4ef99b96f5af865469e025876bdd16016272cd6792ebd426f999ca1", 653890850),
    "lin.x86_64": ("2a51cb34d8459f8ac44029483a078e829e124f4f6ef44785668f833c1241a162", 663475715),
    "mac.arm64": ("efbefe6ba09c7e12d4fb34b676866c7d5fb285490b39f5626d37e29deb1461a3", 312670784),
    "mac.x86_64": ("4dc1243a2fb71f9dbe1e3c67d01999a9daea80f4b1d0cbe2db81bbc9c90a6ad1", 319894365),
    "win.i686": ("dc0526c7157c6938bced9087f742c3fccfe99158c1c549965a909c33ce762f01", 478739423),
    "win.x86_64": ("cefcb948fdcfbd5664e75bf9340809dc6476667b5cca6803757517160f01ce9a", 493148353),
}


def mirror_candidate() -> tuple[RepoConfig, AvailableVersion] | None:
    """Return this platform's pinned asset without querying our release catalog."""
    repo = RepoConfig(
        name="JustpenKit",
        repos=[MIRROR_REPOSITORY],
        pattern="{name}-{version}-{build}-{os}.{arch}.zip",
        os_map=dict(OS_MAP),
        arch_map=ARCH_MAP,
    )
    platform = f"{repo.get_os_name()}.{repo.get_arch()}"
    asset = ASSETS.get(platform)
    if asset is None:
        return None
    sha256, size = asset
    filename = f"camoufox-{MIRROR_VERSION.full_string}-{platform}.zip"
    return repo, AvailableVersion(
        version=MIRROR_VERSION,
        url=f"https://github.com/{MIRROR_REPOSITORY}/releases/download/{MIRROR_TAG}/{filename}",
        is_prerelease=True,
        sha256=sha256,
        asset_size=size,
    )
