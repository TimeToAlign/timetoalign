"""Tests for PerfectAlignment and TimelineGroup classes."""

from __future__ import annotations

import pytest

from timetoalign.alignment import PerfectAlignment, TimelineGroup
from timetoalign.alignment.groups import _reset_group_ids
from timetoalign.timelines import (
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
)

# region Fixtures


@pytest.fixture(autouse=True)
def reset_ids() -> None:
    """Reset ID generators before each test."""
    _reset_group_ids()


@pytest.fixture
def dgt_timeline() -> DiscreteGraphicalTimeline:
    """Create a discrete graphical timeline (pixels)."""
    return DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt1")


@pytest.fixture
def physical_timeline() -> ContinuousPhysicalTimeline:
    """Create a continuous physical timeline (seconds)."""
    return ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="sec1")


@pytest.fixture
def basic_group(dgt_timeline: DiscreteGraphicalTimeline) -> TimelineGroup:
    """Create a basic group with reference timeline."""
    return TimelineGroup.from_reference(dgt_timeline, name="TestGroup")


# endregion


# region PerfectAlignment Tests


class TestPerfectAlignment:
    """Tests for PerfectAlignment dataclass."""

    def test_default_values(self) -> None:
        """Test default alignment values."""
        align = PerfectAlignment()
        assert align.source_start == 0.0
        assert align.source_end is None
        assert align.ref_start == 0.0
        assert align.ref_end is None

    def test_resolve_with_none_values(self) -> None:
        """Test resolve replaces None with actual lengths."""
        align = PerfectAlignment()
        src_start, src_end, ref_start, ref_end = align.resolve(
            source_length=100.0, ref_length=200.0
        )

        assert src_start == 0.0
        assert src_end == 100.0
        assert ref_start == 0.0
        assert ref_end == 200.0

    def test_resolve_with_explicit_values(self) -> None:
        """Test resolve preserves explicit values."""
        align = PerfectAlignment(
            source_start=10.0,
            source_end=90.0,
            ref_start=45.0,
            ref_end=135.0,
        )
        src_start, src_end, ref_start, ref_end = align.resolve(
            source_length=100.0, ref_length=180.0
        )

        assert src_start == 10.0
        assert src_end == 90.0
        assert ref_start == 45.0
        assert ref_end == 135.0

    def test_to_reference_identity(self) -> None:
        """Test identity mapping (same lengths, full range)."""
        align = PerfectAlignment()
        result = align.to_reference(50.0, source_length=100.0, ref_length=100.0)
        assert result == 50.0

    def test_to_reference_scaling(self) -> None:
        """Test scaling when reference is different length."""
        align = PerfectAlignment()
        # Source 100, ref 200: coord 50 -> 100
        result = align.to_reference(50.0, source_length=100.0, ref_length=200.0)
        assert result == 100.0

    def test_to_reference_partial_alignment(self) -> None:
        """Test partial alignment (excerpt mapping)."""
        # Score excerpt (0-100) maps to recording seconds 45-90
        align = PerfectAlignment(
            source_start=0,
            source_end=100.0,
            ref_start=45.0,
            ref_end=90.0,
        )

        # Start of score -> start of mapped region
        assert align.to_reference(0.0, source_length=100.0, ref_length=180.0) == 45.0

        # End of score -> end of mapped region
        assert align.to_reference(100.0, source_length=100.0, ref_length=180.0) == 90.0

        # Middle of score -> middle of mapped region
        result = align.to_reference(50.0, source_length=100.0, ref_length=180.0)
        assert result == pytest.approx(67.5)  # 45 + 0.5 * (90-45)

    def test_from_reference_inverse(self) -> None:
        """Test from_reference is inverse of to_reference."""
        align = PerfectAlignment(
            source_start=0,
            source_end=100.0,
            ref_start=45.0,
            ref_end=90.0,
        )

        # Round trip: source -> ref -> source
        original = 25.0
        ref_coord = align.to_reference(original, source_length=100.0, ref_length=180.0)
        back = align.from_reference(ref_coord, source_length=100.0, ref_length=180.0)
        assert back == pytest.approx(original)

    def test_zero_length_source_raises(self) -> None:
        """Test error when source range is zero length."""
        align = PerfectAlignment(source_start=50.0, source_end=50.0)

        with pytest.raises(ValueError, match="source range is zero-length"):
            align.to_reference(50.0, source_length=100.0, ref_length=100.0)

    def test_zero_length_ref_raises(self) -> None:
        """Test error when reference range is zero length."""
        align = PerfectAlignment(ref_start=50.0, ref_end=50.0)

        with pytest.raises(ValueError, match="reference range is zero-length"):
            align.from_reference(50.0, source_length=100.0, ref_length=100.0)

    def test_is_within_source_range(self) -> None:
        """Test source range boundary check."""
        align = PerfectAlignment(source_start=10.0, source_end=90.0)

        assert align.is_within_source_range(10.0, 100.0, 100.0) is True
        assert align.is_within_source_range(50.0, 100.0, 100.0) is True
        assert align.is_within_source_range(90.0, 100.0, 100.0) is True
        assert align.is_within_source_range(5.0, 100.0, 100.0) is False
        assert align.is_within_source_range(95.0, 100.0, 100.0) is False

    def test_is_within_ref_range(self) -> None:
        """Test reference range boundary check."""
        align = PerfectAlignment(ref_start=45.0, ref_end=90.0)

        assert align.is_within_ref_range(45.0, 100.0, 180.0) is True
        assert align.is_within_ref_range(67.5, 100.0, 180.0) is True
        assert align.is_within_ref_range(90.0, 100.0, 180.0) is True
        assert align.is_within_ref_range(30.0, 100.0, 180.0) is False
        assert align.is_within_ref_range(100.0, 100.0, 180.0) is False

    def test_frozen_dataclass(self) -> None:
        """Test that PerfectAlignment is immutable."""
        align = PerfectAlignment()
        with pytest.raises(AttributeError):
            align.source_start = 10.0  # type: ignore


