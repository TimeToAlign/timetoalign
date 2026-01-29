"""Tests for EventStore ABC and SingleStore.

This module tests the EventStore protocol and the SingleStore wrapper
that provides store interface for single-store loaders.
"""

from __future__ import annotations

import pytest

from timetoalign.core import TimeUnit
from timetoalign.loader import EventData, EventStore, SingleStore


class TestEventStoreProtocol:
    """Verify EventStore ABC contract."""

    def test_cannot_instantiate_abstract(self):
        """EventStore cannot be instantiated directly."""
        with pytest.raises(TypeError, match="abstract"):
            EventStore()  # type: ignore[abstract]

    def test_protocol_methods_required(self):
        """Subclasses must implement all abstract methods."""

        # Incomplete implementation should fail
        class IncompleteStore(EventStore):
            def __iter__(self):
                yield None

        with pytest.raises(TypeError, match="abstract"):
            IncompleteStore()  # type: ignore[abstract]


class TestSingleStore:
    """Tests for SingleStore wrapper."""

    @pytest.fixture
    def sample_data(self) -> EventData:
        """Create a sample EventData for testing."""
        return EventData.from_dicts(
            [
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
                    "instant": 480,
                },
            ],
            unit=TimeUnit.ticks,
        )

    def test_initialization(self, sample_data: EventData):
        """SingleStore initializes correctly."""
        single_store = SingleStore(sample_data, name="beats")

        assert single_store.data is sample_data
        assert single_store.name == "beats"

    def test_default_name(self, sample_data: EventData):
        """Default name is 'events'."""
        store = SingleStore(sample_data)

        assert store.name == "events"

    def test_iteration(self, sample_data: EventData):
        """Iteration yields the single data."""
        store = SingleStore(sample_data, name="beats")

        data_items = list(store)

        assert len(data_items) == 1
        assert data_items[0] is sample_data

    def test_items(self, sample_data: EventData):
        """items() yields (name, data) pairs."""
        store = SingleStore(sample_data, name="beats")

        items = list(store.items())

        assert len(items) == 1
        assert items[0] == ("beats", sample_data)

    def test_keys(self, sample_data: EventData):
        """keys() returns tuple of data names."""
        store = SingleStore(sample_data, name="beats")

        assert store.keys() == ("beats",)

    def test_values(self, sample_data: EventData):
        """values() yields data objects."""
        store = SingleStore(sample_data, name="beats")

        values = list(store.values())

        assert len(values) == 1
        assert values[0] is sample_data

    def test_getitem(self, sample_data: EventData):
        """Can access data by name."""
        store = SingleStore(sample_data, name="beats")

        assert store["beats"] is sample_data

    def test_getitem_invalid_raises_keyerror(self, sample_data: EventData):
        """Invalid name raises KeyError."""
        store = SingleStore(sample_data, name="beats")

        with pytest.raises(KeyError, match="notes"):
            _ = store["notes"]

    def test_len(self, sample_data: EventData):
        """Length is always 1."""
        store = SingleStore(sample_data, name="beats")

        assert len(store) == 1

    def test_contains(self, sample_data: EventData):
        """Membership check works."""
        store = SingleStore(sample_data, name="beats")

        assert "beats" in store
        assert "notes" not in store

    def test_repr(self, sample_data: EventData):
        """repr includes name and count."""
        store = SingleStore(sample_data, name="beats")

        repr_str = repr(store)

        assert "SingleStore" in repr_str
        assert "beats" in repr_str
        assert "2" in repr_str  # 2 events


class TestSingleStoreToTimeline:
    """Test timeline creation from SingleStore."""

    @pytest.fixture
    def sample_data(self) -> EventData:
        """Create a sample EventData for testing."""
        return EventData.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 480,
                },
                {
                    "id": "n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 480,
                    "end": 960,
                },
            ],
            unit=TimeUnit.ticks,
        )

    def test_to_default_timeline_creates_child(self, sample_data: EventData):
        """to_default_timeline creates parent with one child."""
        store = SingleStore(sample_data, name="notes")

        timeline = store.to_default_timeline(uid="test")

        assert timeline.id == "test"
        assert timeline.n_children == 1
        assert "notes" in timeline

    def test_child_has_correct_events(self, sample_data: EventData):
        """Child timeline contains the data's events."""
        store = SingleStore(sample_data, name="notes")

        timeline = store.to_default_timeline()
        child = timeline.get_child("notes")

        # Exact count validation
        assert child.n_events == 2

    def test_child_at_offset_zero(self, sample_data: EventData):
        """Child is embedded at offset 0."""
        store = SingleStore(sample_data, name="notes")

        timeline = store.to_default_timeline()
        offset = timeline.get_child_offset("notes")

        assert offset.value == 0

    def test_flatten_mode_no_children(self, sample_data: EventData):
        """flatten=True creates timeline without children."""
        store = SingleStore(sample_data, name="notes")

        timeline = store.to_timeline(flatten=True)

        assert timeline.n_children == 0
        assert timeline.n_events == 2
