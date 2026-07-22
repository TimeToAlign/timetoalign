"""Fixtures for the alignment-loader tests.

The IEEE 1599 corpus is materialised at module level (i.e. before collection)
so that every worker sees the same on-disk layout and no test pays the
download inside its own timing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from timetoalign.alignment.bundle import AlignmentBundle
from timetoalign.loader.alignment import Ieee1599Loader
from timetoalign.testdata import ensure_data

#: The IEEE 1599 corpus root (six complete specimen packages).
IEEE1599_DIR = ensure_data("ieee1599")

#: Specimen key -> path relative to the corpus root.
IEEE1599_SPECIMENS: dict[str, str] = {
    "gymnopedie": "SatiePetriNets/ieee1599/gymnopedie_01.xml",
    "animals": "Animals and their Sounds/animals_and_their_sounds.xml",
    "khomus": "Khorus Music/khomus.xml",
    "pazzariello": "Pazzariello Sparata/pazzariello_sparata.xml",
    "serie": "Serie in 9_8/serie_in_9_8.xml",
    "bach": "bach_artefuga_01.xml",
}


def _specimen_path(specimen: str) -> Path:
    """Return the XML path of one IEEE 1599 specimen."""
    return IEEE1599_DIR / IEEE1599_SPECIMENS[specimen]


@pytest.fixture(scope="session")
def ieee1599_dir() -> Path:
    """The IEEE 1599 corpus root."""
    return IEEE1599_DIR


@pytest.fixture(scope="session")
def ieee1599_path() -> Callable[[str], Path]:
    """Factory returning the XML path of a named specimen."""
    return _specimen_path


@pytest.fixture(scope="session")
def ieee1599_loaders() -> dict[str, Ieee1599Loader]:
    """Lazily-parsed loaders, one per specimen, shared across the session.

    Parsing the large specimens is the expensive part of these tests, so each
    document is parsed at most once per session and only when a test asks for
    it.
    """
    return {}


@pytest.fixture(scope="session")
def ieee1599_loader(ieee1599_loaders: dict[str, Ieee1599Loader]):
    """Factory returning the (cached) loader for a named specimen."""

    def _loader(specimen: str) -> Ieee1599Loader:
        if specimen not in ieee1599_loaders:
            ieee1599_loaders[specimen] = Ieee1599Loader.from_file(
                _specimen_path(specimen)
            )
        return ieee1599_loaders[specimen]

    return _loader


@pytest.fixture(scope="session")
def ieee1599_bundle(ieee1599_loader):
    """Factory returning the (cached) AlignmentBundle for a named specimen."""
    bundles: dict[str, AlignmentBundle] = {}

    def _bundle(specimen: str) -> AlignmentBundle:
        if specimen not in bundles:
            bundles[specimen] = ieee1599_loader(specimen).create_bundle()
        return bundles[specimen]

    return _bundle