# endregion


# region TimelineGroup Tests


class TestTimelineGroup:
    """Tests for TimelineGroup class."""

    def test_from_reference(self, dgt_timeline: DiscreteGraphicalTimeline) -> None:
        """Test creating a group from reference timeline."""
        group = TimelineGroup.from_reference(dgt_timeline, name="TestGroup")

        assert group.name == "TestGroup"
        assert group.reference_timeline_id == "dgt1"
        assert group.n_timelines == 1
        assert "dgt1" in group.timelines
        assert group.reference is dgt_timeline

    def test_from_reference_auto_id(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test auto-generated group ID."""
        group = TimelineGroup.from_reference(dgt_timeline)
        assert group.id.startswith("group:TimelineGroup")

    def test_from_reference_explicit_id(
        self, dgt_timeline: DiscreteGraphicalTimeline
    ) -> None:
        """Test explicit group ID."""
        group = TimelineGroup.from_reference(dgt_timeline, uid="my_group")
        assert group.id == "my_group"

    def test_add_timeline(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test adding a timeline with alignment."""
        align = PerfectAlignment(
            source_start=0,
            source_end=150.0,
            ref_start=0,
            ref_end=4875,
        )
        basic_group.add_timeline(physical_timeline, alignment=align)

        assert basic_group.n_timelines == 2
        assert "sec1" in basic_group.timelines
        assert basic_group.get_timeline("sec1") is physical_timeline
        assert basic_group.get_alignment("sec1") is align

    def test_add_timeline_default_alignment(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test adding timeline with default (identity) alignment."""
        basic_group.add_timeline(physical_timeline)

        align = basic_group.get_alignment("sec1")
        assert align.source_start == 0.0
        assert align.source_end is None
        assert align.ref_start == 0.0
        assert align.ref_end is None

    def test_add_duplicate_raises(
        self,
        basic_group: TimelineGroup,
        dgt_timeline: DiscreteGraphicalTimeline,
    ) -> None:
        """Test adding duplicate timeline raises error."""
        with pytest.raises(ValueError, match="already in group"):
            basic_group.add_timeline(dgt_timeline)

    def test_remove_timeline(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test removing a timeline from group."""
        basic_group.add_timeline(physical_timeline)
        assert basic_group.n_timelines == 2

        removed = basic_group.remove_timeline("sec1")
        assert removed is physical_timeline
        assert basic_group.n_timelines == 1
        assert "sec1" not in basic_group.timelines

    def test_remove_reference_raises(self, basic_group: TimelineGroup) -> None:
        """Test cannot remove reference timeline."""
        with pytest.raises(ValueError, match="Cannot remove reference"):
            basic_group.remove_timeline("dgt1")

    def test_remove_nonexistent_raises(self, basic_group: TimelineGroup) -> None:
        """Test removing non-existent timeline raises error."""
        with pytest.raises(ValueError, match="not in group"):
            basic_group.remove_timeline("nonexistent")

    def test_get_timeline_keyerror(self, basic_group: TimelineGroup) -> None:
        """Test getting non-existent timeline raises KeyError."""
        with pytest.raises(KeyError):
            basic_group.get_timeline("nonexistent")

    def test_convert_same_timeline(self, basic_group: TimelineGroup) -> None:
        """Test converting to same timeline returns input."""
        result = basic_group.convert(1000.0, "dgt1", "dgt1")
        assert result == 1000.0

    def test_convert_between_timelines(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test coordinate conversion between timelines."""
        # Add seconds timeline: 150 seconds maps to 4875 pixels
        align = PerfectAlignment(
            source_start=0,
            source_end=150.0,
            ref_start=0,
            ref_end=4875,
        )
        basic_group.add_timeline(physical_timeline, alignment=align)

        # 2437.5 pixels (middle) should map to 75 seconds (middle)
        result = basic_group.convert(2437.5, "dgt1", "sec1")
        assert result == pytest.approx(75.0)

        # And reverse
        result = basic_group.convert(75.0, "sec1", "dgt1")
        assert result == pytest.approx(2437.5)

    def test_convert_nonexistent_source(self, basic_group: TimelineGroup) -> None:
        """Test conversion with non-existent source timeline."""
        with pytest.raises(KeyError, match="Source timeline"):
            basic_group.convert(100.0, "nonexistent", "dgt1")

    def test_convert_nonexistent_target(self, basic_group: TimelineGroup) -> None:
        """Test conversion with non-existent target timeline."""
        with pytest.raises(KeyError, match="Target timeline"):
            basic_group.convert(100.0, "dgt1", "nonexistent")

    def test_to_reference_coord(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test to_reference_coord shortcut."""
        align = PerfectAlignment(
            source_start=0,
            source_end=150.0,
            ref_start=0,
            ref_end=4875,
        )
        basic_group.add_timeline(physical_timeline, alignment=align)

        # 75 seconds -> 2437.5 pixels (reference)
        result = basic_group.to_reference_coord(75.0, "sec1")
        assert result == pytest.approx(2437.5)

    def test_from_reference_coord(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test from_reference_coord shortcut."""
        align = PerfectAlignment(
            source_start=0,
            source_end=150.0,
            ref_start=0,
            ref_end=4875,
        )
        basic_group.add_timeline(physical_timeline, alignment=align)

        # 2437.5 pixels (reference) -> 75 seconds
        result = basic_group.from_reference_coord(2437.5, "sec1")
        assert result == pytest.approx(75.0)

    def test_iter_timelines(
        self,
        basic_group: TimelineGroup,
        physical_timeline: ContinuousPhysicalTimeline,
    ) -> None:
        """Test iterating over timelines."""
        basic_group.add_timeline(physical_timeline)

        items = basic_group.iter_timelines()
        assert len(items) == 2

        ids = [tl_id for tl_id, _, _ in items]
        assert "dgt1" in ids
        assert "sec1" in ids

    def test_summary(self, basic_group: TimelineGroup) -> None:
        """Test summary method."""
        summary = basic_group.summary()

        assert summary["name"] == "TestGroup"
        assert summary["reference_timeline_id"] == "dgt1"
        assert summary["n_timelines"] == 1
        assert "dgt1" in summary["timeline_ids"]

    def test_repr(self, basic_group: TimelineGroup) -> None:
        """Test string representation."""
        r = repr(basic_group)
        assert "TimelineGroup" in r
        assert "dgt1" in r
        assert "n_timelines=1" in r


# endregion


# region Integration Tests


class TestGroupIntegration:
    """Integration tests for TimelineGroup with real timelines."""

    def test_thoresen_poc_setup(self) -> None:
        """Test setup similar to Thoresen PoC from spec.

        DGT1 (2009): 5 equal segments, 4875 pixels total
        DGT2 (2010): 5 varying segments, 4328 pixels total

        Both should map to 150 seconds of audio.
        """
        # Create timelines
        dgt1 = DiscreteGraphicalTimeline(length=4875, unit="pixels", uid="dgt1")
        dgt2 = DiscreteGraphicalTimeline(length=4328, unit="pixels", uid="dgt2")
        audio = ContinuousPhysicalTimeline(length=150.0, unit="seconds", uid="audio")

        # Create group 1: DGT1 + audio
        group1 = TimelineGroup.from_reference(dgt1, name="DGT1_Group")
        group1.add_timeline(
            audio,
            alignment=PerfectAlignment(
                source_start=0,
                source_end=150.0,
                ref_start=0,
                ref_end=4875,
            ),
        )

        # Create group 2: DGT2 + audio
        group2 = TimelineGroup.from_reference(dgt2, name="DGT2_Group")
        group2.add_timeline(
            audio,
            alignment=PerfectAlignment(
                source_start=0,
                source_end=150.0,
                ref_start=0,
                ref_end=4328,
            ),
        )

        # Verify conversions
        # DGT1: pixel 0 -> 0 sec, pixel 4875 -> 150 sec
        assert group1.convert(0, "dgt1", "audio") == pytest.approx(0.0)
        assert group1.convert(4875, "dgt1", "audio") == pytest.approx(150.0)

        # DGT2: pixel 0 -> 0 sec, pixel 4328 -> 150 sec
        assert group2.convert(0, "dgt2", "audio") == pytest.approx(0.0)
        assert group2.convert(4328, "dgt2", "audio") == pytest.approx(150.0)

        # Midpoint test
        assert group1.convert(2437.5, "dgt1", "audio") == pytest.approx(75.0)
        assert group2.convert(2164, "dgt2", "audio") == pytest.approx(75.0)


# endregion
