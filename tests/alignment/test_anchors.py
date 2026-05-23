"""Tests for AlignmentAnchor, MatchClaim, and MatchMetadata classes."""

from __future__ import annotations

from datetime import datetime

import pytest

from timetoalign.alignment import AlignmentAnchor, MatchClaim, MatchMetadata

# region Fixtures


@pytest.fixture
def basic_anchor() -> AlignmentAnchor:
    """Create a basic alignment anchor."""
    return AlignmentAnchor(
        timeline_a_id="score:1",
        coordinate_a=100.0,
        timeline_b_id="recording:1",
        coordinate_b=45.5,
    )


@pytest.fixture
def basic_metadata() -> MatchMetadata:
    """Create basic match metadata."""
    return MatchMetadata(
        agent="test_user",
        decision_criteria="manual_alignment",
    )


# endregion


# region MatchMetadata Tests


class TestMatchMetadata:
    """Tests for MatchMetadata dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating metadata with required fields."""
        meta = MatchMetadata(
            agent="analyst",
            decision_criteria="segment_correspondence",
        )

        assert meta.agent == "analyst"
        assert meta.decision_criteria == "segment_correspondence"
        assert meta.certainty == 1.0  # default
        assert meta.notes is None
        assert meta.algorithm_params is None

    def test_full_creation(self) -> None:
        """Test creating metadata with all fields."""
        now = datetime.now()
        meta = MatchMetadata(
            agent="dtw_v2",
            decision_criteria="dynamic_time_warping",
            certainty=0.85,
            created_at=now,
            notes="Test alignment",
            algorithm_params={"window_size": 100},
        )

        assert meta.agent == "dtw_v2"
        assert meta.certainty == 0.85
        assert meta.created_at == now
        assert meta.notes == "Test alignment"
        assert meta.algorithm_params == {"window_size": 100}

    def test_certainty_validation(self) -> None:
        """Test certainty must be in [0, 1]."""
        with pytest.raises(ValueError, match="Certainty must be in"):
            MatchMetadata(agent="test", decision_criteria="test", certainty=-0.1)

        with pytest.raises(ValueError, match="Certainty must be in"):
            MatchMetadata(agent="test", decision_criteria="test", certainty=1.1)

    def test_certainty_boundaries(self) -> None:
        """Test certainty boundary values are valid."""
        meta_0 = MatchMetadata(agent="test", decision_criteria="test", certainty=0.0)
        meta_1 = MatchMetadata(agent="test", decision_criteria="test", certainty=1.0)
        assert meta_0.certainty == 0.0
        assert meta_1.certainty == 1.0

    def test_to_dict(self, basic_metadata: MatchMetadata) -> None:
        """Test serialization to dictionary."""
        d = basic_metadata.to_dict()

        assert d["agent"] == "test_user"
        assert d["decision_criteria"] == "manual_alignment"
        assert d["certainty"] == 1.0
        assert "created_at" in d

    def test_from_dict_roundtrip(self, basic_metadata: MatchMetadata) -> None:
        """Test serialization round-trip."""
        d = basic_metadata.to_dict()
        restored = MatchMetadata.from_dict(d)

        assert restored.agent == basic_metadata.agent
        assert restored.decision_criteria == basic_metadata.decision_criteria
        assert restored.certainty == basic_metadata.certainty

    def test_frozen_dataclass(self, basic_metadata: MatchMetadata) -> None:
        """Test that MatchMetadata is immutable."""
        with pytest.raises(AttributeError):
            basic_metadata.agent = "other"  # type: ignore


# endregion


# region AlignmentAnchor Tests


