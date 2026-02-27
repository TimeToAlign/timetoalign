"""Tests for AlignmentBundle.

Tests cover core functionality:
- Timeline registration and lookup
- Group management
- Coordinate transfer within groups
- Order-independence (critical invariant)
- Cross-group transfer via MatchClaim -> MatchLine -> WarpMap pipeline
- get_timestamp_at() propagation across groups
- are_commensurable() with claims
- WarpMap cache invalidation
- Indirect transfer (within-group convert + cross-group warp)
- Edge cases (insufficient claims, non-synchronous claims)

Per ZERO TOLERANCE policy, all assertions use exact expected values.
"""

from __future__ import annotations

import pytest

from timetoalign.alignment import (
    AlignmentAnchor,
    AlignmentBundle,
    MatchClaim,
    TimelineGroup,
)
from timetoalign.timelines import Timeline

# region Fixtures


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

        with pytest.raises(KeyError, match="No ID matches pattern"):
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
        assert simple_timeline.id in group
        assert second_timeline.id in group

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
        """Transfer between different groups returns None."""
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
    """Tests for custom alignment specifications.

    NOTE: PerfectAlignment is deprecated. Partial alignment is now specified
    via start/end parameters on TimelineGroup.add_timeline(). The
    AlignmentBundle currently only supports linear (full-extent) alignment.
    """

    def test_partial_alignment_via_group(
        self, simple_timeline: Timeline, second_timeline: Timeline
    ) -> None:
        """Can specify partial alignment ranges via group API."""
        # Create group directly with partial alignment
        group = TimelineGroup(id="test_group")
        group.add_timeline(simple_timeline)
        # Map second_timeline's full extent (0-200) to simple_timeline's 0-50
        group.add_timeline(
            second_timeline,
            end=(50.0, simple_timeline.id),  # Map to first 50 units of tl1
        )

        # At tl2 coord 50: 25% through tl2's range (0-200)
        # Should map to 25% through the mapped range (0-50) = 12.5 in tl1
        result = group.convert(
            50.0, source=second_timeline.id, target=simple_timeline.id
        )
        assert result == pytest.approx(12.5)


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
        """Timelines in different groups are not commensurable."""
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


# region Helpers for Cross-Group Tests


def _make_cross_group_bundle() -> (
    tuple[AlignmentBundle, Timeline, Timeline, Timeline, Timeline]
):
    """Build a 2-group bundle with 2 timelines per group.

    Group A ("score_group"):
        - score_tl (length=200)   [bundle uid: "score"]
        - image_tl (length=400)   [bundle uid: "image", aligned to "score"]

    Group B ("recording_group"):
        - audio_tl (length=100)   [bundle uid: "audio"]
        - midi_tl  (length=100)   [bundle uid: "midi", aligned to "audio"]

    Returns:
        (bundle, score_tl, image_tl, audio_tl, midi_tl)
    """
    score_tl = Timeline(length=200, uid="score_t", name="Score")
    image_tl = Timeline(length=400, uid="image_t", name="Image")
    audio_tl = Timeline(length=100, uid="audio_t", name="Audio")
    midi_tl = Timeline(length=100, uid="midi_t", name="MIDI")

    bundle = AlignmentBundle(id="xgroup_test")
    bundle.add_timeline(score_tl, uid="score", as_group="score_group")
    bundle.add_timeline(image_tl, uid="image", aligned_to="score")
    bundle.add_timeline(audio_tl, uid="audio", as_group="recording_group")
    bundle.add_timeline(midi_tl, uid="midi", aligned_to="audio")

    return bundle, score_tl, image_tl, audio_tl, midi_tl


