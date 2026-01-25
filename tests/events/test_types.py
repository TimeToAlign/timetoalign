"""Tests for events/types.py."""

from __future__ import annotations

import pytest
from fractions import Fraction

from timetoalign.core import Coordinate, EventType, TimeUnit
from timetoalign.events import (
    Event,
    InstantEvent,
    IntervalEvent,
    make_instant_event,
    make_interval_event,
)


class TestEvent:
    """Tests for the Event base class."""

    def test_event_creation(self) -> None:
        """Can create a basic Event."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        assert evt.id == "test_1"
        assert evt.event_type == EventType.instant
        assert evt.unit == TimeUnit.ticks
        assert evt.data == ()

    def test_event_with_data(self) -> None:
        """Event can store arbitrary data."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            data=(("pitch", 60), ("velocity", 100)),
        )
        assert evt.get("pitch") == 60
        assert evt.get("velocity") == 100

    def test_event_get_default(self) -> None:
        """get() returns default for missing keys."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        assert evt.get("missing") is None
        assert evt.get("missing", "default") == "default"

    def test_event_has(self) -> None:
        """has() checks for key existence."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            data=(("pitch", 60),),
        )
        assert evt.has("pitch") is True
        assert evt.has("missing") is False

    def test_event_data_dict(self) -> None:
        """data_dict returns data as a dictionary."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            data=(("pitch", 60), ("velocity", 100)),
        )
        d = evt.data_dict
        assert d == {"pitch": 60, "velocity": 100}
        # Should be a new dict each time
        assert d is not evt.data_dict

    def test_event_is_frozen(self) -> None:
        """Event is immutable."""
        evt = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        with pytest.raises(AttributeError):
            evt.id = "changed"  # type: ignore[misc]

    def test_event_is_hashable(self) -> None:
        """Event can be used in sets and as dict keys."""
        evt1 = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        evt2 = Event(
            id="test_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        assert hash(evt1) == hash(evt2)
        assert evt1 in {evt2}


class TestInstantEvent:
    """Tests for InstantEvent."""

    def test_instant_event_creation(self) -> None:
        """Can create an InstantEvent."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            instant=120,
        )
        assert evt.id == "note_1"
        assert evt.instant == 120
        assert evt.event_type == EventType.instant

    def test_instant_event_coordinate(self) -> None:
        """coordinate property returns a Coordinate."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            instant=120,
        )
        coord = evt.coordinate
        assert isinstance(coord, Coordinate)
        assert coord.value == 120
        assert coord.unit == TimeUnit.ticks

    def test_instant_event_start_end_aliases(self) -> None:
        """start and end are aliases for instant."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
            instant=120,
        )
        assert evt.start == 120
        assert evt.end == 120

    def test_instant_event_forces_event_type(self) -> None:
        """InstantEvent enforces event_type=instant."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.interval,  # Wrong type
            unit=TimeUnit.ticks,
            instant=120,
        )
        assert evt.event_type == EventType.instant

    def test_instant_event_with_fraction(self) -> None:
        """InstantEvent works with Fraction coordinates."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.instant,
            unit=TimeUnit.quarters,
            instant=Fraction(3, 4),
        )
        assert evt.instant == Fraction(3, 4)
        assert evt.coordinate.value == Fraction(3, 4)

    def test_instant_event_with_float(self) -> None:
        """InstantEvent works with float coordinates."""
        evt = InstantEvent(
            id="note_1",
            event_type=EventType.instant,
            unit=TimeUnit.seconds,
            instant=1.5,
        )
        assert evt.instant == 1.5


