"""Tests for Timeline base class core functionality.

This module tests:
- Timeline construction and initialization
- Coordinate factory methods
- Event addition and retrieval
- Length management and expansion
- Locking mechanism
- Serialization (to_dict / from_dict)

Validity Rationale:
    These tests verify the fundamental Timeline contract:
    1. A Timeline has a fixed unit and number_type
    2. Events are stored in an EventStore
    3. Length can expand (if unlocked) but not contract below content
    4. Coordinates are validated against the timeline's unit
"""

from __future__ import annotations

import time
from fractions import Fraction
from typing import Any

import pytest

from timetoalign.core import Coordinate, NumberType, TimeUnit
from timetoalign.timelines import Timeline

# region Construction Tests


class TestTimelineConstruction:
    """Test Timeline initialization and factory methods."""

    def test_empty_timeline_defaults(self):
        """Empty timeline uses class defaults (seconds, float)."""
        tl = Timeline.empty()
        assert tl.unit == TimeUnit.seconds
        assert tl.number_type == NumberType.float
        assert tl.length.value == 0
        assert tl.n_events == 0
        assert tl.n_children == 0

    def test_timeline_with_length(self):
        """Timeline can be created with specified length."""
        tl = Timeline(length=100.0)
        assert tl.length.value == 100.0
        assert tl.length.unit == TimeUnit.seconds

    def test_timeline_with_unit_string(self):
        """Timeline accepts unit as string."""
        tl = Timeline(length=100, unit="ticks")
        assert tl.unit == TimeUnit.ticks

    def test_timeline_with_number_type_string(self):
        """Timeline accepts number_type as string."""
        tl = Timeline(length=100, number_type="int")
        assert tl.number_type == NumberType.int

    def test_timeline_with_custom_id(self):
        """Timeline can use custom uid."""
        tl = Timeline(uid="my_custom_id")
        assert tl.id == "my_custom_id"

    def test_timeline_auto_generated_id(self):
        """Timeline generates unique ID if none provided."""
        tl1 = Timeline()
        tl2 = Timeline()
        assert tl1.id != tl2.id
        assert tl1.id.startswith("tl:")

    def test_timeline_with_id_prefix(self):
        """Timeline uses custom id_prefix for auto-generation."""
        tl = Timeline(id_prefix="score")
        assert tl.id.startswith("score:")

    def test_timeline_locked_on_creation(self):
        """Timeline can be created in locked state."""
        tl = Timeline(locked=True)
        assert tl.is_locked

    def test_timeline_with_metadata(self):
        """Timeline stores metadata."""
        meta = {"source": "test", "version": 1}
        tl = Timeline(meta=meta)
        assert tl.meta == meta

    def test_from_events_empty(self):
        """from_events with empty list creates empty timeline."""
        tl = Timeline.from_events([])
        assert tl.length.value == 0
        assert tl.n_events == 0

    def test_from_events_calculates_length(self):
        """from_events sets length to accommodate all events."""
        events = [
            {
                "id": "e1",
                "temporal_type": "instant",
                "event_type": "Beat",
                "instant": 0,
            },
            {
                "id": "e2",
                "temporal_type": "instant",
                "event_type": "Beat",
                "instant": 5,
            },
            {
                "id": "e3",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 3,
                "end": 10,
            },
        ]
        tl = Timeline.from_events(events)
        assert tl.length.value == 10.0
        assert tl.n_events == 3


# endregion


# region Coordinate Factory Tests


