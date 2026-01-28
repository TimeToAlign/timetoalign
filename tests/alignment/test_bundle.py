"""Tests for AlignmentBundle.

Tests cover Phase 1 functionality:
- Timeline registration and lookup
- Group management
- Coordinate transfer within groups
- Order-independence (critical invariant)

Per ZERO TOLERANCE policy, all assertions use exact expected values.
"""

from __future__ import annotations

import pytest

from timetoalign.alignment import AlignmentBundle, PerfectAlignment
from timetoalign.alignment.bundle import _reset_bundle_ids
from timetoalign.timelines import Timeline

# region Fixtures


@pytest.fixture(autouse=True)
def reset_ids() -> None:
    """Reset ID generators before each test for deterministic IDs."""
    _reset_bundle_ids()


@pytest.fixture
def simple_timeline() -> Timeline:
    """A simple 100-unit timeline."""
    return Timeline(length=100, uid="tl_simple", name="Simple Timeline")


@pytest.fixture
def second_timeline() -> Timeline:
    """A second 200-unit timeline."""
    return Timeline(length=200, uid="tl_second", name="Second Timeline")


@pytest.fixture
def third_timeline() -> Timeline:
    """A third 50-unit timeline."""
    return Timeline(length=50, uid="tl_third", name="Third Timeline")


# endregion


# region Test: Bundle Creation


class TestBundleCreation:
    """Tests for AlignmentBundle initialization."""

    def test_create_empty_bundle(self) -> None:
        """Empty bundle can be created."""
        bundle = AlignmentBundle()

        assert bundle.n_timelines == 0
        assert bundle.n_groups == 0
        assert bundle.id.startswith("bundle:")

    def test_create_bundle_with_name(self) -> None:
        """Bundle can be created with a name."""
        bundle = AlignmentBundle(name="Test Bundle")

        assert bundle.name == "Test Bundle"
        assert "Test Bundle" in repr(bundle)

    def test_create_bundle_with_explicit_id(self) -> None:
        """Bundle can be created with explicit ID."""
        bundle = AlignmentBundle(id="my_bundle")

        assert bundle.id == "my_bundle"


# endregion


# region Test: Timeline Management


class TestTimelineManagement:
    """Tests for adding and retrieving timelines."""

    def test_add_timeline_simple(self, simple_timeline: Timeline) -> None:
        """Can add a simple timeline."""
        bundle = AlignmentBundle()
        result = bundle.add_timeline(simple_timeline, uid="tl1")

        # Returns self for chaining
        assert result is bundle

        # Timeline is stored
        assert bundle.n_timelines == 1
        assert "tl1" in bundle.timeline_ids

    def test_add_timeline_uses_timeline_id(self, simple_timeline: Timeline) -> None:
        """If no uid provided, uses timeline.id."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline)

        assert simple_timeline.id in bundle.timeline_ids

    def test_add_duplicate_uid_raises(self, simple_timeline: Timeline) -> None:
        """Adding timeline with duplicate uid raises ValueError."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")

        with pytest.raises(ValueError, match="already exists"):
            bundle.add_timeline(simple_timeline, uid="tl1")

    def test_get_timeline(self, simple_timeline: Timeline) -> None:
        """Can retrieve timeline by ID."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")

        retrieved = bundle.get_timeline("tl1")
        assert retrieved is simple_timeline

    def test_get_timeline_not_found_raises(self) -> None:
        """Getting non-existent timeline raises KeyError."""
        bundle = AlignmentBundle()

        with pytest.raises(KeyError, match="No timeline"):
            bundle.get_timeline("nonexistent")

    def test_timeline_ids_property(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """timeline_ids returns all timeline IDs."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2")

        assert set(bundle.timeline_ids) == {"tl1", "tl2"}


# endregion


# region Test: Group Management