class TestIntervalEvent:
    """Tests for IntervalEvent."""

    def test_interval_event_creation(self) -> None:
        """Can create an IntervalEvent."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.ticks,
            start=0,
            end=480,
        )
        assert evt.id == "note_1"
        assert evt.start == 0
        assert evt.end == 480
        assert evt.event_type == EventType.interval

    def test_interval_event_duration(self) -> None:
        """duration property returns end - start."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.ticks,
            start=100,
            end=500,
        )
        assert evt.duration == 400

    def test_interval_event_coordinates(self) -> None:
        """Coordinate properties work correctly."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.ticks,
            start=0,
            end=480,
        )
        assert evt.start_coordinate == Coordinate(0, TimeUnit.ticks)
        assert evt.end_coordinate == Coordinate(480, TimeUnit.ticks)

    def test_interval_event_instant_alias(self) -> None:
        """instant is alias for start."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.ticks,
            start=100,
            end=500,
        )
        assert evt.instant == 100

    def test_interval_event_forces_event_type(self) -> None:
        """IntervalEvent enforces event_type=interval."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.instant,  # Wrong type
            unit=TimeUnit.ticks,
            start=0,
            end=480,
        )
        assert evt.event_type == EventType.interval

    def test_interval_event_end_less_than_start_raises(self) -> None:
        """End < start raises ValueError."""
        with pytest.raises(ValueError, match="must be >= start"):
            IntervalEvent(
                id="note_1",
                event_type=EventType.interval,
                unit=TimeUnit.ticks,
                start=500,
                end=100,
            )

    def test_interval_event_zero_duration_allowed(self) -> None:
        """Zero duration (start == end) is allowed."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.ticks,
            start=100,
            end=100,
        )
        assert evt.duration == 0

    def test_interval_event_with_fraction(self) -> None:
        """IntervalEvent works with Fraction coordinates."""
        evt = IntervalEvent(
            id="note_1",
            event_type=EventType.interval,
            unit=TimeUnit.quarters,
            start=Fraction(0),
            end=Fraction(3, 4),
        )
        assert evt.duration == Fraction(3, 4)


class TestFactoryFunctions:
    """Tests for make_instant_event and make_interval_event."""

    def test_make_instant_event(self) -> None:
        """make_instant_event creates an InstantEvent."""
        evt = make_instant_event("n1", 120, TimeUnit.ticks)
        assert isinstance(evt, InstantEvent)
        assert evt.id == "n1"
        assert evt.instant == 120
        assert evt.unit == TimeUnit.ticks

    def test_make_instant_event_with_string_unit(self) -> None:
        """make_instant_event accepts string unit."""
        evt = make_instant_event("n1", 120, "ticks")
        assert evt.unit == TimeUnit.ticks

    def test_make_instant_event_with_data(self) -> None:
        """make_instant_event accepts data kwargs."""
        evt = make_instant_event("n1", 120, TimeUnit.ticks, pitch=60, velocity=100)
        assert evt.get("pitch") == 60
        assert evt.get("velocity") == 100

    def test_make_interval_event(self) -> None:
        """make_interval_event creates an IntervalEvent."""
        evt = make_interval_event("n1", 0, 480, TimeUnit.ticks)
        assert isinstance(evt, IntervalEvent)
        assert evt.id == "n1"
        assert evt.start == 0
        assert evt.end == 480

    def test_make_interval_event_with_string_unit(self) -> None:
        """make_interval_event accepts string unit."""
        evt = make_interval_event("n1", 0, 480, "ticks")
        assert evt.unit == TimeUnit.ticks

    def test_make_interval_event_with_data(self) -> None:
        """make_interval_event accepts data kwargs."""
        evt = make_interval_event("n1", 0, 480, TimeUnit.ticks, pitch=60)
        assert evt.get("pitch") == 60

    def test_make_instant_event_with_enum_no_data(self) -> None:
        """make_instant_event with TimeUnit enum and no data kwargs."""
        evt = make_instant_event("n1", 1.5, TimeUnit.seconds)
        assert evt.unit == TimeUnit.seconds
        assert evt.data == ()

    def test_make_interval_event_with_enum_no_data(self) -> None:
        """make_interval_event with TimeUnit enum and no data kwargs."""
        evt = make_interval_event("n1", 0.0, 1.5, TimeUnit.seconds)
        assert evt.unit == TimeUnit.seconds
        assert evt.data == ()
