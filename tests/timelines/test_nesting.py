"""Tests for Timeline nesting (child timelines / segments).

This module tests:
- Adding children to timelines
- Child validation (unit matching, bounds checking)
- Iterating children (sorted, depth-first, breadth-first)
- Child locking behavior
- Segment events in EventStore

Validity Rationale:
    The TTA model specifies that timelines can contain nested "children"
    (segments) that share the same coordinate type. These tests verify:
    1. Children must have matching units (type safety)
    2. Children are locked upon embedding (immutability)
    3. Children appear as interval events in the parent's EventStore
    4. Traversal orders work correctly for hierarchical access
    5. Offset coordinates are correctly managed
"""

from __future__ import annotations

import time

import pytest

from timetoalign.core import Coordinate, TimeUnit
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
    Timeline,
)
from timetoalign.timelines.base import SEGMENT_EVENT_TYPE

# region Child Validation Tests


class TestChildValidation:
    """Test validation when adding children."""

    def test_validate_child_accepts_matching_units(self):
        """Children with matching units are accepted."""
        parent = ContinuousPhysicalTimeline(length=20.0, unit=TimeUnit.seconds)
        child = ContinuousPhysicalTimeline(length=5.0, unit=TimeUnit.seconds)

        # Should not raise
        parent.validate_child(child, offset=0.0)

    def test_validate_child_rejects_mismatched_units(self):
        """Children with different units are rejected."""
        parent = ContinuousPhysicalTimeline(length=20.0, unit=TimeUnit.seconds)
        child = ContinuousPhysicalTimeline(length=5.0, unit=TimeUnit.milliseconds)

        with pytest.raises(ValueError, match="does not match"):
            parent.validate_child(child, offset=0.0)

    def test_validate_child_rejects_non_timeline(self):
        """Non-Timeline objects are rejected."""
        parent = Timeline(length=20.0)

        with pytest.raises(TypeError, match="must be a Timeline"):
            parent.validate_child("not a timeline", offset=0.0)  # type: ignore

    def test_validate_child_rejects_duplicate(self):
        """Same child cannot be added twice."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=0.0)

        with pytest.raises(ValueError, match="already a child"):
            parent.validate_child(child, offset=10.0)

    def test_validate_child_rejects_negative_offset(self):
        """Negative offsets are rejected."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)

        with pytest.raises(ValueError, match="negative"):
            parent.validate_child(child, offset=-1.0)


# endregion


# region Adding Children Tests


