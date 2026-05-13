"""On-demand fetching of bundled test/example corpora.

The corpora live as ``.tar.gz`` release assets in the
``TimeToAlign/tta_test_data`` GitHub repository. They are downloaded the
first time a corpus is requested, verified by SHA256, and extracted into a
predictable directory tree.

Public API
----------

* :func:`ensure_data` — fetch and extract one or more corpora, return their
  on-disk paths.
* :func:`get_data_dir` — single-corpus convenience wrapper.
* :data:`DATA_DIR` — directory under which corpora are extracted.
* :data:`REGISTRY` — mapping of archive filename → expected SHA256 digest.

Usage
-----

::

    from timetoalign.testdata import ensure_data

    HENDRIX = ensure_data("hendrix")
    VIENNA = ensure_data("vienna_1x22")
    audio_dir = ensure_data("audio") / "hard_techno"

Where the data lands
--------------------

By default :data:`DATA_DIR` is resolved as follows:

1. If the ``TTA_TESTDATA_DIR`` environment variable is set, it is used verbatim.
2. Otherwise, if this module appears to be running from a source checkout
   (a sibling ``tests/data/`` directory exists), that directory is used so
   that the existing ``Path(...) / "data" / "<name>"`` constants in
   ``conftest.py`` files keep working unchanged.
3. Otherwise (e.g. ``pip install timetoalign``), pooch's per-user cache
   directory is used.

The cached ``.tar.gz`` archives live in pooch's standard cache (override
with ``TTA_TESTDATA_CACHE``).

Publishing a new test-data release
----------------------------------

Edit corpora under ``tta_test_data/data/<name>/`` in the
``TimeToAlign/tta_test_data`` repository, commit, and push a tag::

    git tag testdata-v2
    git push origin testdata-v2

The release workflow in ``tta_test_data`` packages the corpora, publishes a
release with the tarballs as assets, and writes the matching ``REGISTRY``
block into the release notes. Update :data:`RELEASE_TAG` and :data:`REGISTRY`
below to point at the new release.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import threading
from pathlib import Path

try:
    import pooch
except ImportError as exc:  # pragma: no cover - tested via integration
    raise ImportError(
        "timetoalign.testdata requires the 'pooch' package. "
        "Install it via `pip install timetoalign[examples]` "
        "(or `pip install pooch`)."
    ) from exc


# ---------------------------------------------------------------------------
# Release coordinates — update together when republishing the test data
# ---------------------------------------------------------------------------

#: GitHub release tag in the ``tta_test_data`` repository.
RELEASE_TAG = "testdata-v1"

#: Base URL where the release assets are hosted.
BASE_URL = (
    f"https://github.com/TimeToAlign/tta_test_data/releases/download/{RELEASE_TAG}/"
)

#: ``filename -> "sha256:<hex>"`` for every archive in the release.
#:
#: The canonical values are produced by the ``Publish test data`` GitHub
#: Action in ``TimeToAlign/tta_test_data`` and copied from the release notes.
#: The placeholders below come from a local rebuild and **will not match**
#: the CI-produced archives, because ``tarfile`` is not reproducible by
#: default (mtimes / entry order leak into the gzip bytes). Replace this
#: block with the one emitted by the workflow after the first publish.
REGISTRY: dict[str, str] = {
    "audio.tar.gz": "sha256:77e39d6ac1bdfbafe34c47ac02770768a627d6c8a7bb4fcc6e4ef0a6ae9f2913",
    "audiolabs_omr.tar.gz": "sha256:ccc720668bf257547a26e9b0ffb4daa8d5c9582d80e5251efcdca69dfd88dc41",
    "fixtures.tar.gz": "sha256:fdd053ec18676062be80286868944d3db7acb7933a24443283257ccac512bac1",
    "hendrix.tar.gz": "sha256:163b3933de419124bbb2a04ac64940a50024491ef3e522b5b779526a786efddd",
    "midi.tar.gz": "sha256:d50c65573b8628996aef886890fc6552d5645708a2f9868164f7499001abb21c",
    "performance_precision.tar.gz": "sha256:371e2f8ce20955f8ec67d6814a0de1eed54a56c261cfabbf5ef0cc331b520896",
    "score.tar.gz": "sha256:a46982fc3e1a46cac1f06904004c398cb995dc41660b3135742ab7a30025ad9d",
    "supra.tar.gz": "sha256:8b54ce67ad653eb2f7f8153076e06013762d7fdb16792c4b7dfbe10782dd41d1",
    "tabular.tar.gz": "sha256:f456bda3e105eaaf3acd6e49eb5f21962cf2d6aa7103d3e0f78df38fad3e9661",
    "target_flows.tar.gz": "sha256:7333f0d6c0c7d53a6075391e9ae520aff02cc3eada291cc5b4f48eead8ca2e69",
    "thoresen.tar.gz": "sha256:cdf95b26f6be974d3a26c240d5bc59ad4956167bb52e9c770815cc12d6e10308",
    "vienna_1x22.tar.gz": "sha256:02898e85f9877bbf629ab206c8d9b9972aa89e36040c78e2d5c26776835a11c7",
}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _default_data_dir() -> Path:
    """Resolve the directory under which corpora are extracted."""
    override = os.environ.get("TTA_TESTDATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    # ``timetoalign/testdata/__init__.py`` -> repo_root in an editable install
    # is two ``parent`` hops away.
    pkg_parent = Path(__file__).resolve().parents[2]
    source_tests = pkg_parent / "tests" / "data"
    if (pkg_parent / "tests").is_dir():
        return source_tests

    return Path(pooch.os_cache("timetoalign-testdata")) / "data"


#: Directory under which corpora are extracted.
DATA_DIR: Path = _default_data_dir()

_CACHE_DIR = Path(
    os.environ.get("TTA_TESTDATA_CACHE") or pooch.os_cache("timetoalign-testdata")
)

_POOCH = pooch.create(
    path=_CACHE_DIR,
    base_url=BASE_URL,
    registry=REGISTRY,
    env="TTA_TESTDATA_CACHE",
)

_EXTRACT_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def available_corpora() -> tuple[str, ...]:
    """Return the names of every corpus the registry knows about."""
    return tuple(sorted(name.removesuffix(".tar.gz") for name in REGISTRY))


def ensure_data(*names: str) -> tuple[Path, ...]:
    """Make sure each named corpus is extracted under :data:`DATA_DIR`.

    Downloads the archive via pooch (verifying its SHA256) on first use and
    extracts it into ``DATA_DIR / <name>``. Subsequent calls with the same
    name return immediately as long as a sentinel ``.tta_testdata_hash``
    file matches the cached archive's digest.

    Args:
        *names: Corpus names (top-level subdirectory names under
            :data:`DATA_DIR`), e.g. ``"midi"``, ``"vienna_1x22"``.

    Returns:
        The resolved ``DATA_DIR / <name>`` paths in the same order. A single
        ``Path`` (not a tuple) is returned when called with exactly one name,
        to support ``DATA_DIR = ensure_data("midi")``.

    Raises:
        KeyError: If a name is not present in :data:`REGISTRY`.
    """
    paths = tuple(_ensure_one(name) for name in names)
    if len(paths) == 1:
        return paths[0]  # type: ignore[return-value]
    return paths


def get_data_dir(name: str) -> Path:
    """Return ``DATA_DIR / <name>`` after ensuring it is extracted."""
    return _ensure_one(name)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _ensure_one(name: str) -> Path:
    archive_name = f"{name}.tar.gz"
    if archive_name not in REGISTRY:
        raise KeyError(
            f"Unknown test-data corpus '{name}'. "
            f"Known: {', '.join(available_corpora())}"
        )

    target_dir = DATA_DIR / name
    expected_digest = REGISTRY[archive_name].removeprefix("sha256:")
    marker = target_dir / ".tta_testdata_hash"

    if _looks_ready(target_dir, marker, expected_digest):
        return target_dir

    with _EXTRACT_LOCK:
        if _looks_ready(target_dir, marker, expected_digest):
            return target_dir

        archive_path = Path(_POOCH.fetch(archive_name))

        if target_dir.exists():
            shutil.rmtree(target_dir)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, DATA_DIR)

        if not target_dir.is_dir():
            raise RuntimeError(
                f"Archive {archive_name} did not produce expected directory "
                f"{target_dir}. Did the tarball layout change?"
            )
        marker.write_text(expected_digest, encoding="utf-8")

    return target_dir


def _looks_ready(target_dir: Path, marker: Path, expected_digest: str) -> bool:
    """Return True if ``target_dir`` should be trusted without re-extracting.

    A directory is trusted if:

    * the sentinel file matches the expected digest (canonical case — we
      extracted this exact version), OR
    * the sentinel file is missing but the directory exists and is
      non-empty (developer checkout / migration window — assume the user
      placed correct data here on purpose).

    Deleting ``target_dir`` is the way to force a re-fetch.
    """
    if not target_dir.is_dir():
        return False
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip() == expected_digest
    return any(p for p in target_dir.iterdir() if p.name != marker.name)


def _safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract ``tar`` into ``dest`` while rejecting members that escape it."""
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        member_path = (dest_resolved / member.name).resolve()
        if member_path != dest_resolved and dest_resolved not in member_path.parents:
            raise RuntimeError(f"Refusing to extract unsafe path: {member.name!r}")
    tar.extractall(dest)


__all__ = [
    "BASE_URL",
    "DATA_DIR",
    "REGISTRY",
    "RELEASE_TAG",
    "available_corpora",
    "ensure_data",
    "get_data_dir",
]
