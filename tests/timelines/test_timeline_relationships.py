"""Tests for Timeline Relationship Concepts: Region, SegmentLine, derive(), partition().

This module tests the architecture harmonization features that clarify the TTA
manuscript's distinction between:
- **Region**: A named TimeInterval (NOT a timeline)
- **Child**: A timeline nested in a parent (same unit)
- **Segment**: A Child that is contiguous with siblings
- **SegmentLine**: A parent where ALL children are Segments
- **Derivative**: A new timeline created via C-map conversion (different unit)

From TTA Manuscript (Section 3.4-3.5):
"A Region is a named part of a timeline that is defined by a TimeInterval.
Regions are useful for referring to parts of a timeline by name."

"When all Children of the same parent timeline ('siblings') are contiguous
with each other, we call them Segments and the parent a SegmentLine."

"A ConversionMap implies the presence of a derived timeline in the target unit."

Validity Rationale:
    These tests verify:
    1. Region is an immutable dataclass (NOT a timeline)
    2. Regions can be partitioned into Children
    3. SegmentLine enforces contiguity of children
    4. derive() creates timelines in different units via C-maps
    5. Roundtrip conversions work correctly (inverse C-maps)
"""

from __future__ import annotations

import pytest

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.maps import LinearMap
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    Region,
    SegmentLine,
    Timeline,
    get_timeline_class,
)

# region Region Tests


class TestRegionDataclass:
    """Test the Region dataclass itself (not attached to a timeline)."""

    def test_region_creation(self):
        """Region can be created with name, start, end."""
        start = Coordinate(10.0, TimeUnit.seconds)
        end = Coordinate(30.0, TimeUnit.seconds)
        region = Region(name="Chorus", start=start, end=end)

        assert region.name == "Chorus"
        assert region.start.value == 10.0
        assert region.end.value == 30.0
        assert region.unit == TimeUnit.seconds

    def test_region_duration(self):
        """Region.duration computes end - start."""
        start = Coordinate(10.0, TimeUnit.seconds)
        end = Coordinate(30.0, TimeUnit.seconds)
        region = Region(name="Test", start=start, end=end)

        assert region.duration == 20.0

    def test_region_as_interval(self):
        """Region.as_interval returns (start, end) tuple."""
        start = Coordinate(5.0, TimeUnit.seconds)
        end = Coordinate(15.0, TimeUnit.seconds)
        region = Region(name="Test", start=start, end=end)

        assert region.as_interval == (5.0, 15.0)

    def test_region_contains_left_inclusive(self):
        """Region.contains follows [start, end) convention."""
        start = Coordinate(10.0, TimeUnit.seconds)
        end = Coordinate(20.0, TimeUnit.seconds)
        region = Region(name="Test", start=start, end=end)

        # Start is included
        assert region.contains(10.0) is True
        # Middle is included
        assert region.contains(15.0) is True
        # End is NOT included (right-exclusive)
        assert region.contains(20.0) is False
        # Before start is not included
        assert region.contains(9.99) is False

    def test_region_overlaps(self):
        """Region.overlaps detects overlapping regions."""
        r1 = Region(
            name="A",
            start=Coordinate(0.0, TimeUnit.seconds),
            end=Coordinate(10.0, TimeUnit.seconds),
        )
        r2 = Region(
            name="B",
            start=Coordinate(5.0, TimeUnit.seconds),
            end=Coordinate(15.0, TimeUnit.seconds),
        )
        r3 = Region(
            name="C",
            start=Coordinate(10.0, TimeUnit.seconds),
            end=Coordinate(20.0, TimeUnit.seconds),
        )
        r4 = Region(
            name="D",
            start=Coordinate(15.0, TimeUnit.seconds),
            end=Coordinate(25.0, TimeUnit.seconds),
        )

        # Overlapping
        assert r1.overlaps(r2) is True
        assert r2.overlaps(r1) is True

        # Adjacent (not overlapping - [0,10) and [10,20) don't share coords)
        assert r1.overlaps(r3) is False
        assert r3.overlaps(r1) is False

        # Non-overlapping
        assert r1.overlaps(r4) is False
        assert r4.overlaps(r1) is False

    def test_region_rejects_end_before_start(self):
        """Region rejects end < start in __post_init__."""
        start = Coordinate(20.0, TimeUnit.seconds)
        end = Coordinate(10.0, TimeUnit.seconds)

        with pytest.raises(ValueError, match="end.*cannot be before"):
            Region(name="Invalid", start=start, end=end)

    def test_region_rejects_mismatched_units(self):
        """Region rejects start/end with different units."""
        start = Coordinate(10.0, TimeUnit.seconds)
        end = Coordinate(20.0, TimeUnit.quarters)  # Different unit!

        with pytest.raises(ValueError, match="unit.*must match"):
            Region(name="Invalid", start=start, end=end)

    def test_region_with_metadata(self):
        """Region can store metadata."""
        start = Coordinate(0.0, TimeUnit.seconds)
        end = Coordinate(10.0, TimeUnit.seconds)
        region = Region(
            name="Verse",
            start=start,
            end=end,
            meta={"repeat": 2, "label": "verse_1"},
        )

        assert region.meta["repeat"] == 2
        assert region.meta["label"] == "verse_1"

    def test_region_is_frozen(self):
        """Region is immutable (frozen dataclass)."""
        start = Coordinate(0.0, TimeUnit.seconds)
        end = Coordinate(10.0, TimeUnit.seconds)
        region = Region(name="Test", start=start, end=end)

        with pytest.raises(Exception):  # FrozenInstanceError
            region.name = "Changed"