class TestCoordinateFactory:
    """Test coordinate creation and validation."""

    def test_make_coordinate_from_value(self):
        """make_coordinate creates Coordinate with timeline's unit."""
        tl = Timeline(unit=TimeUnit.seconds)
        coord = tl.make_coordinate(1.5)
        assert coord.value == 1.5
        assert coord.unit == TimeUnit.seconds

    def test_make_coordinate_from_int(self):
        """make_coordinate preserves int type."""
        tl = Timeline(unit=TimeUnit.ticks)
        coord = tl.make_coordinate(480)
        assert coord.value == 480
        assert coord.unit == TimeUnit.ticks

    def test_make_coordinate_from_fraction(self):
        """make_coordinate preserves Fraction type."""
        tl = Timeline(unit=TimeUnit.quarters)
        coord = tl.make_coordinate(Fraction(3, 4))
        assert coord.value == Fraction(3, 4)
        assert coord.unit == TimeUnit.quarters

    def test_origin_always_zero(self):
        """origin property returns coordinate at 0."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        assert tl.origin.value == 0
        assert tl.origin.unit == TimeUnit.seconds

    def test_start_equals_origin(self):
        """start is an alias for origin."""
        tl = Timeline(length=100)
        assert tl.start == tl.origin

    def test_end_equals_length(self):
        """end is an alias for length."""
        tl = Timeline(length=100)
        assert tl.end == tl.length


# endregion


# region Event Management Tests


class TestEventManagement:
    """Test event addition and retrieval."""

    def test_add_events_instant(self, instant_event_rows: list[dict[str, Any]]):
        """Add instant events to timeline."""
        tl = Timeline(length=10.0)
        tl.add_events(instant_event_rows)
        assert tl.n_events == 4

    def test_add_events_interval(self, interval_event_rows: list[dict[str, Any]]):
        """Add interval events to timeline."""
        tl = Timeline(length=10.0)
        tl.add_events(interval_event_rows)
        assert tl.n_events == 3

    def test_add_events_mixed(self, mixed_event_rows: list[dict[str, Any]]):
        """Add mixed instant and interval events."""
        tl = Timeline(length=10.0)
        tl.add_events(mixed_event_rows)
        assert tl.n_events == 7

    def test_add_events_empty_list(self):
        """Adding empty list is a no-op."""
        tl = Timeline(length=10.0)
        tl.add_events([])
        assert tl.n_events == 0

    def test_get_events_all(self, timeline_with_events):
        """get_events without filters returns all events."""
        events = timeline_with_events.get_events()
        assert len(events) == 7

    def test_get_events_by_temporal_type(self, timeline_with_events):
        """Filter events by temporal_type."""
        instants = timeline_with_events.get_events(temporal_type="instant")
        assert len(instants) == 4

        intervals = timeline_with_events.get_events(temporal_type="interval")
        assert len(intervals) == 3

    def test_get_events_by_event_type(self, timeline_with_events):
        """Filter events by event_type."""
        beats = timeline_with_events.get_events(event_type="Beat")
        assert len(beats) == 4

        notes = timeline_with_events.get_events(event_type="Note")
        assert len(notes) == 3

    def test_get_events_excludes_segments_by_default(self):
        """get_events excludes segment events by default."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)
        parent.add_child(child, offset=0)

        # Segment event should NOT be counted
        events = parent.get_events()
        assert len(events) == 0

        # With include_segments=True, it should be included
        events_with_segments = parent.get_events(include_segments=True)
        assert len(events_with_segments) == 1

    def test_get_events_coordinate_range(self, timeline_with_events):
        """Filter events by coordinate range."""
        # Events in range [1.0, 2.5)
        events = timeline_with_events.get_events(min_coord=1.0, max_coord=2.5)
        # Should include beat_2 (1.0), note_2 (1.0-1.25), beat_3 (2.0)
        assert len(events) >= 2


# endregion


# region Length and Expansion Tests


