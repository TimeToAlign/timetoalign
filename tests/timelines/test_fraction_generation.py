"""Regression tests for exact logical coordinate generation."""

from __future__ import annotations

from fractions import Fraction

from timetoalign.core import NumberType, TimeUnit
from timetoalign.timelines import BeatGrid, ContinuousPhysicalTimeline, Timeline


def _rational_pair(event: dict, field: str) -> Fraction:
    """Return the exact rational represented by a stored coordinate struct."""
    coordinate = event[field]
    return Fraction(coordinate["numerator"], coordinate["denominator"])


def test_beatgrid_materialization_stores_exact_coordinates() -> None:
    """Beat and measure rows retain their exact quarter-note coordinates."""
    grid = BeatGrid(
        length=Fraction(3, 1),
        beats_per_measure=6,
        beat_unit=Fraction(1, 8),
    )

    grid.materialize_beats()
    grid.materialize_measures()

    beats = grid.get_events(event_type="Beat")
    measures = grid.get_events(event_type="Measure")

    beat_rows = list(beats)
    measure_rows = list(measures)

    assert [_rational_pair(event, "start") for event in beat_rows] == [
        Fraction(0),
        Fraction(1, 2),
        Fraction(1),
        Fraction(3, 2),
        Fraction(2),
        Fraction(5, 2),
    ]
    assert [
        (_rational_pair(event, "start"), _rational_pair(event, "end"))
        for event in measure_rows
    ] == [(Fraction(0), Fraction(3))]


def test_physical_timeline_metrical_generation_stores_exact_coordinates() -> None:
    """Metrical events generated from a physical timeline retain exact positions."""
    audio = ContinuousPhysicalTimeline(length=6.0)
    result = audio.create_metrical_grid(
        first_beat_at=0.0,
        end_at=6.0,
        tempo_bpm=60.0,
        beats_per_measure=6,
        beat_unit=Fraction(1, 8),
        beat_type="intervals",
        measure_type="events",
    )

    beats = list(result.grid.get_events(event_type="Beat"))
    measures = list(result.grid.get_events(event_type="Measure"))

    assert _rational_pair(beats[3], "start") == Fraction(3, 2)
    assert _rational_pair(beats[3], "end") == Fraction(2)
    assert [
        (_rational_pair(event, "start"), _rational_pair(event, "end"))
        for event in measures
    ] == [(Fraction(0), Fraction(3))]


def test_from_events_preserves_exact_fraction_length() -> None:
    """Timeline.from_events retains an exact maximum event coordinate."""
    timeline = Timeline.from_events(
        [
            {
                "id": "beat",
                "temporal_type": "instant",
                "event_type": "Beat",
                "instant": Fraction(3, 2),
            }
        ],
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )

    assert timeline.length.value == Fraction(3, 2)