# endregion


# region Timeline Region Management Tests


class TestTimelineRegionManagement:
    """Test add_region, get_region, iter_regions on Timeline."""

    def test_add_region_returns_region_object(self):
        """add_region returns the created Region object."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        region = tl.add_region("Chorus", start=30, end=60)

        assert isinstance(region, Region)
        assert region.name == "Chorus"
        assert region.duration == 30.0

    def test_add_region_stores_region(self):
        """Added regions are stored and retrievable."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Verse", start=0, end=30)
        tl.add_region("Chorus", start=30, end=60)

        assert tl.n_regions == 2
        assert tl.has_region("Verse") is True
        assert tl.has_region("Chorus") is True
        assert tl.has_region("Bridge") is False

    def test_get_region_returns_dict(self):
        """get_region returns dictionary for backwards compatibility."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Test", start=10, end=20)

        result = tl.get_region("Test")
        assert isinstance(result, dict)
        assert result["name"] == "Test"
        assert result["start"] == 10.0
        assert result["end"] == 20.0

    def test_get_region_object_returns_region(self):
        """get_region_object returns the Region instance."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Test", start=10, end=20)

        region = tl.get_region_object("Test")
        assert isinstance(region, Region)
        assert region.name == "Test"

    def test_get_region_nonexistent_returns_none(self):
        """get_region returns None for nonexistent region."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        assert tl.get_region("NonExistent") is None

    def test_iter_regions(self):
        """iter_regions yields all Region objects."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("A", start=0, end=25)
        tl.add_region("B", start=25, end=50)
        tl.add_region("C", start=50, end=75)

        regions = list(tl.iter_regions())
        assert len(regions) == 3
        names = {r.name for r in regions}
        assert names == {"A", "B", "C"}

    def test_list_regions(self):
        """list_regions returns region names."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("X", start=0, end=50)
        tl.add_region("Y", start=50, end=100)

        names = tl.list_regions()
        assert set(names) == {"X", "Y"}

    def test_add_region_rejects_duplicate_name(self):
        """add_region rejects duplicate region names."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Chorus", start=30, end=60)

        with pytest.raises(ValueError, match="already exists"):
            tl.add_region("Chorus", start=70, end=90)

    def test_add_region_on_locked_timeline_raises(self):
        """add_region raises RuntimeError on locked timeline."""
        tl = Timeline(length=100, unit=TimeUnit.seconds, locked=True)

        with pytest.raises(RuntimeError, match="locked"):
            tl.add_region("Test", start=0, end=10)


# endregion


# region Partition Tests


