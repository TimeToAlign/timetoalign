"""Shared pytest fixtures for timetoalign tests."""

import contextlib

# Import ms3 in the controller process first: its packaging machinery may
# (re)write a generated version module on import, and concurrent first
# imports across xdist workers can race on that write.
with contextlib.suppress(Exception):
    import ms3  # noqa: F401

from fractions import Fraction

import pytest

from timetoalign.core import (
    Coordinate,
    IdGenerator,
    ScopedId,
    TimeUnit,
)


def pytest_addoption(parser):
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked slow (long-running corpus-scale integration tests)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test: pass --runslow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


# --- Coordinate fixtures ---


@pytest.fixture
def coord_ticks_int() -> Coordinate:
    """A coordinate with integer ticks."""
    return Coordinate(120, TimeUnit.ticks)


@pytest.fixture
def coord_seconds_float() -> Coordinate:
    """A coordinate with float seconds."""
    return Coordinate(1.5, TimeUnit.seconds)


@pytest.fixture
def coord_quarters_fraction() -> Coordinate:
    """A coordinate with Fraction quarters."""
    return Coordinate(Fraction(3, 4), TimeUnit.quarters)


# --- ID fixtures ---


@pytest.fixture
def scoped_id() -> ScopedId:
    """A basic scoped ID."""
    return ScopedId("midi", "n42")


@pytest.fixture
def id_generator() -> IdGenerator:
    """A fresh ID generator."""
    return IdGenerator("test")