class TestAddChild:
    """Test add_child functionality."""

    def test_add_child_basic(self):
        """Basic child addition works."""
        parent = Timeline(length=20.0, uid="parent")
        child = Timeline(length=5.0, uid="child")

        parent.add_child(child, offset=0.0)

        assert parent.n_children == 1
        assert "child" in parent

    def test_add_child_stores_offset(self):
        """Child offset is stored correctly."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=10.0)

        offset = parent.get_child_offset("child")
        assert offset.value == 10.0
        assert offset.unit == parent.unit

    def test_add_child_locks_child(self):
        """Child is locked after being added."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0)

        assert not child.is_locked
        parent.add_child(child, offset=0.0)
        assert child.is_locked

    def test_add_child_creates_segment_event(self):
        """Adding child creates segment event in EventStore."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=10.0)

        # Check segment event exists
        all_events = parent.get_events(include_segments=True)
        assert len(all_events) == 1

        # Check segment event properties
        segment_events = parent._events.filter(event_type=SEGMENT_EVENT_TYPE)
        assert len(segment_events) == 1

    def test_add_child_auto_expands_parent(self):
        """Parent auto-expands if child exceeds bounds."""
        parent = Timeline(length=10.0)
        child = Timeline(length=5.0)

        # Child at offset 8 would end at 13
        parent.add_child(child, offset=8.0)

        assert parent.length.value == 13.0

    def test_add_child_locked_parent_raises(self):
        """Locked parent rejects children that exceed bounds."""
        parent = Timeline(length=10.0, locked=True)
        child = Timeline(length=5.0)

        with pytest.raises(ValueError, match="locked"):
            parent.add_child(child, offset=8.0)

    def test_add_child_allow_expansion_overrides_lock(self):
        """allow_expansion=True overrides parent lock."""
        parent = Timeline(length=10.0, locked=True)
        child = Timeline(length=5.0)

        parent.add_child(child, offset=8.0, allow_expansion=True)
        assert parent.length.value == 13.0

    def test_add_multiple_children(self):
        """Multiple children can be added."""
        parent = Timeline(length=20.0)
        child1 = Timeline(length=5.0, uid="c1")
        child2 = Timeline(length=5.0, uid="c2")
        child3 = Timeline(length=5.0, uid="c3")

        parent.add_child(child1, offset=0.0)
        parent.add_child(child2, offset=5.0)
        parent.add_child(child3, offset=10.0)

        assert parent.n_children == 3

    def test_add_child_with_coordinate_offset(self):
        """Offset can be a Coordinate object."""
        parent = Timeline(length=20.0, unit=TimeUnit.seconds)
        child = Timeline(length=5.0, unit=TimeUnit.seconds)
        offset = Coordinate(10.0, TimeUnit.seconds)

        parent.add_child(child, offset=offset)

        stored_offset = parent.get_child_offset(child.id)
        assert stored_offset.value == 10.0


# endregion


# region Get Child Tests


class TestGetChild:
    """Test child retrieval."""

    def test_get_child_by_id(self):
        """get_child retrieves child by ID."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="my_child")
        parent.add_child(child, offset=0.0)

        retrieved = parent.get_child("my_child")
        assert retrieved is child

    def test_get_child_nonexistent_raises(self):
        """get_child raises KeyError for unknown ID."""
        parent = Timeline(length=20.0)

        with pytest.raises(KeyError, match="nonexistent"):
            parent.get_child("nonexistent")

    def test_get_child_offset_by_id(self):
        """get_child_offset retrieves offset by ID."""
        parent = Timeline(length=20.0)
        child = Timeline(length=5.0, uid="my_child")
        parent.add_child(child, offset=7.5)

        offset = parent.get_child_offset("my_child")
        assert offset.value == 7.5

    def test_get_child_offset_nonexistent_raises(self):
        """get_child_offset raises KeyError for unknown ID."""
        parent = Timeline(length=20.0)

        with pytest.raises(KeyError, match="nonexistent"):
            parent.get_child_offset("nonexistent")


# endregion


# region Iteration Tests