class TestTimelinePartition:
    """Test Timeline.partition() - creating Children from Regions."""

    def test_partition_creates_child(self):
        """partition creates a child timeline at the region's offset."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Chorus", start=30, end=60)

        child = tl.partition("Chorus")

        assert tl.n_children == 1
        assert child.length.value == 30.0  # 60 - 30
        assert child.name == "Chorus"

    def test_partition_child_offset(self):
        """Partitioned child has correct offset in parent."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Verse", start=20, end=40)

        child = tl.partition("Verse")

        offset = tl.get_child_offset(child.id)
        assert offset.value == 20.0

    def test_partition_copies_events_by_default(self):
        """partition copies events within the region to the child."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 10.0,
                },
                {
                    "id": "e2",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 35.0,
                },
                {
                    "id": "e3",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 55.0,
                },
                {
                    "id": "e4",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 80.0,
                },
            ]
        )
        tl.add_region("Middle", start=30, end=60)

        child = tl.partition("Middle")

        # Child should have 2 events (e2 at 35 -> 5, e3 at 55 -> 25)
        assert child.n_events == 2

    def test_partition_adjusts_event_coordinates(self):
        """Copied events have coordinates relative to child's origin."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 45.0,
                },
            ]
        )
        tl.add_region("Section", start=40, end=60)

        child = tl.partition("Section")

        # Event at 45 in parent should be at 5 in child (45 - 40)
        events = list(child.events)
        assert len(events) == 1
        # The event coordinate should be offset-adjusted
        # Events have 'start' coordinate struct, not 'instant' directly
        event = events[0]
        start_coord = event.get("start")
        if isinstance(start_coord, dict) and "value" in start_coord:
            assert start_coord["value"] == pytest.approx(5.0)
        elif start_coord is not None:
            assert float(start_coord) == pytest.approx(5.0)
        else:
            # Fallback: check instant field
            event_instant = event.get("instant")
            if isinstance(event_instant, dict) and "value" in event_instant:
                assert event_instant["value"] == pytest.approx(5.0)
            else:
                assert float(event_instant) == pytest.approx(5.0)

    def test_partition_copy_events_false(self):
        """partition with copy_events=False creates empty child."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 35.0,
                },
            ]
        )
        tl.add_region("Section", start=30, end=60)

        child = tl.partition("Section", copy_events=False)

        assert child.n_events == 0

    def test_partition_nonexistent_region_raises(self):
        """partition raises KeyError for nonexistent region."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)

        with pytest.raises(KeyError, match="not found"):
            tl.partition("NonExistent")

    def test_partition_locked_timeline_raises(self):
        """partition raises RuntimeError on locked timeline."""
        tl = Timeline(length=100, unit=TimeUnit.seconds)
        tl.add_region("Test", start=0, end=10)
        tl._locked = True

        with pytest.raises(RuntimeError, match="locked"):
            tl.partition("Test")


# endregion


# region SegmentLine Tests