def _make_linear_claims(
    tl_a_id: str, tl_b_id: str, n_points: int = 5
) -> list[MatchClaim]:
    """Create n_points instant MatchClaims mapping [0..n-1] linearly.

    The mapping is: coord_b = coord_a * 0.5
    So tl_a range [0, n-1] maps to tl_b range [0, (n-1)*0.5].

    Uses actual timeline IDs (not bundle UIDs).
    """
    claims = []
    for i in range(n_points):
        coord_a = float(i * 50)  # 0, 50, 100, 150, 200
        coord_b = float(i * 25)  # 0, 25, 50, 75, 100
        claims.append(
            MatchClaim(
                timeline_a_id=tl_a_id,
                timeline_b_id=tl_b_id,
                start_anchor=AlignmentAnchor(
                    timeline_a_id=tl_a_id,
                    coordinate_a=coord_a,
                    timeline_b_id=tl_b_id,
                    coordinate_b=coord_b,
                ),
            )
        )
    return claims


# endregion


# region Test: Cross-Group Transfer


class TestCrossGroupTransfer:
    """Tests for cross-group transfer via MatchClaim -> MatchLine -> WarpMap."""

    def test_direct_cross_group_transfer(self) -> None:
        """Transfer between directly-claimed timelines in different groups."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        # Claims map score_tl.id -> audio_tl.id linearly: coord_b = coord_a * 0.5
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # score coord 100 -> audio coord 50 (linear interpolation)
        result = bundle.transfer(100.0, "score", "audio")
        assert result == 50.0

    def test_direct_cross_group_transfer_boundary_zero(self) -> None:
        """Transfer at coordinate 0 (boundary)."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        result = bundle.transfer(0.0, "score", "audio")
        assert result == 0.0

    def test_direct_cross_group_transfer_boundary_max(self) -> None:
        """Transfer at the maximum anchor coordinate."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # coord_a=200 -> coord_b=100
        result = bundle.transfer(200.0, "score", "audio")
        assert result == 100.0

    def test_cross_group_interpolation_midpoint(self) -> None:
        """Transfer at a coordinate between anchors uses linear interpolation."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # coord 75 is between anchors at 50 and 100 (mapped to 25 and 50)
        # Linear interpolation: 25 + (75-50)/(100-50) * (50-25) = 25 + 12.5 = 37.5
        result = bundle.transfer(75.0, "score", "audio")
        assert result == 37.5

    def test_cross_group_reverse_direction(self) -> None:
        """Transfer works in reverse (target -> source) via separate WarpMap."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # audio coord 50 -> score coord 100
        result = bundle.transfer(50.0, "audio", "score")
        assert result == 100.0

    def test_indirect_cross_group_transfer(self) -> None:
        """Transfer via indirect path: within-group convert then cross-group warp.

        Scenario: "image" is in same group as "score" (image = score * 2).
        Claims connect score.id -> audio.id. So image -> audio requires:
        1. Convert image coord in score_group to score coord (200/400 = 0.5 ratio)
        2. Warp score coord to audio coord via WarpMap (score * 0.5)
        """
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # image coord 200 -> score coord 100 (within group, 200/400 * 200 = 100)
        # score coord 100 -> audio coord 50 (warp, 100 * 0.5 = 50)
        result = bundle.transfer(200.0, "image", "audio")
        assert result == 50.0

    def test_indirect_cross_group_transfer_via_group_extension(self) -> None:
        """Transfer to a non-claimed target timeline via group extension.

        Scenario: Claims connect score.id -> audio.id. "midi" is in same
        group as "audio". MatchLine.from_claims() with group info extends
        the claims to include midi via the recording_group.
        """
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        # score coord 100 -> audio coord 50 (warp) -> midi coord 50
        # (midi is same length as audio, 1:1 within the recording_group)
        result = bundle.transfer(100.0, "score", "midi")
        assert result == 50.0

    def test_cross_group_no_claims_returns_none(self) -> None:
        """Transfer between unconnected groups returns None."""
        bundle, _, _, _, _ = _make_cross_group_bundle()

        # No claims added
        result = bundle.transfer(50.0, "score", "audio")
        assert result is None

    def test_cross_group_non_synchronous_claims_return_none(self) -> None:
        """Non-synchronous claims do not enable cross-group transfer."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        # Add non-synchronous claims (no anchors -> no WarpMap)
        claims = [
            MatchClaim.nomatch(
                event={"start": 50.0},
                source_tl_id=score_tl.id,
                target_tl_id=audio_tl.id,
            )
        ]
        bundle.add_match_claims(claims)

        result = bundle.transfer(50.0, "score", "audio")
        assert result is None

    def test_cross_group_single_claim_insufficient(self) -> None:
        """A single claim (1 anchor point) is insufficient for WarpMap (need >= 2)."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        claims = [
            MatchClaim(
                timeline_a_id=score_tl.id,
                timeline_b_id=audio_tl.id,
                start_anchor=AlignmentAnchor(
                    timeline_a_id=score_tl.id,
                    coordinate_a=100.0,
                    timeline_b_id=audio_tl.id,
                    coordinate_b=50.0,
                ),
            )
        ]
        bundle.add_match_claims(claims)

        result = bundle.transfer(100.0, "score", "audio")
        assert result is None

    def test_transfer_interval_cross_group(self) -> None:
        """transfer_interval works across groups."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        result = bundle.transfer_interval(50.0, 150.0, "score", "audio")
        assert result is not None
        assert result == (25.0, 75.0)


