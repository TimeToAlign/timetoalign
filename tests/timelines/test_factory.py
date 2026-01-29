"""Tests for create_timeline factory function.

This module tests the timeline creation API including:
- create_timeline() universal factory
- EventStore.to_timeline() and to_default_timeline()
- EventData.to_timeline()
"""

from __future__ import annotations

import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader import EventData, SingleStore
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
    create_timeline,
)
from timetoalign.timelines.factory import _infer_timeline_class


class TestInferTimelineClass:
    """Tests for _infer_timeline_class helper."""

    def test_logical_discrete(self):
        """Ticks with int -> DiscreteLogicalTimeline."""
        cls = _infer_timeline_class(TimeUnit.ticks, NumberType.int)
        assert cls is DiscreteLogicalTimeline

    def test_logical_continuous_float(self):
        """Quarters with float -> ContinuousLogicalTimeline."""
        cls = _infer_timeline_class(TimeUnit.quarters, NumberType.float)
        assert cls is ContinuousLogicalTimeline

    def test_logical_continuous_fraction(self):
        """Quarters with fraction -> ContinuousLogicalTimeline."""
        cls = _infer_timeline_class(TimeUnit.quarters, NumberType.fraction)
        assert cls is ContinuousLogicalTimeline

    def test_physical_continuous(self):
        """Seconds with float -> ContinuousPhysicalTimeline."""
        cls = _infer_timeline_class(TimeUnit.seconds, NumberType.float)
        assert cls is ContinuousPhysicalTimeline


class TestCreateTimelineFromEventData:
    """Tests for create_timeline with EventData source."""

    @pytest.fixture
    def sample_data(self) -> EventData:
        """EventData with sample events."""
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

    def test_creates_timeline_with_child(self, sample_data: EventData):
        """create_timeline wraps data in store, creates child."""
        timeline = create_timeline(sample_data, uid="test")

        assert timeline.id == "test"
        assert timeline.n_children == 1
        assert "events" in timeline

    def test_child_has_correct_events(self, sample_data: EventData):
        """Child timeline has the data's events."""
        timeline = create_timeline(sample_data)

        child = timeline.get_child("events")
        # Exact count: 2 events
        assert child.n_events == 2

    def test_flatten_mode(self, sample_data: EventData):
        """flatten=True creates timeline without children."""
        timeline = create_timeline(sample_data, flatten=True)

        assert timeline.n_children == 0
        # Exact count: 2 events
        assert timeline.n_events == 2


class TestCreateTimelineFromStore:
    """Tests for create_timeline with EventStore source."""

    @pytest.fixture
    def multi_data_store(self) -> SingleStore:
        """Store with multiple event types for filter testing."""
        data = EventData.from_dicts(
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
                {
                    "id": "r1",
                    "temporal_type": "interval",
                    "event_type": "Rest",
                    "start": 960,
                    "end": 1440,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return SingleStore(data, name="notes")

    def test_creates_children(self, multi_data_store: SingleStore):
        """Default mode creates children at offset 0."""
        timeline = create_timeline(multi_data_store, uid="test")

        assert timeline.id == "test"
        assert timeline.n_children == 1

    def test_store_filters_applied(self, multi_data_store: SingleStore):
        """store_filters excludes filtered events."""
        timeline = create_timeline(
            multi_data_store,
            store_filters={"notes": {"event_type": "Note"}},
        )

        child = timeline.get_child("notes")
        # Exact count: 2 notes, rest excluded
        assert child.n_events == 2


class TestCreateTimelineIncludeExclude:
    """Tests for include_stores and exclude_stores parameters."""

    @pytest.fixture
    def two_data_store(self):
        """Create two separate stores and combine manually for testing."""
        # We'll test with ScoreStore once we have it available
        # For now, use a simple data
        data = EventData.from_dicts(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 0,
                },
            ],
            unit=TimeUnit.ticks,
        )
        return SingleStore(data, name="events")

    def test_include_stores_limits_children(self, two_data_store):
        """include_stores only includes specified data."""
        timeline = create_timeline(
            two_data_store,
            include_stores=["events"],
        )

        assert timeline.n_children == 1
        assert "events" in timeline

    def test_empty_after_filtering_raises(self, two_data_store):
        """ValueError if all data filtered out."""
        with pytest.raises(ValueError, match="No data"):
            create_timeline(
                two_data_store,
                include_stores=["nonexistent"],
            )