class TestSegmentLineBasics:
    """Test SegmentLine basic functionality."""

    def test_segmentline_creation(self):
        """SegmentLine can be created empty."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)
        assert sl.n_segments == 0
        assert sl.length.value == 0

    def test_append_segment_adds_contiguous_children(self):
        """append_segment adds children contiguously."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)

        s1 = ContinuousLogicalTimeline(length=4)
        s2 = ContinuousLogicalTimeline(length=4)
        s3 = ContinuousLogicalTimeline(length=4)

        sl.append_segment(s1, name="m1")
        sl.append_segment(s2, name="m2")
        sl.append_segment(s3, name="m3")

        assert sl.n_segments == 3
        assert sl.length.value == 12  # 4 + 4 + 4

    def test_segment_offsets_are_contiguous(self):
        """Segment offsets form a contiguous sequence."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)

        s1 = ContinuousLogicalTimeline(length=4)
        s2 = ContinuousLogicalTimeline(length=3)
        s3 = ContinuousLogicalTimeline(length=5)

        sl.append_segment(s1)
        sl.append_segment(s2)
        sl.append_segment(s3)

        offsets = [offset.value for _, offset, _ in sl.iter_segments()]
        assert offsets == [0, 4, 7]  # 0, 0+4, 4+3

    def test_add_child_with_wrong_offset_raises(self):
        """add_child with non-contiguous offset raises ValueError."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)
        s1 = ContinuousLogicalTimeline(length=4)
        sl.append_segment(s1)

        s2 = ContinuousLogicalTimeline(length=4)

        # Offset 5 is wrong - should be 4 (immediately after s1)
        with pytest.raises(ValueError, match="contiguous"):
            sl.add_child(s2, offset=5)

    def test_first_segment_must_start_at_zero(self):
        """First segment must have offset 0."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)
        s1 = ContinuousLogicalTimeline(length=4)

        # First segment at offset 5 is invalid
        with pytest.raises(ValueError, match="contiguous"):
            sl.add_child(s1, offset=5)

    def test_get_segment_by_index(self):
        """get_segment_by_index retrieves segments by 0-based index."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)

        s1 = ContinuousLogicalTimeline(length=4, name="first")
        s2 = ContinuousLogicalTimeline(length=4, name="second")
        s3 = ContinuousLogicalTimeline(length=4, name="third")

        sl.append_segment(s1)
        sl.append_segment(s2)
        sl.append_segment(s3)

        offset, segment = sl.get_segment_by_index(1)
        assert segment.name == "second"
        assert offset.value == 4

    def test_get_segment_by_index_out_of_range(self):
        """get_segment_by_index raises IndexError for invalid index."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)
        sl.append_segment(ContinuousLogicalTimeline(length=4))

        with pytest.raises(IndexError):
            sl.get_segment_by_index(5)

    def test_get_segment_at_coordinate(self):
        """get_segment_at finds segment containing a coordinate."""
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)

        s1 = ContinuousLogicalTimeline(length=4, name="m1")
        s2 = ContinuousLogicalTimeline(length=4, name="m2")
        s3 = ContinuousLogicalTimeline(length=4, name="m3")

        sl.append_segment(s1)
        sl.append_segment(s2)
        sl.append_segment(s3)

        # Coordinate 6 is in segment 2 (offset 4-8)
        idx, segment, _ = sl.get_segment_at(6.0)
        assert idx == 1
        assert segment.name == "m2"


class TestSegmentLineFromSegmentation:
    """Test SegmentLine.from_segmentation() factory method."""

    def test_segmentation_creates_correct_segments(self):
        """from_segmentation splits timeline at given coordinates."""
        source = ContinuousLogicalTimeline(length=100)
        sl = SegmentLine.from_segmentation(source, [0, 25, 50, 75, 100])

        assert sl.n_segments == 4
        assert sl.length.value == 100

    def test_segmentation_segment_lengths(self):
        """Segmented segments have correct lengths."""
        source = ContinuousLogicalTimeline(length=100)
        sl = SegmentLine.from_segmentation(source, [0, 30, 70, 100])

        lengths = [seg.length.value for _, _, seg in sl.iter_segments()]
        assert lengths == [30, 40, 30]  # 30-0, 70-30, 100-70

    def test_segmentation_copies_events(self):
        """from_segmentation copies events to respective segments."""
        source = ContinuousLogicalTimeline(length=100)
        source.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Note",
                    "instant": 10.0,
                },
                {
                    "id": "e2",
                    "temporal_type": "instant",
                    "event_type": "Note",
                    "instant": 35.0,
                },
                {
                    "id": "e3",
                    "temporal_type": "instant",
                    "event_type": "Note",
                    "instant": 60.0,
                },
                {
                    "id": "e4",
                    "temporal_type": "instant",
                    "event_type": "Note",
                    "instant": 90.0,
                },
            ]
        )

        sl = SegmentLine.from_segmentation(source, [0, 25, 50, 75, 100])

        # Each segment should have 1 event
        for _, _, seg in sl.iter_segments():
            assert seg.n_events == 1

    def test_segmentation_requires_at_least_two_coords(self):
        """from_segmentation requires at least 2 split coordinates."""
        source = ContinuousLogicalTimeline(length=100)

        with pytest.raises(ValueError, match="at least 2"):
            SegmentLine.from_segmentation(source, [50])

    def test_segmentation_fails_if_source_has_children(self):
        """from_segmentation fails if source already has children."""
        source = ContinuousLogicalTimeline(length=100)
        child = ContinuousLogicalTimeline(length=10)
        source.add_child(child, offset=0)

        with pytest.raises(ValueError, match="already has children"):
            SegmentLine.from_segmentation(source, [0, 50, 100])


# endregion


# region derive() Tests


class TestTimelineDerive:
    """Test Timeline.derive() - creating derivative timelines via C-maps."""

    def test_derive_creates_timeline_in_target_unit(self):
        """derive() creates a new timeline in the C-map's target unit."""
        audio = ContinuousPhysicalTimeline(length=60.0, unit=TimeUnit.seconds)

        # 2 quarters per second = 120 BPM
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="tempo",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters)

        assert score.unit == TimeUnit.quarters
        assert score.length.value == 120.0  # 60 * 2

    def test_derive_creates_correct_timeline_type(self):
        """derive() creates appropriate Timeline subclass for target domain."""
        audio = ContinuousPhysicalTimeline(length=60.0)
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters)

        # Should be ContinuousLogicalTimeline (quarters is in logical domain)
        assert isinstance(score, ContinuousLogicalTimeline)

    def test_derive_attaches_inverse_cmap(self):
        """derive() attaches inverse C-map for roundtrip conversion."""
        audio = ContinuousPhysicalTimeline(length=60.0)
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters)

        # Derived timeline should have C-map back to seconds
        inverse = score.get_conversion_map(TimeUnit.seconds)
        assert inverse is not None

        # Roundtrip test: 60 quarters -> seconds -> quarters
        seconds = inverse(60.0)  # 60 / 2 = 30
        assert seconds == pytest.approx(30.0)

    def test_derive_roundtrip_accuracy(self):
        """derive() enables accurate roundtrip conversions."""
        audio = ContinuousPhysicalTimeline(length=100.0)
        tempo_map = LinearMap(
            scalar=1.5,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters)
        inverse = score.get_conversion_map(TimeUnit.seconds)

        # Test multiple values
        test_values = [0.0, 25.0, 50.0, 75.0, 100.0]
        for original in test_values:
            quarters = tempo_map(original)
            back = inverse(quarters)
            assert back == pytest.approx(original, abs=1e-10)

    def test_derive_without_cmap_raises(self):
        """derive() raises ValueError if no C-map for target unit."""
        audio = ContinuousPhysicalTimeline(length=60.0)

        with pytest.raises(ValueError, match="No C-Map"):
            audio.derive(TimeUnit.quarters)

    def test_derive_with_custom_name(self):
        """derive() uses custom name if provided."""
        audio = ContinuousPhysicalTimeline(length=60.0)
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters, name="my_score")

        assert score.name == "my_score"

    def test_derive_copies_events_when_requested(self):
        """derive() copies and converts events when copy_events=True."""
        audio = ContinuousPhysicalTimeline(length=60.0)
        audio.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 10.0,
                },
                {
                    "id": "e2",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 30.0,
                },
            ]
        )
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters, copy_events=True)

        # Events should be copied and coordinates converted
        assert score.n_events == 2

    def test_derive_does_not_copy_events_by_default(self):
        """derive() does not copy events by default."""
        audio = ContinuousPhysicalTimeline(length=60.0)
        audio.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 10.0,
                },
            ]
        )
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        score = audio.derive(TimeUnit.quarters)

        assert score.n_events == 0