class TestIterChildren:
    """Test child iteration with different traversal orders."""

    def test_iter_children_empty(self):
        """Iterating children of childless timeline yields nothing."""
        parent = Timeline(length=20.0)
        children = list(parent.iter_children())
        assert children == []

    def test_iter_children_sorted_by_offset(self):
        """Sorted order yields children by offset."""
        parent = Timeline(length=30.0)
        c1 = Timeline(length=5.0, uid="c1")
        c2 = Timeline(length=5.0, uid="c2")
        c3 = Timeline(length=5.0, uid="c3")

        # Add in non-sorted order
        parent.add_child(c2, offset=10.0)
        parent.add_child(c3, offset=20.0)
        parent.add_child(c1, offset=0.0)

        children = list(parent.iter_children(order="sorted"))
        child_ids = [c.id for _, c in children]
        assert child_ids == ["c1", "c2", "c3"]

    def test_iter_children_include_self(self):
        """include_self=True yields parent first."""
        parent = Timeline(length=20.0, uid="parent")
        child = Timeline(length=5.0, uid="child")
        parent.add_child(child, offset=0.0)

        results = list(parent.iter_children(include_self=True))
        assert len(results) == 2
        assert results[0][1].id == "parent"
        assert results[0][0].value == 0  # Parent offset is 0

    def test_iter_children_nested_sorted(self, nested_timeline_structure):
        """Sorted iteration on nested structure yields correct order."""
        parent = nested_timeline_structure

        # Sorted order: by offset, including recursion
        results = list(parent.iter_children(order="sorted"))
        offsets = [offset.value for offset, _ in results]

        # Expected: child_a(0), grandchild_a1(0+1=1), child_b(10),
        #           grandchild_b1(10+1=11), grandchild_b2(10+5=15)
        assert offsets == [0.0, 1.0, 10.0, 11.0, 15.0]

    def test_iter_children_nested_breadth_first(self, nested_timeline_structure):
        """Breadth-first iteration yields levels in order."""
        parent = nested_timeline_structure

        results = list(parent.iter_children(order="breadth_first"))
        child_ids = [c.id for _, c in results]

        # Level 1: child_a, child_b
        # Level 2: grandchild_a1, grandchild_b1, grandchild_b2
        assert child_ids[:2] == ["child_a", "child_b"]
        assert set(child_ids[2:]) == {"grandchild_a1", "grandchild_b1", "grandchild_b2"}

    def test_iter_children_nested_depth_first(self, nested_timeline_structure):
        """Depth-first iteration follows branches."""
        parent = nested_timeline_structure

        results = list(parent.iter_children(order="depth_first"))
        child_ids = [c.id for _, c in results]

        # child_a first, then its descendants, then child_b, then its descendants
        # Order within siblings may vary by dict order
        assert child_ids[0] in ["child_a", "child_b"]
        if child_ids[0] == "child_a":
            assert child_ids[1] == "grandchild_a1"

    def test_iter_children_recursion_limit(self, nested_timeline_structure):
        """recursion_limit controls depth of iteration."""
        parent = nested_timeline_structure

        # Limit 1: only direct children
        results_1 = list(parent.iter_children(recursion_limit=1))
        assert len(results_1) == 2  # child_a, child_b

        # Limit 2: children and grandchildren
        results_2 = list(parent.iter_children(recursion_limit=2))
        assert len(results_2) == 5  # 2 children + 3 grandchildren

    def test_iter_children_recursion_limit_zero(self, nested_timeline_structure):
        """recursion_limit=0 yields nothing (unless include_self)."""
        parent = nested_timeline_structure

        results = list(parent.iter_children(recursion_limit=0))
        assert results == []

        results_with_self = list(
            parent.iter_children(recursion_limit=0, include_self=True)
        )
        assert len(results_with_self) == 1

    def test_iter_children_offsets_are_absolute(self, nested_timeline_structure):
        """Offsets in iteration are relative to the root parent."""
        parent = nested_timeline_structure

        results = dict(
            (c.id, offset.value) for offset, c in parent.iter_children(order="sorted")
        )

        # grandchild_a1 is at offset 1 within child_a, which is at offset 0
        # So absolute offset is 0 + 1 = 1
        assert results["grandchild_a1"] == 1.0

        # grandchild_b1 is at offset 1 within child_b, which is at offset 10
        # So absolute offset is 10 + 1 = 11
        assert results["grandchild_b1"] == 11.0


# endregion


# region Unit Validation Tests