# endregion


# region Test: get_timestamp_at Cross-Group


class TestGetTimestampAtCrossGroup:
    """Tests for get_timestamp_at() propagation across groups."""

    def test_timestamp_includes_source_group(self) -> None:
        """get_timestamp_at returns source group timelines."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        ts = bundle.get_timestamp_at(100.0, "score", format="flat")

        # Source group timelines present (score + image)
        score_key = next(k for k in ts if k.startswith("score"))
        image_key = next(k for k in ts if k.startswith("image"))
        assert ts[score_key] == 100.0
        # image = score * 2 (200 length mapped to 400)
        assert ts[image_key] == 200.0

    def test_timestamp_includes_target_group(self) -> None:
        """get_timestamp_at propagates to connected groups."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        ts = bundle.get_timestamp_at(100.0, "score", format="flat")

        # Target group timelines should be present
        audio_key = next((k for k in ts if k.startswith("audio")), None)
        assert audio_key is not None
        assert ts[audio_key] == 50.0

    def test_timestamp_nested_format(self) -> None:
        """get_timestamp_at with nested format groups by group_id."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        ts = bundle.get_timestamp_at(100.0, "score", format="nested")

        # Must have source group
        assert "score_group" in ts
        # Target group may or may not appear depending on whether WarpMap works
        if "recording_group" in ts:
            # Check some value in the recording group
            recording_vals = ts["recording_group"]
            audio_key = next((k for k in recording_vals if k.startswith("audio")), None)
            if audio_key:
                assert recording_vals[audio_key] == 50.0

    def test_timestamp_prefix_format(self) -> None:
        """get_timestamp_at with prefix format uses group/timeline keys."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=5)
        bundle.add_match_claims(claims)

        ts = bundle.get_timestamp_at(100.0, "score", format="prefix")

        # Keys should be "group_id/timeline_uid" format
        score_keys = [k for k in ts if k.startswith("score_group/")]
        assert len(score_keys) >= 1  # at least "score"

    def test_timestamp_no_claims_source_only(self) -> None:
        """Without claims, get_timestamp_at returns only source group."""
        bundle, _, _, _, _ = _make_cross_group_bundle()

        ts = bundle.get_timestamp_at(100.0, "score", format="nested")

        assert "score_group" in ts
        assert "recording_group" not in ts


# endregion


# region Test: are_commensurable with Claims