# endregion


# region get_timeline_class Tests


class TestGetTimelineClass:
    """Test the get_timeline_class() factory function."""

    def test_logical_continuous(self):
        """get_timeline_class('logical', False) returns ContinuousLogicalTimeline."""
        cls = get_timeline_class("logical", discrete=False)
        assert cls == ContinuousLogicalTimeline

    def test_logical_discrete(self):
        """get_timeline_class('logical', True) returns DiscreteLogicalTimeline."""
        from timetoalign.timelines import DiscreteLogicalTimeline

        cls = get_timeline_class("logical", discrete=True)
        assert cls == DiscreteLogicalTimeline

    def test_physical_continuous(self):
        """get_timeline_class('physical', False) returns ContinuousPhysicalTimeline."""
        cls = get_timeline_class("physical", discrete=False)
        assert cls == ContinuousPhysicalTimeline

    def test_physical_discrete(self):
        """get_timeline_class('physical', True) returns DiscretePhysicalTimeline."""
        from timetoalign.timelines import DiscretePhysicalTimeline

        cls = get_timeline_class("physical", discrete=True)
        assert cls == DiscretePhysicalTimeline

    def test_graphical_continuous(self):
        """get_timeline_class('graphical', False) returns ContinuousGraphicalTimeline."""
        from timetoalign.timelines import ContinuousGraphicalTimeline

        cls = get_timeline_class("graphical", discrete=False)
        assert cls == ContinuousGraphicalTimeline

    def test_graphical_discrete(self):
        """get_timeline_class('graphical', True) returns DiscreteGraphicalTimeline."""
        from timetoalign.timelines import DiscreteGraphicalTimeline

        cls = get_timeline_class("graphical", discrete=True)
        assert cls == DiscreteGraphicalTimeline

    def test_unknown_domain_raises(self):
        """get_timeline_class raises ValueError for unknown domain."""
        with pytest.raises(ValueError, match="Unknown domain"):
            get_timeline_class("imaginary")