class TestLengthAndExpansion:
    """Test length management and auto-expansion."""

    def test_set_length_expands(self):
        """Can increase length of unlocked timeline."""
        tl = Timeline(length=10.0)
        tl.length = 20.0
        assert tl.length.value == 20.0

    def test_set_length_contracts_empty(self):
        """Can decrease length if no content beyond new length."""
        tl = Timeline(length=10.0)
        tl.length = 5.0
        assert tl.length.value == 5.0

    def test_set_length_refuses_content_cutoff(self):
        """Cannot reduce length below content."""
        tl = Timeline(length=10.0)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 8.0,
                }
            ]
        )
        with pytest.raises(ValueError, match="content extends to"):
            tl.length = 5.0

    def test_add_events_auto_expand_unlocked(self):
        """Unlocked timeline auto-expands for out-of-bounds events."""
        tl = Timeline(length=5.0)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 10.0,
                }
            ]
        )
        assert tl.length.value == 10.0

    def test_add_events_locked_raises(self):
        """Locked timeline raises on out-of-bounds events."""
        tl = Timeline(length=5.0, locked=True)
        with pytest.raises(ValueError, match="Timeline is locked"):
            tl.add_events(
                [
                    {
                        "id": "e1",
                        "temporal_type": "instant",
                        "event_type": "Beat",
                        "instant": 10.0,
                    }
                ]
            )

    def test_add_events_allow_expansion_overrides_lock(self):
        """allow_expansion=True overrides lock."""
        tl = Timeline(length=5.0, locked=True)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 10.0,
                }
            ],
            allow_expansion=True,
        )
        assert tl.length.value == 10.0

    def test_set_length_locked_raises(self):
        """Cannot set length on locked timeline."""
        tl = Timeline(length=10.0, locked=True)
        with pytest.raises(RuntimeError, match="locked"):
            tl.length = 20.0


# endregion


# region Locking Tests


class TestLocking:
    """Test the locking mechanism."""

    def test_is_locked_default_false(self):
        """Timeline is unlocked by default."""
        tl = Timeline()
        assert not tl.is_locked

    def test_is_locked_when_created_locked(self):
        """Timeline can be created locked."""
        tl = Timeline(locked=True)
        assert tl.is_locked

    def test_child_becomes_locked(self):
        """Child timeline is locked when added to parent."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)
        assert not child.is_locked

        parent.add_child(child, offset=0)
        assert child.is_locked

    def test_locked_child_cannot_expand(self):
        """Locked child cannot have events added beyond its length."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)
        parent.add_child(child, offset=0)

        with pytest.raises(ValueError, match="locked"):
            child.add_events(
                [
                    {
                        "id": "e1",
                        "temporal_type": "instant",
                        "event_type": "Beat",
                        "instant": 10.0,
                    }
                ]
            )


# endregion


# region Serialization Tests