class TestAlignmentAnchor:
    """Tests for AlignmentAnchor dataclass (pure coordinate pair)."""

    def test_basic_creation(self) -> None:
        """Test creating an anchor with required fields."""
        anchor = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=10.0,
            timeline_b_id="tl2",
            coordinate_b=20.0,
        )

        assert anchor.timeline_a_id == "tl1"
        assert anchor.coordinate_a == 10.0
        assert anchor.timeline_b_id == "tl2"
        assert anchor.coordinate_b == 20.0

    def test_no_id_field(self) -> None:
        """Test that AlignmentAnchor has no id field."""
        anchor = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        assert not hasattr(anchor, "id")

    def test_no_claim_fields(self) -> None:
        """Test that AlignmentAnchor has no is_explicit or is_synchronous."""
        anchor = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        assert not hasattr(anchor, "is_explicit")
        assert not hasattr(anchor, "is_synchronous")

    def test_timelines_property(self, basic_anchor: AlignmentAnchor) -> None:
        """Test timelines property."""
        assert basic_anchor.timelines == ("score:1", "recording:1")

    def test_coordinates_property(self, basic_anchor: AlignmentAnchor) -> None:
        """Test coordinates property."""
        assert basic_anchor.coordinates == (100.0, 45.5)

    def test_get_coordinate_for(self, basic_anchor: AlignmentAnchor) -> None:
        """Test getting coordinate for specific timeline."""
        assert basic_anchor.get_coordinate_for("score:1") == 100.0
        assert basic_anchor.get_coordinate_for("recording:1") == 45.5
        assert basic_anchor.get_coordinate_for("other") is None

    def test_connects(self, basic_anchor: AlignmentAnchor) -> None:
        """Test connects method."""
        assert basic_anchor.connects("score:1") is True
        assert basic_anchor.connects("recording:1") is True
        assert basic_anchor.connects("other") is False

    def test_connects_both(self, basic_anchor: AlignmentAnchor) -> None:
        """Test connects_both method."""
        assert basic_anchor.connects_both("score:1", "recording:1") is True
        assert basic_anchor.connects_both("recording:1", "score:1") is True
        assert basic_anchor.connects_both("score:1", "other") is False

    def test_to_dict(self, basic_anchor: AlignmentAnchor) -> None:
        """Test serialization to dictionary."""
        d = basic_anchor.to_dict()

        assert d["timeline_a_id"] == "score:1"
        assert d["coordinate_a"] == 100.0
        assert d["timeline_b_id"] == "recording:1"
        assert d["coordinate_b"] == 45.5
        # No is_explicit, is_synchronous, or id in dict
        assert "is_explicit" not in d
        assert "is_synchronous" not in d
        assert "id" not in d

    def test_from_dict_roundtrip(self, basic_anchor: AlignmentAnchor) -> None:
        """Test serialization round-trip."""
        d = basic_anchor.to_dict()
        restored = AlignmentAnchor.from_dict(d)

        assert restored.timeline_a_id == basic_anchor.timeline_a_id
        assert restored.coordinate_a == basic_anchor.coordinate_a
        assert restored.timeline_b_id == basic_anchor.timeline_b_id
        assert restored.coordinate_b == basic_anchor.coordinate_b

    def test_frozen_dataclass(self, basic_anchor: AlignmentAnchor) -> None:
        """Test that AlignmentAnchor is immutable."""
        with pytest.raises(AttributeError):
            basic_anchor.coordinate_a = 200.0  # type: ignore

    def test_repr(self, basic_anchor: AlignmentAnchor) -> None:
        """Test string representation."""
        r = repr(basic_anchor)
        assert "AlignmentAnchor" in r
        assert "score:1" in r
        assert "recording:1" in r

    def test_value_equality(self) -> None:
        """Test that anchors with same values are equal (value objects)."""
        a1 = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=10.0,
            timeline_b_id="tl2",
            coordinate_b=20.0,
        )
        a2 = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=10.0,
            timeline_b_id="tl2",
            coordinate_b=20.0,
        )
        assert a1 == a2


# endregion


# region MatchClaim Tests


