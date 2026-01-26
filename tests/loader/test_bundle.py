"""Tests for EventBundle ABC and SingleStoreBundle.

This module tests the EventBundle protocol and the SingleStoreBundle wrapper
that provides bundle interface for single-store loaders.
"""

from __future__ import annotations

import pytest

from timetoalign.core import TimeUnit
from timetoalign.loader import EventBundle, EventStore, SingleStoreBundle


class TestEventBundleProtocol:
    """Verify EventBundle ABC contract."""

    def test_cannot_instantiate_abstract(self):
        """EventBundle cannot be instantiated directly."""
        with pytest.raises(TypeError, match="abstract"):
            EventBundle()  # type: ignore[abstract]

    def test_protocol_methods_required(self):
        """Subclasses must implement all abstract methods."""

        # Incomplete implementation should fail
        class IncompleteBundle(EventBundle):
            def __iter__(self):
                yield None

        with pytest.raises(TypeError, match="abstract"):
            IncompleteBundle()  # type: ignore[abstract]


class TestSingleStoreBundle:
    """Tests for SingleStoreBundle wrapper."""

    @pytest.fixture
    def sample_store(self) -> EventStore:
        """Create a sample EventStore for testing."""
        return EventStore.from_dicts(
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

    def test_initialization(self, sample_store: EventStore):
        """SingleStoreBundle initializes correctly."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        assert bundle.store is sample_store
        assert bundle.name == "beats"

    def test_default_name(self, sample_store: EventStore):
        """Default name is 'events'."""
        bundle = SingleStoreBundle(sample_store)

        assert bundle.name == "events"

    def test_iteration(self, sample_store: EventStore):
        """Iteration yields the single store."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        stores = list(bundle)

        assert len(stores) == 1
        assert stores[0] is sample_store

    def test_items(self, sample_store: EventStore):
        """items() yields (name, store) pairs."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        items = list(bundle.items())

        assert len(items) == 1
        assert items[0] == ("beats", sample_store)

    def test_keys(self, sample_store: EventStore):
        """keys() returns tuple of store names."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        assert bundle.keys() == ("beats",)

    def test_values(self, sample_store: EventStore):
        """values() yields stores."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        values = list(bundle.values())

        assert len(values) == 1
        assert values[0] is sample_store

    def test_getitem(self, sample_store: EventStore):
        """Can access store by name."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        assert bundle["beats"] is sample_store

    def test_getitem_invalid_raises_keyerror(self, sample_store: EventStore):
        """Invalid name raises KeyError."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        with pytest.raises(KeyError, match="notes"):
            _ = bundle["notes"]

    def test_len(self, sample_store: EventStore):
        """Length is always 1."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        assert len(bundle) == 1

    def test_contains(self, sample_store: EventStore):
        """Membership check works."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        assert "beats" in bundle
        assert "notes" not in bundle

    def test_repr(self, sample_store: EventStore):
        """repr includes name and count."""
        bundle = SingleStoreBundle(sample_store, name="beats")

        repr_str = repr(bundle)

        assert "SingleStoreBundle" in repr_str
        assert "beats" in repr_str
        assert "2" in repr_str  # 2 events


class TestSingleStoreBundleToTimeline:
    """Test timeline creation from SingleStoreBundle."""

    @pytest.fixture
    def sample_store(self) -> EventStore:
        """Create a sample EventStore for testing."""
        return EventStore.from_dicts(
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

    def test_to_default_timeline_creates_child(self, sample_store: EventStore):
        """to_default_timeline creates parent with one child."""
        bundle = SingleStoreBundle(sample_store, name="notes")

        timeline = bundle.to_default_timeline(uid="test")

        assert timeline.id == "test"
        assert timeline.n_children == 1
        assert "notes" in timeline

    def test_child_has_correct_events(self, sample_store: EventStore):
        """Child timeline contains the store's events."""
        bundle = SingleStoreBundle(sample_store, name="notes")

        timeline = bundle.to_default_timeline()
        child = timeline.get_child("notes")

        # Exact count validation
        assert child.n_events == 2

    def test_child_at_offset_zero(self, sample_store: EventStore):
        """Child is embedded at offset 0."""
        bundle = SingleStoreBundle(sample_store, name="notes")

        timeline = bundle.to_default_timeline()
        offset = timeline.get_child_offset("notes")

        assert offset.value == 0

    def test_flatten_mode_no_children(self, sample_store: EventStore):
        """flatten=True creates timeline without children."""
        bundle = SingleStoreBundle(sample_store, name="notes")

        timeline = bundle.to_timeline(flatten=True)

        assert timeline.n_children == 0
        assert timeline.n_events == 2