# endregion


# region Integration Tests


class TestTimelineRelationshipsIntegration:
    """Integration tests combining multiple relationship concepts."""

    def test_region_to_segmentline(self):
        """Regions can be used to create a SegmentLine structure."""
        # Create a timeline representing a song
        song = ContinuousPhysicalTimeline(length=180.0, unit=TimeUnit.seconds)

        # Define song structure via regions
        song.add_region("Intro", start=0, end=30)
        song.add_region("Verse1", start=30, end=60)
        song.add_region("Chorus1", start=60, end=90)
        song.add_region("Verse2", start=90, end=120)
        song.add_region("Chorus2", start=120, end=150)
        song.add_region("Outro", start=150, end=180)

        # Partition creates children
        assert song.n_regions == 6

        intro = song.partition("Intro", copy_events=False)
        assert intro.length.value == 30.0

    def test_derive_then_add_children(self):
        """Derived timeline can have children added (same unit)."""
        # Physical timeline with tempo
        audio = ContinuousPhysicalTimeline(length=60.0)
        tempo_map = LinearMap(
            scalar=2.0,
            offset=0.0,
            source_unit=TimeUnit.seconds,
            target_unit=TimeUnit.quarters,
            uid="t",
        )
        audio.add_conversion_map(tempo_map)

        # Derive logical timeline
        score = audio.derive(TimeUnit.quarters)

        # Add children (measures) to derived timeline
        for i in range(30):
            measure = ContinuousLogicalTimeline(length=4, name=f"m{i+1}")
            score.add_child(measure, offset=i * 4)

        assert score.n_children == 30

    def test_segmentline_with_cmaps(self):
        """SegmentLine segments can have individual C-maps."""
        # Create a SegmentLine with segments having different tempos
        sl = SegmentLine(length=0, unit=TimeUnit.quarters)

        # Segment 1: 8 quarters at 120 BPM (4 seconds)
        s1 = ContinuousLogicalTimeline(length=8, name="fast")
        s1.add_conversion_map(
            LinearMap(
                scalar=0.5,  # 1 quarter = 0.5 seconds at 120 BPM
                offset=0.0,
                source_unit=TimeUnit.quarters,
                target_unit=TimeUnit.seconds,
                uid="s1_tempo",
            )
        )
        sl.append_segment(s1)

        # Segment 2: 8 quarters at 60 BPM (8 seconds)
        s2 = ContinuousLogicalTimeline(length=8, name="slow")
        s2.add_conversion_map(
            LinearMap(
                scalar=1.0,  # 1 quarter = 1 second at 60 BPM
                offset=0.0,
                source_unit=TimeUnit.quarters,
                target_unit=TimeUnit.seconds,
                uid="s2_tempo",
            )
        )
        sl.append_segment(s2)

        assert sl.length.value == 16  # 8 + 8 quarters
        # Fast section: 8 * 0.5 = 4 seconds
        # Slow section: 8 * 1.0 = 8 seconds
        # Total physical duration would be 12 seconds


# endregion
