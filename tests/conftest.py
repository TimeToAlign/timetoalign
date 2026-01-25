"""Shared pytest fixtures for timetoalign tests."""

from fractions import Fraction

import pytest

from timetoalign.core import (
    Coordinate,
    IdGenerator,
    ScopedId,
    TimeUnit,
)

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