class TestMatchClaim:
    """Tests for MatchClaim dataclass (top-level timeline IDs)."""

    def test_instant_creation(self, basic_anchor: AlignmentAnchor) -> None:
        """Test creating instant match (single anchor)."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )

        assert claim.is_interval is False
        assert claim.start_anchor is basic_anchor
        assert claim.end_anchor is None
        assert claim.timeline_a_id == "score:1"
        assert claim.timeline_b_id == "recording:1"

    def test_interval_creation(self) -> None:
        """Test creating interval match (two anchors)."""
        start = AlignmentAnchor(
            timeline_a_id="dgt1",
            coordinate_a=0.0,
            timeline_b_id="dgt2",
            coordinate_b=0.0,
        )
        end = AlignmentAnchor(
            timeline_a_id="dgt1",
            coordinate_a=975.0,
            timeline_b_id="dgt2",
            coordinate_b=866.0,
        )
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="dgt2",
            start_anchor=start,
            end_anchor=end,
        )

        assert claim.is_interval is True
        assert claim.start_anchor is start
        assert claim.end_anchor is end

    def test_auto_generated_id(self, basic_anchor: AlignmentAnchor) -> None:
        """Test ID is auto-generated if not provided."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        assert claim.id.startswith("claim:MatchClaim")

    def test_explicit_id(self, basic_anchor: AlignmentAnchor) -> None:
        """Test explicit ID is preserved."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
            id="my_claim",
        )
        assert claim.id == "my_claim"

    def test_mismatched_anchors_raises(self) -> None:
        """Test error when anchors connect different timelines."""
        start = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        end = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=100.0,
            timeline_b_id="tl3",  # Different!
            coordinate_b=100.0,
        )

        with pytest.raises(ValueError, match="must connect same timelines"):
            MatchClaim(
                timeline_a_id="tl1",
                timeline_b_id="tl2",
                start_anchor=start,
                end_anchor=end,
            )

    def test_synchronous_requires_anchor(self) -> None:
        """Test that synchronous claims require a start_anchor."""
        with pytest.raises(ValueError, match="require a start_anchor"):
            MatchClaim(
                timeline_a_id="tl1",
                timeline_b_id="tl2",
                start_anchor=None,
                is_synchronous=True,
            )

    def test_non_synchronous_rejects_anchor(self) -> None:
        """Test that non-synchronous claims must not have anchors."""
        anchor = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        with pytest.raises(ValueError, match="must not have anchors"):
            MatchClaim(
                timeline_a_id="tl1",
                timeline_b_id="tl2",
                start_anchor=anchor,
                is_synchronous=False,
            )

    def test_non_synchronous_claim(self) -> None:
        """Test creating a non-synchronous claim (no anchors)."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            is_synchronous=False,
        )
        assert claim.start_anchor is None
        assert claim.end_anchor is None
        assert claim.anchors == []
        assert claim.timeline_a_id == "tl1"
        assert claim.timeline_b_id == "tl2"

    def test_anchor_timeline_mismatch_raises(self) -> None:
        """Test error when anchor timelines don't match claim timelines."""
        anchor = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        with pytest.raises(ValueError, match="must match claim timelines"):
            MatchClaim(
                timeline_a_id="tl1",
                timeline_b_id="tl3",  # Doesn't match anchor
                start_anchor=anchor,
            )

    def test_timelines_property(self, basic_anchor: AlignmentAnchor) -> None:
        """Test timelines property."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        assert claim.timelines == ("score:1", "recording:1")

    def test_get_coordinates_for_instant(self, basic_anchor: AlignmentAnchor) -> None:
        """Test get_coordinates_for with instant match."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )

        start, end = claim.get_coordinates_for("score:1")
        assert start == 100.0
        assert end is None

    def test_get_coordinates_for_interval(self) -> None:
        """Test get_coordinates_for with interval match."""
        start = AlignmentAnchor(
            timeline_a_id="dgt1",
            coordinate_a=0.0,
            timeline_b_id="dgt2",
            coordinate_b=0.0,
        )
        end = AlignmentAnchor(
            timeline_a_id="dgt1",
            coordinate_a=975.0,
            timeline_b_id="dgt2",
            coordinate_b=866.0,
        )
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="dgt2",
            start_anchor=start,
            end_anchor=end,
        )

        start_coord, end_coord = claim.get_coordinates_for("dgt1")
        assert start_coord == 0.0
        assert end_coord == 975.0

        start_coord, end_coord = claim.get_coordinates_for("dgt2")
        assert start_coord == 0.0
        assert end_coord == 866.0

    def test_get_coordinates_invalid_timeline(
        self, basic_anchor: AlignmentAnchor
    ) -> None:
        """Test error when getting coordinates for non-connected timeline."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )

        with pytest.raises(ValueError, match="not in this claim"):
            claim.get_coordinates_for("other")

    def test_get_coordinates_non_synchronous_raises(self) -> None:
        """Test error when getting coordinates from non-synchronous claim."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            is_synchronous=False,
        )
        with pytest.raises(ValueError, match="no anchors"):
            claim.get_coordinates_for("tl1")

    def test_connects(self, basic_anchor: AlignmentAnchor) -> None:
        """Test connects method."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )

        assert claim.connects("score:1") is True
        assert claim.connects("recording:1") is True
        assert claim.connects("other") is False

    def test_connects_both(self, basic_anchor: AlignmentAnchor) -> None:
        """Test connects_both method."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )

        assert claim.connects_both("score:1", "recording:1") is True
        assert claim.connects_both("score:1", "other") is False

    def test_anchors_property_instant(self, basic_anchor: AlignmentAnchor) -> None:
        """Test anchors property for instant match."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        assert claim.anchors == [basic_anchor]

    def test_anchors_property_interval(self) -> None:
        """Test anchors property for interval match."""
        start = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=0.0,
            timeline_b_id="tl2",
            coordinate_b=0.0,
        )
        end = AlignmentAnchor(
            timeline_a_id="tl1",
            coordinate_a=100.0,
            timeline_b_id="tl2",
            coordinate_b=100.0,
        )
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            start_anchor=start,
            end_anchor=end,
        )

        assert claim.anchors == [start, end]

    def test_anchors_property_non_synchronous(self) -> None:
        """Test anchors property for non-synchronous claim returns empty list."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            is_synchronous=False,
        )
        assert claim.anchors == []

    def test_with_metadata(
        self, basic_anchor: AlignmentAnchor, basic_metadata: MatchMetadata
    ) -> None:
        """Test creating claim with metadata."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
            metadata=basic_metadata,
        )

        assert claim.metadata is basic_metadata
        assert claim.metadata.agent == "test_user"

    def test_instant_factory(self) -> None:
        """Test instant match via direct construction."""
        claim = MatchClaim(
            timeline_a_id="score",
            timeline_b_id="recording",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score",
                coordinate_a=0.0,
                timeline_b_id="recording",
                coordinate_b=0.0,
            ),
        )

        assert claim.is_interval is False
        assert claim.timeline_a_id == "score"
        assert claim.timeline_b_id == "recording"
        assert claim.start_anchor.coordinate_a == 0.0

    def test_interval_factory(self) -> None:
        """Test interval match via direct construction."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="dgt2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=0.0,
                timeline_b_id="dgt2",
                coordinate_b=0.0,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=975.0,
                timeline_b_id="dgt2",
                coordinate_b=866.0,
            ),
        )

        assert claim.is_interval is True
        assert claim.timeline_a_id == "dgt1"
        assert claim.timeline_b_id == "dgt2"
        start, end = claim.get_coordinates_for("dgt1")
        assert start == 0.0
        assert end == 975.0

    def test_from_events_factory(self) -> None:
        """Test from_events() factory method (case a: event-based)."""
        claim = MatchClaim.from_events(
            event_a={"start": 100.0},
            tl_a_id="score",
            event_b={"start": 45.5},
            tl_b_id="recording",
        )

        assert claim.is_synchronous is True
        assert claim.timeline_a_id == "score"
        assert claim.timeline_b_id == "recording"
        assert claim.start_anchor is not None
        assert claim.start_anchor.coordinate_a == 100.0
        assert claim.start_anchor.coordinate_b == 45.5

    def test_from_events_with_interval(self) -> None:
        """Test from_events() with end coordinate (case a: interval)."""
        claim = MatchClaim.from_events(
            event_a={"start": 0.0, "end": 100.0},
            tl_a_id="tl1",
            event_b={"start": 0.0, "end": 200.0},
            tl_b_id="tl2",
            end_coord_key="end",
        )

        assert claim.is_interval is True
        assert claim.end_anchor is not None
        assert claim.end_anchor.coordinate_a == 100.0
        assert claim.end_anchor.coordinate_b == 200.0

    def test_from_projection_factory(self) -> None:
        """Test from_projection() factory method (case b: projection)."""
        claim = MatchClaim.from_projection(
            event={"start": 100.0},
            source_tl_id="score",
            target_tl_id="recording",
            target_coord=45.5,
        )

        assert claim.is_synchronous is True
        assert claim.timeline_a_id == "score"
        assert claim.timeline_b_id == "recording"
        assert claim.start_anchor is not None
        assert claim.start_anchor.coordinate_a == 100.0
        assert claim.start_anchor.coordinate_b == 45.5

    def test_nomatch_factory(self) -> None:
        """Test nomatch() factory method (case c: no match)."""
        claim = MatchClaim.nomatch(
            event={"start": 100.0},
            source_tl_id="score",
            target_tl_id="recording",
        )

        assert claim.is_synchronous is False
        assert claim.start_anchor is None
        assert claim.end_anchor is None
        assert claim.timeline_a_id == "score"
        assert claim.timeline_b_id == "recording"
        assert claim.anchors == []

    def test_implicit_factory(self) -> None:
        """Test implicit() factory method (case d: inferred)."""
        claim = MatchClaim.implicit(
            tl_a_id="tl1",
            coord_a=100.0,
            tl_b_id="tl2",
            coord_b=200.0,
        )

        assert claim.is_synchronous is True
        assert claim.is_explicit is False
        assert claim.start_anchor is not None
        assert claim.start_anchor.coordinate_a == 100.0
        assert claim.timeline_a_id == "tl1"
        assert claim.timeline_b_id == "tl2"

    def test_implicit_with_source_claim(self) -> None:
        """Test implicit() tracks the source claim."""
        source = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=100.0,
                timeline_b_id="tl2",
                coordinate_b=200.0,
            ),
        )
        implicit = MatchClaim.implicit(
            tl_a_id="tl1",
            coord_a=100.0,
            tl_b_id="tl3",
            coord_b=300.0,
            source_claim=source,
        )

        assert implicit.source_claim_id == source.id

    def test_to_dict_instant(self, basic_anchor: AlignmentAnchor) -> None:
        """Test serialization of instant match."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        d = claim.to_dict()

        assert "id" in d
        assert "timeline_a_id" in d
        assert "timeline_b_id" in d
        assert "start_anchor" in d
        assert d["end_anchor"] is None
        assert d["is_explicit"] is True
        assert d["is_synchronous"] is True

    def test_to_dict_interval(self) -> None:
        """Test serialization of interval match."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=0.0,
                timeline_b_id="tl2",
                coordinate_b=0.0,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=100.0,
                timeline_b_id="tl2",
                coordinate_b=100.0,
            ),
        )
        d = claim.to_dict()

        assert d["start_anchor"] is not None
        assert d["end_anchor"] is not None

    def test_from_dict_roundtrip_instant(self, basic_anchor: AlignmentAnchor) -> None:
        """Test serialization round-trip for instant match."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        d = claim.to_dict()
        restored = MatchClaim.from_dict(d)

        assert restored.id == claim.id
        assert restored.is_interval is False
        assert restored.timeline_a_id == claim.timeline_a_id

    def test_from_dict_roundtrip_interval(self) -> None:
        """Test serialization round-trip for interval match."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=0.0,
                timeline_b_id="tl2",
                coordinate_b=0.0,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=100.0,
                timeline_b_id="tl2",
                coordinate_b=200.0,
            ),
            metadata=MatchMetadata(agent="test", decision_criteria="test"),
        )
        d = claim.to_dict()
        restored = MatchClaim.from_dict(d)

        assert restored.id == claim.id
        assert restored.is_interval is True
        assert restored.metadata is not None
        assert restored.metadata.agent == "test"

    def test_from_dict_roundtrip_non_synchronous(self) -> None:
        """Test serialization round-trip for non-synchronous claim."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            is_synchronous=False,
        )
        d = claim.to_dict()
        restored = MatchClaim.from_dict(d)

        assert restored.is_synchronous is False
        assert restored.start_anchor is None
        assert restored.timeline_a_id == "tl1"
        assert restored.timeline_b_id == "tl2"

    def test_frozen_dataclass(self, basic_anchor: AlignmentAnchor) -> None:
        """Test that MatchClaim is immutable."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        with pytest.raises(AttributeError):
            claim.is_explicit = False  # type: ignore

    def test_repr_instant(self, basic_anchor: AlignmentAnchor) -> None:
        """Test string representation of instant match."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=basic_anchor,
        )
        r = repr(claim)

        assert "instant" in r
        assert "score:1" in r
        assert "recording:1" in r

    def test_repr_interval(self) -> None:
        """Test string representation of interval match."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="dgt2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=0.0,
                timeline_b_id="dgt2",
                coordinate_b=0.0,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=975.0,
                timeline_b_id="dgt2",
                coordinate_b=866.0,
            ),
        )
        r = repr(claim)

        assert "interval" in r
        assert "dgt1" in r
        assert "dgt2" in r
        assert "0.0-975.0" in r

    def test_repr_non_synchronous(self) -> None:
        """A non-synchronous claim renders the NOMATCH flag (not 'non-synchronous')."""
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            is_synchronous=False,
        )
        r = repr(claim)
        assert "NOMATCH" in r
        assert "non-synchronous" not in r
        assert "tl1" in r
        assert "tl2" in r

    def test_repr_nomatch_with_coordinate_exact(self) -> None:
        """NOMATCH claim from nomatch() renders the source coordinate exactly."""
        claim = MatchClaim.nomatch(
            event={"start": 188.8},
            source_tl_id="score:clt1",
            target_tl_id="perf:Chopin_Ashkenazy",
        )
        assert claim.source_coordinate == 188.8
        assert repr(claim) == (
            "MatchClaim(score:clt1@188.8 <-> perf:Chopin_Ashkenazy [NOMATCH])"
        )

    def test_repr_nomatch_without_coordinate(self) -> None:
        """NOMATCH claim with no 'start' falls back to bare timeline_a."""
        claim = MatchClaim.nomatch(
            event={"id": "orphan"},
            source_tl_id="score:clt1",
            target_tl_id="perf:Chopin_Ashkenazy",
        )
        assert claim.source_coordinate is None
        assert repr(claim) == (
            "MatchClaim(score:clt1 <-> perf:Chopin_Ashkenazy [NOMATCH])"
        )

    def test_nomatch_source_coordinate_roundtrip(self) -> None:
        """to_dict()/from_dict() preserves source_coordinate for a NOMATCH claim."""
        claim = MatchClaim.nomatch(
            event={"start": 188.8},
            source_tl_id="score:clt1",
            target_tl_id="perf:Chopin_Ashkenazy",
        )
        restored = MatchClaim.from_dict(claim.to_dict())
        assert restored == claim
        assert restored.source_coordinate == 188.8

    def test_repr_synchronous_instant_unchanged(self) -> None:
        """Regression guard: a synchronous instant repr is unchanged (no NOMATCH)."""
        claim = MatchClaim(
            timeline_a_id="score:1",
            timeline_b_id="recording:1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:1",
                coordinate_a=100.0,
                timeline_b_id="recording:1",
                coordinate_b=45.5,
            ),
        )
        assert claim.source_coordinate is None
        assert repr(claim) == (
            "MatchClaim(instant: score:1@100.0 <-> recording:1@45.5)"
        )