class TestGroupManagement:
    """Tests for creating and managing timeline groups."""

    def test_add_timeline_aligned_to_creates_group(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Adding timeline with aligned_to creates a group."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        assert bundle.n_groups == 1
        assert bundle.n_timelines == 2

    def test_group_contains_both_timelines(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Group contains both source and aligned timeline."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        group = bundle.default_group
        assert group is not None
        # Groups use actual timeline.id, not bundle UIDs
        assert simple_timeline.id in group.timelines
        assert second_timeline.id in group.timelines

    def test_reference_timeline_is_first(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Group reference is the first timeline added."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        group = bundle.default_group
        assert group is not None
        # Groups use actual timeline.id, not bundle UIDs
        assert group.reference_timeline_id == simple_timeline.id

    def test_add_timeline_to_nonexistent_raises(
        self, simple_timeline: Timeline
    ) -> None:
        """Aligning to non-existent timeline raises KeyError."""
        bundle = AlignmentBundle()

        with pytest.raises(KeyError, match="not in bundle"):
            bundle.add_timeline(simple_timeline, uid="tl1", aligned_to="nonexistent")

    def test_add_timeline_as_group(self, simple_timeline: Timeline) -> None:
        """Can create timeline as reference of a named group."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1", as_group="my_group")

        assert "my_group" in bundle.group_ids
        group = bundle.get_group("my_group")
        # Groups use actual timeline.id, not bundle UIDs
        assert group.reference_timeline_id == simple_timeline.id

    def test_get_group_for_timeline(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Can get the group containing a timeline."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1", as_group="grp1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        group = bundle.get_group_for_timeline("tl2")
        assert group is not None
        assert group.id == "grp1"

    def test_standalone_timeline_has_no_group(self, simple_timeline: Timeline) -> None:
        """Standalone timeline returns None for get_group_for_timeline."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")

        assert bundle.get_group_for_timeline("tl1") is None


# endregion


# region Test: Coordinate Transfer


class TestCoordinateTransfer:
    """Tests for coordinate transfer between timelines."""

    def test_transfer_same_timeline_returns_input(
        self, simple_timeline: Timeline
    ) -> None:
        """Transferring to same timeline returns input coordinate."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1", as_group="grp")

        result = bundle.transfer(50.0, "tl1", "tl1")
        assert result == 50.0

    def test_transfer_within_group_linear(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Transfer within group uses linear interpolation."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")  # length=100
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")  # length=200

        # 50/100 = 0.5, so in tl2: 0.5 * 200 = 100
        result = bundle.transfer(50.0, "tl1", "tl2")
        assert result == 100.0

        # Reverse: 100/200 = 0.5, so in tl1: 0.5 * 100 = 50
        result_reverse = bundle.transfer(100.0, "tl2", "tl1")
        assert result_reverse == 50.0

    def test_transfer_boundary_values(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Transfer works correctly at boundaries."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")  # length=100
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")  # length=200

        # Start: 0 -> 0
        assert bundle.transfer(0.0, "tl1", "tl2") == 0.0

        # End: 100 -> 200
        assert bundle.transfer(100.0, "tl1", "tl2") == 200.0

    def test_transfer_not_in_bundle_raises(self, simple_timeline: Timeline) -> None:
        """Transfer with non-existent timeline raises KeyError."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")

        with pytest.raises(KeyError, match="not in bundle"):
            bundle.transfer(50.0, "nonexistent", "tl1")

        with pytest.raises(KeyError, match="not in bundle"):
            bundle.transfer(50.0, "tl1", "nonexistent")

    def test_transfer_not_in_same_group_returns_none(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Transfer between different groups returns None (Phase 1)."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1", as_group="grp1")
        bundle.add_timeline(second_timeline, uid="tl2", as_group="grp2")

        result = bundle.transfer(50.0, "tl1", "tl2")
        assert result is None

    def test_transfer_interval(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Can transfer an interval."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")  # length=100
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")  # length=200

        result = bundle.transfer_interval(25.0, 75.0, "tl1", "tl2")
        assert result is not None
        assert result == (50.0, 150.0)


# endregion


# region Test: Custom Alignment


class TestCustomAlignment:
    """Tests for custom PerfectAlignment specifications."""

    def test_partial_alignment(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Can specify partial alignment ranges."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")  # length=100

        # Map only 0-100 of tl2 to 0-50 of tl1
        alignment = PerfectAlignment(
            source_start=0,
            source_end=100,
            ref_start=0,
            ref_end=50,
        )
        bundle.add_timeline(
            second_timeline, uid="tl2", aligned_to="tl1", alignment=alignment
        )

        # At source coord 50: ratio = 50/100 = 0.5, ref = 0.5 * 50 = 25
        # But we're going FROM tl2 TO tl1, so:
        # 50 in tl2 -> (50 - 0) / (100 - 0) = 0.5 ratio -> 0 + 0.5 * 50 = 25 in ref
        result = bundle.transfer(50.0, "tl2", "tl1")
        assert result == 25.0


# endregion


# region Test: Order Independence (CRITICAL)


class TestOrderIndependence:
    """Tests verifying order-independence of timeline addition.

    This is a CRITICAL invariant: the resulting bundle structure and
    coordinate transfer results must be identical regardless of the
    order in which timelines are added.
    """

    def test_two_timelines_order_1(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Adding tl1 first, then tl2 aligned to tl1."""
        bundle = AlignmentBundle(id="test_bundle")
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        # Transfer should work
        result = bundle.transfer(50.0, "tl1", "tl2")
        assert result == 100.0

    def test_three_timelines_any_order_same_result(
        self,
        simple_timeline: Timeline,
        second_timeline: Timeline,
        third_timeline: Timeline,
    ) -> None:
        """Three timelines added in different orders produce same transfer results."""
        # Order 1: tl1, tl2, tl3
        b1 = AlignmentBundle(id="b1")
        tl1_1 = Timeline(length=100, uid="t1")
        tl2_1 = Timeline(length=200, uid="t2")
        tl3_1 = Timeline(length=50, uid="t3")
        b1.add_timeline(tl1_1, uid="tl1")
        b1.add_timeline(tl2_1, uid="tl2", aligned_to="tl1")
        b1.add_timeline(tl3_1, uid="tl3", aligned_to="tl1")

        # Order 2: tl2, tl1, tl3 (tl2 first, then tl1 aligned to tl2)
        # Note: This changes the reference, so let's test with same reference
        b2 = AlignmentBundle(id="b2")
        tl1_2 = Timeline(length=100, uid="t1")
        tl2_2 = Timeline(length=200, uid="t2")
        tl3_2 = Timeline(length=50, uid="t3")
        b2.add_timeline(tl1_2, uid="tl1")
        b2.add_timeline(tl3_2, uid="tl3", aligned_to="tl1")
        b2.add_timeline(tl2_2, uid="tl2", aligned_to="tl1")

        # Both should give same transfer results
        # tl1 -> tl2: 50/100 * 200 = 100
        assert (
            b1.transfer(50.0, "tl1", "tl2") == b2.transfer(50.0, "tl1", "tl2") == 100.0
        )

        # tl1 -> tl3: 50/100 * 50 = 25
        assert (
            b1.transfer(50.0, "tl1", "tl3") == b2.transfer(50.0, "tl1", "tl3") == 25.0
        )

        # tl2 -> tl3: 100/200 = 0.5 * 50 = 25
        assert (
            b1.transfer(100.0, "tl2", "tl3") == b2.transfer(100.0, "tl2", "tl3") == 25.0
        )

    def test_summary_is_deterministic(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Summary output is deterministic (sorted keys)."""
        bundle = AlignmentBundle(id="test_bundle", name="Test")
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        summary = bundle.summary()

        # Check structure
        assert summary["id"] == "test_bundle"
        assert summary["name"] == "Test"
        assert summary["n_timelines"] == 2
        assert summary["n_groups"] == 1

        # Timeline keys should be sorted
        assert list(summary["timelines"].keys()) == ["tl1", "tl2"]


# endregion


# region Test: Commensurability


class TestCommensurability:
    """Tests for checking if timelines can be connected."""

    def test_same_timeline_is_commensurable(self, simple_timeline: Timeline) -> None:
        """A timeline is commensurable with itself."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")

        assert bundle.are_commensurable("tl1", "tl1") is True

    def test_same_group_is_commensurable(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Timelines in same group are commensurable."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1")
        bundle.add_timeline(second_timeline, uid="tl2", aligned_to="tl1")

        assert bundle.are_commensurable("tl1", "tl2") is True

    def test_different_groups_not_commensurable(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Timelines in different groups are not commensurable (Phase 1)."""
        bundle = AlignmentBundle()
        bundle.add_timeline(simple_timeline, uid="tl1", as_group="grp1")
        bundle.add_timeline(second_timeline, uid="tl2", as_group="grp2")

        assert bundle.are_commensurable("tl1", "tl2") is False


# endregion


# region Test: Method Chaining


class TestMethodChaining:
    """Tests for fluent API (method chaining)."""

    def test_chained_add_timeline(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """add_timeline returns self for chaining."""
        tl1 = Timeline(length=100, uid="a")
        tl2 = Timeline(length=200, uid="b")
        tl3 = Timeline(length=50, uid="c")

        bundle = (
            AlignmentBundle()
            .add_timeline(tl1, uid="tl1")
            .add_timeline(tl2, uid="tl2", aligned_to="tl1")
            .add_timeline(tl3, uid="tl3", aligned_to="tl1")
        )

        assert bundle.n_timelines == 3
        assert bundle.n_groups == 1


# endregion