class TestUnitValidation:
    """Test that unit mismatches are caught."""

    def test_logical_cannot_contain_physical(self):
        """Logical timeline cannot contain physical timeline."""
        logical = ContinuousLogicalTimeline(length=8.0, unit=TimeUnit.quarters)
        physical = ContinuousPhysicalTimeline(length=5.0, unit=TimeUnit.seconds)

        with pytest.raises(ValueError, match="does not match"):
            logical.add_child(physical, offset=0.0)

    def test_physical_cannot_contain_logical(self):
        """Physical timeline cannot contain logical timeline."""
        physical = ContinuousPhysicalTimeline(length=20.0, unit=TimeUnit.seconds)
        logical = ContinuousLogicalTimeline(length=4.0, unit=TimeUnit.quarters)

        with pytest.raises(ValueError, match="does not match"):
            physical.add_child(logical, offset=0.0)

    def test_same_domain_different_unit_rejected(self):
        """Same domain but different units are rejected."""
        seconds_tl = ContinuousPhysicalTimeline(length=20.0, unit=TimeUnit.seconds)
        ms_tl = ContinuousPhysicalTimeline(length=5000.0, unit=TimeUnit.milliseconds)

        with pytest.raises(ValueError, match="does not match"):
            seconds_tl.add_child(ms_tl, offset=0.0)

    def test_discrete_and_continuous_same_domain_rejected(self):
        """Discrete and continuous timelines with different units rejected."""
        ticks_tl = DiscreteLogicalTimeline(length=1920, unit=TimeUnit.ticks)
        quarters_tl = ContinuousLogicalTimeline(length=4.0, unit=TimeUnit.quarters)

        with pytest.raises(ValueError, match="does not match"):
            ticks_tl.add_child(quarters_tl, offset=0)


# endregion


# region Performance Tests


class TestNestingPerformance:
    """Performance tests for nesting operations."""

    def test_add_many_children_performance(self, profiler):
        """Benchmark adding many children."""
        n_children = 1000
        parent = Timeline(length=float(n_children * 2))
        children = [Timeline(length=1.0, uid=f"c_{i}") for i in range(n_children)]

        start = time.perf_counter()
        for i, child in enumerate(children):
            parent.add_child(child, offset=float(i * 2))
        elapsed = time.perf_counter() - start

        profiler.record("add_1000_children", elapsed)

        assert parent.n_children == n_children
        # Should complete in reasonable time
        assert elapsed < 10.0, f"Adding {n_children} children took {elapsed:.2f}s"

    def test_iterate_deep_hierarchy_performance(self, profiler):
        """Benchmark iterating a deep hierarchy."""
        # Create a chain of 100 nested timelines
        depth = 100
        root = Timeline(length=float(depth), uid="root")
        current = root

        for i in range(depth - 1):
            child = Timeline(length=float(depth - i - 1), uid=f"level_{i + 1}")
            current.add_child(child, offset=1.0)
            current = child

        start = time.perf_counter()
        results = list(root.iter_children(order="depth_first"))
        elapsed = time.perf_counter() - start

        profiler.record("iterate_depth_100", elapsed)

        assert len(results) == depth - 1
        # Should be fast even for deep hierarchies
        assert elapsed < 1.0, f"Iterating depth {depth} took {elapsed:.2f}s"


# endregion


# region Use Conversion Map Tests