# endregion


# region Integration Tests


class TestClaimIntegration:
    """Integration tests for alignment claims."""

    def test_thoresen_segment_claims(self) -> None:
        """Test creating segment claims similar to Thoresen PoC.

        Creates 5 interval matches for segment correspondence:
        - DGT1 segments: 5 equal (975 px each)
        - DGT2 segments: 5 varying (866, 867, 867, 864, 864)
        """
        segment_lengths_dgt1 = [975, 975, 975, 975, 975]
        segment_lengths_dgt2 = [866, 867, 867, 864, 864]

        claims = []
        offset_dgt1 = 0
        offset_dgt2 = 0

        for i in range(5):
            claim = MatchClaim(
                timeline_a_id="dgt1",
                timeline_b_id="dgt2",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="dgt1",
                    coordinate_a=float(offset_dgt1),
                    timeline_b_id="dgt2",
                    coordinate_b=float(offset_dgt2),
                ),
                end_anchor=AlignmentAnchor(
                    timeline_a_id="dgt1",
                    coordinate_a=float(offset_dgt1 + segment_lengths_dgt1[i]),
                    timeline_b_id="dgt2",
                    coordinate_b=float(offset_dgt2 + segment_lengths_dgt2[i]),
                ),
                metadata=MatchMetadata(
                    agent="analyst",
                    decision_criteria="segment_correspondence",
                ),
            )
            claims.append(claim)

            offset_dgt1 += segment_lengths_dgt1[i]
            offset_dgt2 += segment_lengths_dgt2[i]

        # Verify
        assert len(claims) == 5
        assert all(c.is_interval for c in claims)
        assert all(c.connects_both("dgt1", "dgt2") for c in claims)

        # Check first segment
        start, end = claims[0].get_coordinates_for("dgt1")
        assert start == 0.0
        assert end == 975.0

        start, end = claims[0].get_coordinates_for("dgt2")
        assert start == 0.0
        assert end == 866.0

        # Check last segment ends at total length
        _, end_dgt1 = claims[4].get_coordinates_for("dgt1")
        _, end_dgt2 = claims[4].get_coordinates_for("dgt2")
        assert end_dgt1 == 4875.0
        assert end_dgt2 == 4328.0


# endregion