class TestSerialization:
    """Test to_dict and from_dict methods."""

    def test_to_dict_basic(self):
        """to_dict includes all timeline properties."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds, uid="test_tl")
        data = tl.to_dict()

        assert data["id"] == "test_tl"
        assert data["class"] == "Timeline"
        assert data["unit"] == "seconds"
        assert data["length"] == 10.0
        assert data["locked"] is False

    def test_to_dict_with_events(self, mixed_event_rows: list[dict[str, Any]]):
        """to_dict includes events."""
        tl = Timeline(length=10.0)
        tl.add_events(mixed_event_rows)
        data = tl.to_dict()

        assert len(data["events"]) == 7

    def test_to_dict_with_children(self):
        """to_dict includes children recursively."""
        parent = Timeline(length=20.0, uid="parent")
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=10.0)

        data = parent.to_dict()
        assert "child" in data["children"]
        assert data["children"]["child"]["offset"] == 10.0
        assert data["children"]["child"]["timeline"]["id"] == "child"

    def test_from_dict_roundtrip(self, mixed_event_rows: list[dict[str, Any]]):
        """from_dict reconstructs timeline from to_dict output."""
        original = Timeline(length=10.0, uid="original")
        original.add_events(mixed_event_rows)

        data = original.to_dict()
        restored = Timeline.from_dict(data)

        assert restored.id == original.id
        assert restored.length.value == original.length.value
        assert restored.n_events == original.n_events

    def test_from_dict_with_children(self):
        """from_dict reconstructs nested structure."""
        parent = Timeline(length=20.0, uid="parent")
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=10.0)

        data = parent.to_dict()
        restored = Timeline.from_dict(data)

        assert restored.n_children == 1
        assert "child" in restored._children
        restored_child = restored.get_child("child")
        assert restored_child.length.value == 5.0


# endregion


# region Magic Methods Tests


class TestMagicMethods:
    """Test __len__, __repr__, __str__, __contains__."""

    def test_len_returns_event_count(self, timeline_with_events):
        """__len__ returns number of events."""
        assert len(timeline_with_events) == 7

    def test_repr_format(self):
        """__repr__ includes key information."""
        tl = Timeline(length=10.0, uid="test")
        repr_str = repr(tl)
        assert "Timeline" in repr_str
        assert "test" in repr_str
        assert "10" in repr_str

    def test_str_format(self):
        """__str__ is human-readable."""
        tl = Timeline(length=10.0, uid="test", unit=TimeUnit.seconds)
        str_repr = str(tl)
        assert "Timeline" in str_repr
        assert "test" in str_repr
        assert "seconds" in str_repr

    def test_contains_child_by_object(self):
        """__contains__ works with Timeline objects."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)
        other = Timeline(length=3.0)

        parent.add_child(child, offset=0)

        assert child in parent
        assert other not in parent

    def test_contains_child_by_id(self):
        """__contains__ works with string IDs."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="my_child")
        parent.add_child(child, offset=0)

        assert "my_child" in parent
        assert "nonexistent" not in parent

    def test_contains_region_by_name(self):
        """__contains__ checks regions by string name."""
        tl = Timeline(length=100.0)
        tl.add_region("Chorus", start=30, end=60)

        assert "Chorus" in tl
        assert "Bridge" not in tl

    def test_contains_region_by_object(self):
        """__contains__ checks Region objects by name."""
        from timetoalign.timelines import Region

        tl = Timeline(length=100.0)
        tl.add_region("Chorus", start=30, end=60)

        region = tl.get_region("Chorus")
        assert region in tl

        other = Region(
            name="Other",
            start=Coordinate(0, TimeUnit.seconds),
            end=Coordinate(10, TimeUnit.seconds),
        )
        assert other not in tl

    def test_contains_checks_regions_and_children(self):
        """__contains__ with string checks both regions and children."""
        tl = Timeline(length=100.0)
        tl.add_region("Chorus", start=30, end=60)
        child = Timeline(length=5.0, uid="my_child")
        tl.add_child(child, offset=0)

        # Both region and child names should be found
        assert "Chorus" in tl
        assert "my_child" in tl
        assert "nonexistent" not in tl


# endregion


# region Future API Stubs Tests


class TestFutureApiStubs:
    """Test placeholder methods for future phases."""

    def test_add_match_not_implemented(self):
        """add_match raises NotImplementedError."""
        tl = Timeline()
        with pytest.raises(NotImplementedError, match="Phase 6"):
            tl.add_match(None)

    def test_add_break_not_implemented(self):
        """add_break raises NotImplementedError."""
        tl = Timeline()
        coord = Coordinate(5.0, TimeUnit.seconds)
        with pytest.raises(NotImplementedError, match="future phase"):
            tl.add_break(coord)

    def test_add_jump_not_implemented(self):
        """add_jump raises NotImplementedError."""
        tl = Timeline()
        coord1 = Coordinate(5.0, TimeUnit.seconds)
        coord2 = Coordinate(10.0, TimeUnit.seconds)
        with pytest.raises(NotImplementedError, match="future phase"):
            tl.add_jump(coord1, coord2)


# endregion


# region Performance Tests


class TestPerformance:
    """Performance benchmarks for Timeline operations."""

    def test_add_many_events_performance(self, profiler):
        """Benchmark adding many events."""
        n_events = 10000
        events = [
            {
                "id": f"e_{i}",
                "temporal_type": "instant",
                "event_type": "Beat",
                "instant": float(i),
            }
            for i in range(n_events)
        ]

        tl = Timeline(length=float(n_events))

        start = time.perf_counter()
        tl.add_events(events)
        elapsed = time.perf_counter() - start

        profiler.record("add_10000_events", elapsed)

        assert tl.n_events == n_events
        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0, f"Adding {n_events} events took {elapsed:.2f}s"

    def test_create_many_timelines_performance(self, profiler):
        """Benchmark creating many timelines."""
        n_timelines = 1000

        start = time.perf_counter()
        timelines = [Timeline(length=100.0) for _ in range(n_timelines)]
        elapsed = time.perf_counter() - start

        profiler.record("create_1000_timelines", elapsed)

        assert len(timelines) == n_timelines
        # Should complete quickly (< 2 seconds)
        assert elapsed < 2.0, f"Creating {n_timelines} timelines took {elapsed:.2f}s"


# endregion