class TestAddChildWithConversionMap:
    """Test add_child with use_conversion_map parameter.

    When the child uses a different unit than the parent, the
    ``use_conversion_map`` parameter finds a C-Map on the parent,
    inverts it, and derives a converted copy of the child in the
    parent's unit.
    """

    def test_auto_select_conversion_map(self):
        """use_conversion_map=True auto-selects parent's C-Map."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=10.0, unit=TimeUnit.seconds, uid="notes"
        )
        child.add_events(
            [
                {"event_type": "Note", "start": 0.0, "end": 0.5},
                {"event_type": "Note", "start": 1.0, "end": 1.5},
            ]
        )

        parent.add_child(child, offset=0, use_conversion_map=True)

        assert parent.n_children == 1
        converted = parent.get_child("notes[samples]")
        assert converted.unit == TimeUnit.samples
        assert converted.length.value == 441000.0

    def test_converted_child_has_correct_id_and_name(self):
        """Converted child ID is '{original}[{parent_unit}]'."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="my_notes"
        )

        parent.add_child(child, offset=0, use_conversion_map=True)

        converted = parent.get_child("my_notes[samples]")
        assert converted.id == "my_notes[samples]"
        assert "samples" in converted.name

    def test_converted_child_events_have_correct_coordinates(self):
        """Event coordinates are converted from child unit to parent unit."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=10.0, unit=TimeUnit.seconds, uid="notes"
        )
        child.add_events(
            [
                {"event_type": "Note", "start": 1.0, "end": 2.0},
            ]
        )

        parent.add_child(child, offset=0, use_conversion_map=True)

        converted = parent.get_child("notes[samples]")
        events = list(converted._events)
        assert len(events) == 1
        event = events[0]
        # 1.0 seconds * 44100 = 44100 samples
        start_val = event["start"]
        if isinstance(start_val, dict):
            start_val = start_val["value"]
        assert start_val == pytest.approx(44100.0)
        # 2.0 seconds * 44100 = 88200 samples
        end_val = event["end"]
        if isinstance(end_val, dict):
            end_val = end_val["value"]
        assert end_val == pytest.approx(88200.0)

    def test_original_child_is_not_modified(self):
        """The original child timeline is not locked or mutated."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        parent.add_child(child, offset=0, use_conversion_map=True)

        # Original child should not be locked (the converted copy is)
        assert not child.is_locked
        assert child.unit == TimeUnit.seconds
        assert child.length.value == 5.0

    def test_use_conversion_map_by_string_target_unit(self):
        """use_conversion_map='seconds' finds the map by target unit name."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        parent.add_child(child, offset=0, use_conversion_map="seconds")

        assert parent.n_children == 1
        assert "notes[samples]" in parent

    def test_use_conversion_map_by_cmap_object(self):
        """use_conversion_map accepts a ConversionMap object directly."""
        from timetoalign.maps.convenience import SamplesToSeconds

        cmap = SamplesToSeconds(sample_rate=44100)
        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        # Attach the map (so parent knows about it for timestamp system)
        parent.add_conversion_map(cmap)

        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        parent.add_child(child, offset=0, use_conversion_map=cmap)

        assert parent.n_children == 1

    def test_no_conversion_map_raises_on_unit_mismatch(self):
        """Without use_conversion_map, mismatched units still raise."""
        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        with pytest.raises(ValueError, match="does not match"):
            parent.add_child(child, offset=0)

    def test_auto_select_raises_when_no_cmap_matches(self):
        """use_conversion_map=True raises if no C-Map targets child's unit."""
        parent = Timeline(length=100, unit=TimeUnit.samples, uid="audio")
        # No conversion map attached!
        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        with pytest.raises(ValueError, match="no C-Map"):
            parent.add_child(child, offset=0, use_conversion_map=True)

    def test_same_unit_child_ignores_conversion_map(self):
        """If units already match, use_conversion_map is a no-op."""
        parent = Timeline(length=20.0, unit=TimeUnit.seconds, uid="parent")
        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="child"
        )

        # Even with use_conversion_map=True, same-unit child is added as-is
        parent.add_child(child, offset=0, use_conversion_map=True)

        assert parent.n_children == 1
        # The child is added with its original ID (no [unit] suffix)
        assert "child" in parent

    def test_allow_expansion_works_with_conversion(self):
        """allow_expansion works when combined with use_conversion_map."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=44100, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        # Child in seconds is 5s = 220500 samples, exceeds parent length
        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        parent.add_child(child, offset=0, use_conversion_map=True, allow_expansion=True)

        # Parent should have expanded
        assert parent.length.value == 220500.0
        assert parent.n_children == 1

    def test_converted_child_is_locked(self):
        """The converted copy (not the original) is locked after embedding."""
        from timetoalign.maps.convenience import SamplesToSeconds

        parent = Timeline(length=441000, unit=TimeUnit.samples, uid="audio")
        parent.add_conversion_map(SamplesToSeconds(sample_rate=44100))

        child = ContinuousPhysicalTimeline(
            length=5.0, unit=TimeUnit.seconds, uid="notes"
        )

        parent.add_child(child, offset=0, use_conversion_map=True)

        converted = parent.get_child("notes[samples]")
        assert converted.is_locked
        assert not child.is_locked


# endregion
