"""Tests for events/store.py."""

from __future__ import annotations

import pytest
from fractions import Fraction

from timetoalign.core import EventType, TimeUnit
from timetoalign.events import (
    EventStore,
    InstantEvent,
    IntervalEvent,
    make_instant_event,
    make_interval_event,
)


class TestEventStoreCreation:
    """Tests for EventStore creation."""

    def test_empty_store(self) -> None:
        """Can create an empty EventStore."""
        store = EventStore()
        assert len(store) == 0
        assert store.name == ""
        assert store.unit is None

    def test_store_with_name(self) -> None:
        """Can create a named EventStore."""
        store = EventStore(name="midi_events")
        assert store.name == "midi_events"

    def test_store_with_unit(self) -> None:
        """Can create a store with fixed unit."""
        store = EventStore(unit=TimeUnit.ticks)
        assert store.unit == TimeUnit.ticks

    def test_store_repr(self) -> None:
        """__repr__ returns useful info."""
        store = EventStore(name="test", unit=TimeUnit.ticks)
        r = repr(store)
        assert "EventStore" in r
        assert "test" in r
        assert "ticks" in r
        assert "events=0" in r


class TestEventStoreAddEvents:
    """Tests for adding events to EventStore."""

    def test_add_instant_event(self) -> None:
        """Can add an instant event."""
        store = EventStore()
        evt = store.add_instant("n1", 120, TimeUnit.ticks)
        assert len(store) == 1
        assert isinstance(evt, InstantEvent)
        assert evt.id == "n1"

    def test_add_interval_event(self) -> None:
        """Can add an interval event."""
        store = EventStore()
        evt = store.add_interval("n1", 0, 480, TimeUnit.ticks)
        assert len(store) == 1
        assert isinstance(evt, IntervalEvent)
        assert evt.start == 0
        assert evt.end == 480

    def test_add_event_object(self) -> None:
        """Can add a pre-created event."""
        store = EventStore()
        evt = make_instant_event("n1", 120, TimeUnit.ticks)
        store.add(evt)
        assert len(store) == 1
        assert store.get("n1") is evt

    def test_add_with_data(self) -> None:
        """Can add events with data."""
        store = EventStore()
        evt = store.add_instant("n1", 120, TimeUnit.ticks, pitch=60, velocity=100)
        assert evt.get("pitch") == 60
        assert evt.get("velocity") == 100

    def test_add_duplicate_id_raises(self) -> None:
        """Adding duplicate ID raises ValueError."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        with pytest.raises(ValueError, match="already exists"):
            store.add_instant("n1", 240, TimeUnit.ticks)

    def test_add_unit_mismatch_raises(self) -> None:
        """Adding event with wrong unit raises ValueError."""
        store = EventStore(unit=TimeUnit.ticks)
        with pytest.raises(ValueError, match="doesn't match store unit"):
            store.add_instant("n1", 1.5, TimeUnit.seconds)

    def test_add_with_string_unit(self) -> None:
        """Can add events with string unit."""
        store = EventStore()
        evt = store.add_instant("n1", 120, "ticks")
        assert evt.unit == TimeUnit.ticks

    def test_add_interval_with_string_unit(self) -> None:
        """Can add interval events with string unit."""
        store = EventStore()
        evt = store.add_interval("n1", 0, 480, "ticks")
        assert evt.unit == TimeUnit.ticks

    def test_add_instant_with_enum_unit_no_data(self) -> None:
        """add_instant with TimeUnit enum and no data kwargs."""
        store = EventStore()
        # Explicitly use TimeUnit enum (not string) and no data kwargs
        evt = store.add_instant("n1", 120, TimeUnit.seconds)
        assert evt.unit == TimeUnit.seconds
        assert evt.data == ()

    def test_add_interval_with_enum_unit_no_data(self) -> None:
        """add_interval with TimeUnit enum and no data kwargs."""
        store = EventStore()
        # Explicitly use TimeUnit enum (not string) and no data kwargs
        evt = store.add_interval("n1", 0.0, 1.5, TimeUnit.seconds)
        assert evt.unit == TimeUnit.seconds
        assert evt.data == ()


class TestEventStoreRetrieval:
    """Tests for retrieving events from EventStore."""

    def test_get_existing(self) -> None:
        """Can get an existing event by ID."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        evt = store.get("n1")
        assert evt is not None
        assert evt.id == "n1"

    def test_get_missing(self) -> None:
        """get() returns None for missing ID."""
        store = EventStore()
        assert store.get("missing") is None

    def test_get_instant(self) -> None:
        """get_instant() returns InstantEvent or None."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)

        assert store.get_instant("n1") is not None
        assert store.get_instant("n2") is None  # It's an interval
        assert store.get_instant("missing") is None

    def test_get_interval(self) -> None:
        """get_interval() returns IntervalEvent or None."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)

        assert store.get_interval("n2") is not None
        assert store.get_interval("n1") is None  # It's an instant
        assert store.get_interval("missing") is None

    def test_contains(self) -> None:
        """Can use 'in' operator to check for ID."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        assert "n1" in store
        assert "missing" not in store


class TestEventStoreIteration:
    """Tests for iterating over EventStore."""

    def test_iter_all(self) -> None:
        """Can iterate over all events."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)
        events = list(store)
        assert len(events) == 2

    def test_iter_instants(self) -> None:
        """iter_instants() yields only instant events."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)
        store.add_instant("n3", 240, TimeUnit.ticks)

        instants = list(store.iter_instants())
        assert len(instants) == 2
        assert all(isinstance(e, InstantEvent) for e in instants)

    def test_iter_intervals(self) -> None:
        """iter_intervals() yields only interval events."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)
        store.add_interval("n3", 480, 960, TimeUnit.ticks)

        intervals = list(store.iter_intervals())
        assert len(intervals) == 2
        assert all(isinstance(e, IntervalEvent) for e in intervals)

    def test_iter_by_type(self) -> None:
        """iter_by_type() filters by EventType."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)

        instants = list(store.iter_by_type(EventType.instant))
        intervals = list(store.iter_by_type(EventType.interval))

        assert len(instants) == 1
        assert len(intervals) == 1

    def test_iter_sorted(self) -> None:
        """iter_sorted() yields events in coordinate order."""
        store = EventStore()
        store.add_instant("n2", 240, TimeUnit.ticks)
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n3", 360, TimeUnit.ticks)

        sorted_events = list(store.iter_sorted())
        assert [e.id for e in sorted_events] == ["n1", "n2", "n3"]

    def test_iter_sorted_reverse(self) -> None:
        """iter_sorted(reverse=True) yields descending order."""
        store = EventStore()
        store.add_instant("n2", 240, TimeUnit.ticks)
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n3", 360, TimeUnit.ticks)

        sorted_events = list(store.iter_sorted(reverse=True))
        assert [e.id for e in sorted_events] == ["n3", "n2", "n1"]

    def test_iter_sorted_mixed_types(self) -> None:
        """iter_sorted() works with mixed event types."""
        store = EventStore()
        store.add_interval("n1", 0, 100, TimeUnit.ticks)
        store.add_instant("n2", 50, TimeUnit.ticks)
        store.add_interval("n3", 200, 300, TimeUnit.ticks)

        sorted_events = list(store.iter_sorted())
        # n1 starts at 0, n2 at 50, n3 at 200
        assert [e.id for e in sorted_events] == ["n1", "n2", "n3"]


class TestEventStoreFilter:
    """Tests for EventStore.filter()."""

    def test_filter_by_event_type(self) -> None:
        """Can filter by event type."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_interval("n2", 0, 480, TimeUnit.ticks)

        results = list(store.filter(event_type=EventType.instant))
        assert len(results) == 1
        assert results[0].id == "n1"

    def test_filter_by_unit(self) -> None:
        """Can filter by unit."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n2", 1.5, TimeUnit.seconds)

        results = list(store.filter(unit=TimeUnit.ticks))
        assert len(results) == 1
        assert results[0].id == "n1"

    def test_filter_by_min_coord_instant(self) -> None:
        """min_coord filters instant events."""
        store = EventStore()
        store.add_instant("n1", 100, TimeUnit.ticks)
        store.add_instant("n2", 200, TimeUnit.ticks)
        store.add_instant("n3", 300, TimeUnit.ticks)

        results = list(store.filter(min_coord=200))
        assert [e.id for e in results] == ["n2", "n3"]

    def test_filter_by_max_coord_instant(self) -> None:
        """max_coord filters instant events."""
        store = EventStore()
        store.add_instant("n1", 100, TimeUnit.ticks)
        store.add_instant("n2", 200, TimeUnit.ticks)
        store.add_instant("n3", 300, TimeUnit.ticks)

        results = list(store.filter(max_coord=200))
        assert [e.id for e in results] == ["n1"]

    def test_filter_by_min_coord_interval(self) -> None:
        """min_coord filters interval events (by end)."""
        store = EventStore()
        store.add_interval("n1", 0, 100, TimeUnit.ticks)
        store.add_interval("n2", 100, 200, TimeUnit.ticks)
        store.add_interval("n3", 200, 300, TimeUnit.ticks)

        # min_coord=150 means end must be > 150
        results = list(store.filter(min_coord=150))
        assert [e.id for e in results] == ["n2", "n3"]

    def test_filter_by_max_coord_interval(self) -> None:
        """max_coord filters interval events (by start)."""
        store = EventStore()
        store.add_interval("n1", 0, 100, TimeUnit.ticks)
        store.add_interval("n2", 100, 200, TimeUnit.ticks)
        store.add_interval("n3", 200, 300, TimeUnit.ticks)

        # max_coord=150 means start must be < 150
        results = list(store.filter(max_coord=150))
        assert [e.id for e in results] == ["n1", "n2"]

    def test_filter_by_data_key(self) -> None:
        """Can filter by data key existence."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks, pitch=60)
        store.add_instant("n2", 240, TimeUnit.ticks)

        results = list(store.filter(data_key="pitch"))
        assert len(results) == 1
        assert results[0].id == "n1"

    def test_filter_by_data_value(self) -> None:
        """Can filter by data key and value."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks, pitch=60)
        store.add_instant("n2", 240, TimeUnit.ticks, pitch=72)

        results = list(store.filter(data_key="pitch", data_value=60))
        assert len(results) == 1
        assert results[0].id == "n1"

    def test_filter_combined(self) -> None:
        """Multiple filter criteria are AND-ed."""
        store = EventStore()
        store.add_instant("n1", 100, TimeUnit.ticks, pitch=60)
        store.add_instant("n2", 200, TimeUnit.ticks, pitch=60)
        store.add_instant("n3", 300, TimeUnit.ticks, pitch=72)

        results = list(store.filter(min_coord=150, data_key="pitch", data_value=60))
        assert len(results) == 1
        assert results[0].id == "n2"

    def test_filter_with_base_event_min_coord(self) -> None:
        """Filter handles base Event (edge case) with min_coord."""
        from timetoalign.events.types import Event

        store = EventStore()
        # Directly add a base Event (not InstantEvent or IntervalEvent)
        # This is an edge case - shouldn't happen in practice but tests the branch
        base_evt = Event(
            id="base1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        store._events.append(base_evt)
        store._id_index["base1"] = 0

        # With min_coord set, base Event should pass through (no instant/start check)
        results = list(store.filter(min_coord=100))
        # Base event has no coordinate, so it passes the filter (no check applies)
        assert len(results) == 1
        assert results[0].id == "base1"

    def test_filter_with_base_event_max_coord(self) -> None:
        """Filter handles base Event (edge case) with max_coord."""
        from timetoalign.events.types import Event

        store = EventStore()
        # Directly add a base Event
        base_evt = Event(
            id="base1",
            event_type=EventType.instant,
            unit=TimeUnit.ticks,
        )
        store._events.append(base_evt)
        store._id_index["base1"] = 0

        # With max_coord set, base Event should pass through
        results = list(store.filter(max_coord=100))
        assert len(results) == 1
        assert results[0].id == "base1"


class TestEventStoreBulkOperations:
    """Tests for bulk operations on EventStore."""

    def test_ids(self) -> None:
        """ids() returns all event IDs in insertion order."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n2", 240, TimeUnit.ticks)
        store.add_instant("n3", 360, TimeUnit.ticks)

        assert store.ids() == ["n1", "n2", "n3"]

    def test_count_by_type(self) -> None:
        """count_by_type() returns counts per type."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n2", 240, TimeUnit.ticks)
        store.add_interval("n3", 0, 480, TimeUnit.ticks)

        counts = store.count_by_type()
        assert counts[EventType.instant] == 2
        assert counts[EventType.interval] == 1

    def test_count_by_type_empty(self) -> None:
        """count_by_type() works on empty store."""
        store = EventStore()
        counts = store.count_by_type()
        assert counts[EventType.instant] == 0
        assert counts[EventType.interval] == 0

    def test_clear(self) -> None:
        """clear() removes all events."""
        store = EventStore()
        store.add_instant("n1", 120, TimeUnit.ticks)
        store.add_instant("n2", 240, TimeUnit.ticks)

        store.clear()
        assert len(store) == 0
        assert "n1" not in store
        assert store.ids() == []