class TestCreateTimelineErrors:
    """Tests for error handling in create_timeline."""

    def test_invalid_source_type_raises(self):
        """TypeError for unsupported source type."""
        with pytest.raises(TypeError, match="must be EventStore"):
            create_timeline("invalid")  # type: ignore[arg-type]


class TestEventDataToTimeline:
    """Tests for EventData.to_timeline() method."""

    @pytest.fixture
    def sample_data(self) -> EventData:
        """EventData for testing."""
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
                {
                    "id": "r1",
                    "temporal_type": "interval",
                    "event_type": "Rest",
                    "start": 960,
                    "end": 1440,
                },
            ],
            unit=TimeUnit.ticks,
        )

    def test_creates_timeline_directly(self, sample_data: EventData):
        """to_timeline creates timeline with data's events."""
        timeline = sample_data.to_timeline(uid="direct")

        assert timeline.id == "direct"
        # Exact count: 3 events (2 notes + 1 rest)
        assert timeline.n_events == 3

    def test_with_filters(self, sample_data: EventData):
        """to_timeline with filters excludes filtered events."""
        timeline = sample_data.to_timeline(
            uid="filtered",
            filters={"event_type": "Note"},
        )

        # Exact count: 2 notes only
        assert timeline.n_events == 2

    def test_infers_correct_timeline_class(self, sample_data: EventData):
        """to_timeline creates appropriate timeline subclass."""
        timeline = sample_data.to_timeline()

        # ticks -> DiscreteLogicalTimeline
        assert isinstance(timeline, DiscreteLogicalTimeline)

    def test_seconds_data_creates_physical_timeline(self):
        """Seconds data creates ContinuousPhysicalTimeline."""
        data = EventData.from_dicts(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 0.0,
                },
            ],
            unit=TimeUnit.seconds,
        )

        timeline = data.to_timeline()

        assert isinstance(timeline, ContinuousPhysicalTimeline)


class TestTimelineChildrenStructure:
    """Tests for timeline structure with children."""

    @pytest.fixture
    def notes_data(self) -> EventData:
        """EventData with note events."""
        return EventData.from_dicts(
            [
                {
                    "id": "n1",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 0,
                    "end": 100,
                },
                {
                    "id": "n2",
                    "temporal_type": "interval",
                    "event_type": "Note",
                    "start": 100,
                    "end": 200,
                },
            ],
            unit=TimeUnit.ticks,
        )

    def test_parent_length_equals_max_child(self, notes_data: EventData):
        """Parent timeline length is max of children lengths."""
        store = SingleStore(notes_data, name="notes")
        timeline = store.to_default_timeline()

        # Child ends at 200, so parent length should be at least 200
        assert timeline.length.value >= 200

    def test_children_locked_after_addition(self, notes_data: EventData):
        """Children are locked after being added to parent."""
        store = SingleStore(notes_data, name="notes")
        timeline = store.to_default_timeline()

        child = timeline.get_child("notes")
        assert child.is_locked

    def test_children_maintain_own_coordinates(self, notes_data: EventData):
        """Children maintain their own 0-based coordinate system."""
        store = SingleStore(notes_data, name="notes")
        timeline = store.to_default_timeline()

        child = timeline.get_child("notes")

        # Child's origin is always 0
        assert child.origin.value == 0

        # Child's events start at their original coordinates
        events = list(child.events)
        first_event = events[0]
        assert first_event["start"]["value"] == 0
