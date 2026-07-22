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

import logging
import os
import shutil
import tarfile
import threading
from pathlib import Path

_LOG = logging.getLogger(__name__)

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
RELEASE_TAG = "testdata-v5"

#: Base URL where the release assets are hosted.
BASE_URL = (
    f"https://github.com/TimeToAlign/tta_test_data/releases/download/{RELEASE_TAG}/"
)

#: ``filename -> "sha256:<hex>"`` for every archive in the release.
#:
#: The canonical values are produced by the ``Publish test data`` GitHub
#: Action in ``TimeToAlign/tta_test_data`` and copied from the release notes.
#: ``tarfile`` is not reproducible by default (mtimes / entry order leak into
#: the gzip bytes), so a local rebuild will not match the CI-produced
#: archives — always use the digests emitted by the workflow.
REGISTRY = {
    "audio.tar.gz": "sha256:aa73e59d128a131cdaa4efddea0a06aa324946618961871de7b7e64b639b705b",
    "audiolabs_omr.tar.gz": "sha256:74b5ee2c3e99e29e5f6dfccf942f18644030d77f551f2631580a8045a97c59cd",
    "fixtures.tar.gz": "sha256:50a5b67fab60d88f057c91333e616417ccb45c4e4f791f0f65ea00168b4a4876",
    "hendrix.tar.gz": "sha256:9d7303967b58a49f1958bd67bdcfc9739e2cc1dd0229d4d079a4842aef3664c9",
    "ieee1599.tar.gz": "sha256:05a598692259d21cc140a456f6e2fd75470d5581bbda893daa364361b910816a",
    "midi.tar.gz": "sha256:b5b6b50f88ae3ead487bf69b4fcf219f5ef034908886e3acaafe190229e7a676",
    "mpm_toolbox.tar.gz": "sha256:fe08c8821a412ef7be62b794585d1fec73b96b867b9ab67f77462ba42cf825f8",
    "parangonar.tar.gz": "sha256:b21ad8f06c9a8ac3bcc1ee07a2cdba0652f56f00942d5923c3e98ac13732094b",
    "performance_precision.tar.gz": "sha256:450f946cdf5872fbb1f199bba63bccea03503f382cbd1f43d03eaf64a4d1c6c9",
    "score.tar.gz": "sha256:16d763677447f721934e50e2416464152c2f5a69c21e9228559678eb04c922a0",
    "supra.tar.gz": "sha256:da8955e66083bdf09407ae60f5f012a9cb6b3135da0b48dde927d983df6f3d10",
    "tabular.tar.gz": "sha256:2be7453064572274f697975154f3419f83a839cc4ea5d4a2bf4e6e7b8a1f5bdd",
    "target_flows.tar.gz": "sha256:98643d399c956292681052d7bf9d0fb0697cfe1b6b459c70f53c48272eca28c7",
    "thoresen.tar.gz": "sha256:ac4f3fa76588873dc9738f5d33d2c5c07960f060462d9383f96b74e26cad5e84",
    "vienna_1x22.tar.gz": "sha256:b56b7c634c82c093d86b4d593be498ea41222e0ab281a265f4bf82754894babd",
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
    """Return True iff ``target_dir`` should be trusted without re-extracting.

    A directory is trusted in one of two cases:

    * **Sentinel match (canonical case)** — the sentinel file
      ``marker`` exists and matches ``expected_digest``, *and* the
      directory contains at least one non-marker child.  The non-marker
      child check guards against partial-extraction states where the
      sentinel got written but the actual data files were never written
      (or were deleted afterwards): without the guard, downstream
      ``open()`` would fail with ``FileNotFoundError``.
    * **Developer-checkout fallback** — the sentinel is missing but the
      directory exists and contains at least one non-marker file
      (developer checkout / migration window — assume the user placed
      correct data here on purpose).  This path emits a single
      ``logging.WARNING`` (channel ``timetoalign.testdata``) advising
      the caller that contents are not verified against the release
      digest.

    Returns ``False`` when ``target_dir`` does not exist, is empty, or
    holds only the sentinel file with no payload data.  Deleting
    ``target_dir`` is the way to force a re-fetch.
    """
    if not target_dir.is_dir():
        return False

    has_payload = any(p for p in target_dir.iterdir() if p.name != marker.name)

    if marker.is_file():
        if marker.read_text(encoding="utf-8").strip() != expected_digest:
            return False
        # Sentinel matches AND payload is present
        return has_payload

    if not has_payload:
        return False

    _LOG.warning(
        "%s has no .tta_testdata_hash sentinel — trusting existing contents; "
        "rerun ensure_data() after deleting the directory if you suspect drift",
        target_dir,
    )
    return True


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