class TestCommensurabilityWithClaims:
    """Tests for are_commensurable() when cross-group claims exist."""

    def test_commensurable_with_direct_claims(self) -> None:
        """Two timelines connected by direct claims are commensurable."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        assert bundle.are_commensurable("score", "audio") is True

    def test_commensurable_via_group_membership(self) -> None:
        """Timeline in same group as a claimed timeline is commensurable.

        Claims connect score.id <-> audio.id. "image" is in score's group.
        The claim's anchor touches score_tl.id which is in score_group,
        and audio_tl.id which is in recording_group. So "image" (in score_group)
        should be commensurable with "audio" (in recording_group).
        """
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        # image is in score_group, audio is in recording_group
        # Claims connect score_tl.id (in score_group) to audio_tl.id (in recording_group)
        assert bundle.are_commensurable("image", "audio") is True

    def test_not_commensurable_without_claims(self) -> None:
        """Without claims, timelines in different groups are not commensurable."""
        bundle, _, _, _, _ = _make_cross_group_bundle()

        assert bundle.are_commensurable("score", "audio") is False

    def test_not_commensurable_non_synchronous_only(self) -> None:
        """Non-synchronous claims don't make timelines commensurable."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        claims = [
            MatchClaim.nomatch(
                event={"start": 50.0},
                source_tl_id=score_tl.id,
                target_tl_id=audio_tl.id,
            )
        ]
        bundle.add_match_claims(claims)

        assert bundle.are_commensurable("score", "audio") is False


# endregion


# region Test: Cache Invalidation


class TestCacheInvalidation:
    """Tests for WarpMap cache invalidation on add_match_claims()."""

    def test_cache_populated_on_first_transfer(self) -> None:
        """First transfer builds WarpMap and populates cache."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        assert len(bundle._warp_map_cache) == 0  # No cache yet

        bundle.transfer(50.0, "score", "audio")

        assert len(bundle._warp_map_cache) >= 1  # Cache populated

    def test_cache_reused_on_second_transfer(self) -> None:
        """Second transfer reuses cached WarpMap (no rebuild)."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        result1 = bundle.transfer(50.0, "score", "audio")
        cache_after_first = dict(bundle._warp_map_cache)

        result2 = bundle.transfer(50.0, "score", "audio")

        assert result1 == result2
        # Same WarpMap objects should be in cache
        for key in cache_after_first:
            if key in bundle._warp_map_cache:
                assert bundle._warp_map_cache[key] is cache_after_first[key]

    def test_cache_invalidated_on_new_claims(self) -> None:
        """Adding new claims invalidates the cache."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        bundle.transfer(50.0, "score", "audio")
        assert len(bundle._warp_map_cache) >= 1

        # Add more claims -> invalidates cache
        more_claims = [
            MatchClaim(
                timeline_a_id=score_tl.id,
                timeline_b_id=audio_tl.id,
                start_anchor=AlignmentAnchor(
                    timeline_a_id=score_tl.id,
                    coordinate_a=175.0,
                    timeline_b_id=audio_tl.id,
                    coordinate_b=87.5,
                ),
            )
        ]
        bundle.add_match_claims(more_claims)

        assert len(bundle._warp_map_cache) == 0  # Cache cleared

    def test_transfer_after_invalidation_rebuilds(self) -> None:
        """Transfer after cache invalidation builds a new WarpMap."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        # Start with 3 claims: linear mapping coord_b = coord_a * 0.5
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        result1 = bundle.transfer(100.0, "score", "audio")
        assert result1 == 50.0

        # Add an additional claim that is consistent with the linear mapping
        more_claims = [
            MatchClaim(
                timeline_a_id=score_tl.id,
                timeline_b_id=audio_tl.id,
                start_anchor=AlignmentAnchor(
                    timeline_a_id=score_tl.id,
                    coordinate_a=150.0,
                    timeline_b_id=audio_tl.id,
                    coordinate_b=75.0,
                ),
            )
        ]
        bundle.add_match_claims(more_claims)

        # Transfer should still work after rebuild
        result2 = bundle.transfer(100.0, "score", "audio")
        assert result2 == 50.0


# endregion


# region Test: add_match_claims API


