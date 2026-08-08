"""Regression tests for structural pitch protocol discovery."""

from __future__ import annotations

from fractions import Fraction

import pytest

import timetoalign.core as core
from timetoalign.core.enums import TimeUnit
from timetoalign.core.events import EnharmonicPitch, SpecificPitch
from timetoalign.core.protocols import (
    EnharmonicPitchLike,
    GenericPitchLike,
    SpecificPitchClassLike,
    SpecificPitchLike,
)
from timetoalign.core.time import Coordinate, CoordinateField, DurationField
from timetoalign.loader.score.ms3 import Ms3Loader
from timetoalign.loader.score.stores.notes import NoteEventData
from timetoalign.testdata import ensure_data


@pytest.fixture(scope="module")
def vienna_chopin_notes() -> NoteEventData:
    """Load the Vienna Chopin notes table through the public score loader."""
    path = ensure_data("vienna_1x22") / "ms3" / "chopin_op10_no3.notes.tsv"
    return Ms3Loader.from_file(path).get_events()


def test_generic_pitch_discovery_returns_only_pitch_fields(
    vienna_chopin_notes: NoteEventData,
) -> None:
    """Pitch discovery excludes temporal fields on a real notes table."""
    fields = vienna_chopin_notes.get_fields_satisfying(GenericPitchLike)

    assert {field.name for field in fields} == {"midi", "specific_pitch"}
    assert not any(isinstance(field, CoordinateField) for field in fields)
    assert not any(isinstance(field, DurationField) for field in fields)


@pytest.mark.parametrize(
    "protocol",
    [
        GenericPitchLike,
        SpecificPitchClassLike,
        EnharmonicPitchLike,
        SpecificPitchLike,
    ],
)
def test_coordinate_is_not_pitch_like(protocol: type) -> None:
    """A coordinate scalar satisfies none of the pitch protocols."""
    coordinate = Coordinate(Fraction(1, 2), TimeUnit.quarters)

    assert not isinstance(coordinate, protocol)


def test_pitch_specificity_ladder() -> None:
    """Spelled and enharmonic pitches retain their protocol relationships."""
    specific = SpecificPitch(step="C", alter=1, octave=4)
    enharmonic = EnharmonicPitch(midi_number=61)

    assert isinstance(specific, SpecificPitchLike)
    assert isinstance(specific, EnharmonicPitchLike)
    assert isinstance(specific, GenericPitchLike)
    assert isinstance(enharmonic, EnharmonicPitchLike)
    assert isinstance(enharmonic, GenericPitchLike)
    assert not isinstance(enharmonic, SpecificPitchLike)


def test_pitch_like_is_not_exported_from_core() -> None:
    """The removed empty pitch protocol is not importable from core."""
    assert "PitchLike" not in vars(core)