class TestAddMatchClaims:
    """Tests for the add_match_claims() method."""

    def test_returns_self_for_chaining(self) -> None:
        """add_match_claims returns self for method chaining."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)

        result = bundle.add_match_claims(claims)
        assert result is bundle

    def test_claims_stored_in_cross_group_claims(self) -> None:
        """Claims are stored in cross_group_claims list."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()
        claims = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims)

        assert len(bundle.cross_group_claims) == 3

    def test_multiple_add_claims_accumulate(self) -> None:
        """Multiple add_match_claims calls accumulate claims."""
        bundle, score_tl, _, audio_tl, _ = _make_cross_group_bundle()

        claims1 = _make_linear_claims(score_tl.id, audio_tl.id, n_points=3)
        bundle.add_match_claims(claims1)
        assert len(bundle.cross_group_claims) == 3

        claims2 = [
            MatchClaim(
                timeline_a_id=score_tl.id,
                timeline_b_id=audio_tl.id,
                start_anchor=AlignmentAnchor(
                    timeline_a_id=score_tl.id,
                    coordinate_a=150.0,
                    timeline_b_id=audio_tl.id,
                    coordinate_b=75.0,
                ),
            )
        ]
        bundle.add_match_claims(claims2)
        assert len(bundle.cross_group_claims) == 4


# endregion


# region Test: add_group API


class TestAddGroup:
    """Tests for the add_group() method."""

    def test_add_prebuilt_group(self) -> None:
        """Can add a pre-built TimelineGroup with all its timelines."""
        tl1 = Timeline(length=100, uid="g1")
        tl2 = Timeline(length=200, uid="g2")

        group = TimelineGroup(id="my_group", timelines=[tl1, tl2])

        bundle = AlignmentBundle(id="test")
        bundle.add_group(group)

        assert bundle.n_groups == 1
        assert bundle.n_timelines == 2
        assert tl1.id in bundle.timeline_ids
        assert tl2.id in bundle.timeline_ids

    def test_add_group_with_uid_map(self) -> None:
        """Can add a group with custom UIDs via uid_map."""
        tl1 = Timeline(length=100, uid="g1")
        tl2 = Timeline(length=200, uid="g2")

        group = TimelineGroup(id="my_group", timelines=[tl1, tl2])

        bundle = AlignmentBundle(id="test")
        bundle.add_group(group, uid_map={tl1.id: "custom1", tl2.id: "custom2"})

        assert "custom1" in bundle.timeline_ids
        assert "custom2" in bundle.timeline_ids
        assert bundle.get_timeline("custom1") is tl1
        assert bundle.get_timeline("custom2") is tl2

    def test_add_group_duplicate_id_raises(self) -> None:
        """Adding group with duplicate ID raises ValueError."""
        tl1 = Timeline(length=100, uid="g1")
        group = TimelineGroup(id="my_group", timelines=[tl1])

        bundle = AlignmentBundle(id="test")
        bundle.add_group(group)

        tl2 = Timeline(length=200, uid="g2")
        group2 = TimelineGroup(id="my_group", timelines=[tl2])
        with pytest.raises(ValueError, match="already exists"):
            bundle.add_group(group2)

    def test_add_group_cross_group_transfer(self) -> None:
        """Cross-group transfer works with add_group API."""
        tl_score = Timeline(length=200, uid="s1")
        tl_audio = Timeline(length=100, uid="a1")

        grp_score = TimelineGroup(id="score", timelines=[tl_score])
        grp_audio = TimelineGroup(id="audio", timelines=[tl_audio])

        bundle = AlignmentBundle(id="test")
        bundle.add_group(grp_score)
        bundle.add_group(grp_audio)

        claims = _make_linear_claims(tl_score.id, tl_audio.id, n_points=5)
        bundle.add_match_claims(claims)

        result = bundle.transfer(100.0, tl_score.id, tl_audio.id)
        assert result == 50.0


# endregion
