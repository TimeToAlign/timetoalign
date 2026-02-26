"""Tests for MatchGraph and MatchStamp classes.

This module tests the graph-building layer of the alignment infrastructure:
- MatchStamp: Cross-group timestamp representation
- MatchGraph: Graph of MatchClaims with networkx integration
"""

from __future__ import annotations

import pytest

from timetoalign.alignment import (
    AlignmentAnchor,
    MatchClaim,
    MatchMetadata,
    TimelineGroup,
)
from timetoalign.alignment.graph import MatchGraph, MatchStamp
from timetoalign.core.enums import Domain, TimeUnit
from timetoalign.timelines import (
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
)

# region Fixtures


@pytest.fixture
def simple_instant_claim() -> MatchClaim:
    """Simple instant match between two timelines."""
    return MatchClaim(
        timeline_a_id="tl_a",
        timeline_b_id="tl_b",
        start_anchor=AlignmentAnchor(
            timeline_a_id="tl_a",
            coordinate_a=100.0,
            timeline_b_id="tl_b",
            coordinate_b=50.0,
        ),
        metadata=MatchMetadata(agent="test", decision_criteria="manual"),
    )


@pytest.fixture
def simple_interval_claim() -> MatchClaim:
    """Simple interval match between two timelines."""
    return MatchClaim(
        timeline_a_id="tl_a",
        timeline_b_id="tl_b",
        start_anchor=AlignmentAnchor(
            timeline_a_id="tl_a",
            coordinate_a=0.0,
            timeline_b_id="tl_b",
            coordinate_b=0.0,
        ),
        end_anchor=AlignmentAnchor(
            timeline_a_id="tl_a",
            coordinate_a=100.0,
            timeline_b_id="tl_b",
            coordinate_b=50.0,
        ),
        metadata=MatchMetadata(agent="test", decision_criteria="manual"),
    )


@pytest.fixture
def three_timeline_claims() -> list[MatchClaim]:
    """Claims connecting three timelines: A <-> B <-> C."""
    return [
        MatchClaim(
            timeline_a_id="tl_a",
            timeline_b_id="tl_b",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl_a",
                coordinate_a=100.0,
                timeline_b_id="tl_b",
                coordinate_b=50.0,
            ),
        ),
        MatchClaim(
            timeline_a_id="tl_b",
            timeline_b_id="tl_c",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl_b",
                coordinate_a=50.0,
                timeline_b_id="tl_c",
                coordinate_b=25.0,
            ),
        ),
    ]


@pytest.fixture
def dgt1_timeline() -> DiscreteGraphicalTimeline:
    """DGT1 timeline for group tests."""
    return DiscreteGraphicalTimeline(
        length=1000,
        unit="pixels",
        uid="dgt1",
    )


@pytest.fixture
def dgt2_timeline() -> DiscreteGraphicalTimeline:
    """DGT2 timeline for group tests."""
    return DiscreteGraphicalTimeline(
        length=800,
        unit="pixels",
        uid="dgt2",
    )


@pytest.fixture
def audio_timeline() -> ContinuousPhysicalTimeline:
    """Audio timeline for group tests."""
    return ContinuousPhysicalTimeline(
        length=100.0,
        unit="seconds",
        uid="audio",
    )


@pytest.fixture
def dgt1_group(
    dgt1_timeline: DiscreteGraphicalTimeline,
    audio_timeline: ContinuousPhysicalTimeline,
) -> TimelineGroup:
    """Group with DGT1 and audio timelines.

    DGT1: 1000 pixels, Audio: 100 seconds
    Audio's full extent (0-100) maps to DGT1's full extent (0-1000).
    """
    group = TimelineGroup(id="dgt1_group", name="DGT1_Group")
    group.add_timeline(dgt1_timeline)
    group.add_timeline(audio_timeline)
    return group


# endregion


# region MatchStamp Tests


class TestMatchStamp:
    """Tests for MatchStamp class."""

    def test_basic_creation(self) -> None:
        """Create a basic MatchStamp."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
            anchor_edges=[("tl_a", "tl_b")],
            inferred_edges=[],
        )
        assert stamp.n_timelines == 2
        assert stamp.n_explicit_edges == 1
        assert stamp.n_inferred_edges == 0

    def test_empty_stamp(self) -> None:
        """Create an empty MatchStamp."""
        stamp = MatchStamp()
        assert stamp.n_timelines == 0
        assert stamp.timeline_ids == []

    def test_get_coordinate(self) -> None:
        """Get coordinate for specific timeline."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
        )
        assert stamp.get_coordinate("tl_a") == 100.0
        assert stamp.get_coordinate("tl_b") == 50.0
        assert stamp.get_coordinate("tl_c") is None

    def test_has_timeline(self) -> None:
        """Check if timeline is in stamp."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
        )
        assert stamp.has_timeline("tl_a") is True
        assert stamp.has_timeline("tl_c") is False

    def test_timeline_ids(self) -> None:
        """Get list of timeline IDs."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0, "tl_c": 25.0},
        )
        assert set(stamp.timeline_ids) == {"tl_a", "tl_b", "tl_c"}

    def test_filter_by_timelines_include(self) -> None:
        """Filter stamp to include only specific timelines."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0, "tl_c": 25.0},
            anchor_edges=[("tl_a", "tl_b"), ("tl_b", "tl_c")],
        )
        filtered = stamp.filter_by_timelines(include={"tl_a", "tl_b"})

        assert filtered.n_timelines == 2
        assert "tl_c" not in filtered.coordinates
        assert len(filtered.anchor_edges) == 1
        assert ("tl_a", "tl_b") in filtered.anchor_edges

    def test_filter_by_timelines_exclude(self) -> None:
        """Filter stamp to exclude specific timelines."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0, "tl_c": 25.0},
            anchor_edges=[("tl_a", "tl_b"), ("tl_b", "tl_c")],
        )
        filtered = stamp.filter_by_timelines(exclude={"tl_c"})

        assert filtered.n_timelines == 2
        assert "tl_c" not in filtered.coordinates
        assert len(filtered.anchor_edges) == 1

    def test_to_dict_roundtrip(self) -> None:
        """Serialize and deserialize MatchStamp."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
            anchor_edges=[("tl_a", "tl_b")],
            inferred_edges=[("tl_b", "tl_c")],
        )
        data = stamp.to_dict()
        restored = MatchStamp.from_dict(data)

        assert restored.coordinates == stamp.coordinates
        assert restored.anchor_edges == stamp.anchor_edges
        assert restored.inferred_edges == stamp.inferred_edges

    def test_repr(self) -> None:
        """Test string representation."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
        )
        repr_str = repr(stamp)
        assert "MatchStamp" in repr_str
        assert "tl_a" in repr_str
        assert "100.00" in repr_str


# endregion


# region MatchGraph Basic Tests


class TestMatchGraphBasic:
    """Basic tests for MatchGraph class."""

    def test_empty_graph(self) -> None:
        """Create an empty MatchGraph."""
        graph = MatchGraph()
        assert graph.n_claims == 0
        assert graph.n_nodes == 0
        assert graph.n_edges == 0

    def test_single_instant_claim(self, simple_instant_claim: MatchClaim) -> None:
        """Graph with single instant claim."""
        graph = MatchGraph([simple_instant_claim])

        assert graph.n_claims == 1
        assert graph.n_nodes == 2
        assert graph.n_edges == 1
        assert graph.timeline_ids == {"tl_a", "tl_b"}

    def test_single_interval_claim(self, simple_interval_claim: MatchClaim) -> None:
        """Graph with single interval claim."""
        graph = MatchGraph([simple_interval_claim])

        assert graph.n_claims == 1
        assert graph.n_nodes == 4  # 2 start nodes + 2 end nodes
        assert graph.n_edges == 2  # start edge + end edge

    def test_multiple_claims(self, three_timeline_claims: list[MatchClaim]) -> None:
        """Graph with multiple claims connecting three timelines."""
        graph = MatchGraph(three_timeline_claims)

        assert graph.n_claims == 2
        assert graph.n_edges == 2
        assert graph.timeline_ids == {"tl_a", "tl_b", "tl_c"}

    def test_get_nodes_for_timeline(self, simple_interval_claim: MatchClaim) -> None:
        """Get nodes for specific timeline."""
        graph = MatchGraph([simple_interval_claim])

        nodes_a = graph.get_nodes_for_timeline("tl_a")
        assert len(nodes_a) == 2  # start and end
        assert ("tl_a", 0.0) in nodes_a
        assert ("tl_a", 100.0) in nodes_a

    def test_get_coordinates_for_timeline(
        self, simple_interval_claim: MatchClaim
    ) -> None:
        """Get coordinates for specific timeline."""
        graph = MatchGraph([simple_interval_claim])

        coords = graph.get_coordinates_for_timeline("tl_a")
        assert coords == [0.0, 100.0]

    def test_get_connected_nodes(self, simple_instant_claim: MatchClaim) -> None:
        """Get nodes connected to a given node."""
        graph = MatchGraph([simple_instant_claim])

        connected = graph.get_connected_nodes(("tl_a", 100.0))
        assert len(connected) == 1
        assert ("tl_b", 50.0) in connected

    def test_get_connected_timelines(
        self, three_timeline_claims: list[MatchClaim]
    ) -> None:
        """Get timelines connected to a given timeline."""
        graph = MatchGraph(three_timeline_claims)

        # tl_a connects to tl_b
        connected_a = graph.get_connected_timelines("tl_a")
        assert connected_a == {"tl_b"}

        # tl_b connects to both tl_a and tl_c
        connected_b = graph.get_connected_timelines("tl_b")
        assert connected_b == {"tl_a", "tl_c"}


# endregion


# region MatchGraph MatchStamp Extraction Tests


class TestMatchGraphStamps:
    """Tests for MatchStamp extraction from MatchGraph."""

    def test_instant_claim_yields_one_stamp(
        self, simple_instant_claim: MatchClaim
    ) -> None:
        """Instant claim yields one MatchStamp."""
        graph = MatchGraph([simple_instant_claim])
        start_stamp, end_stamp = graph.get_match_stamps()

        assert start_stamp is not None
        assert end_stamp is None  # Instant = no end stamp

        assert start_stamp.get_coordinate("tl_a") == 100.0
        assert start_stamp.get_coordinate("tl_b") == 50.0
        assert len(start_stamp.anchor_edges) == 1

    def test_interval_claim_yields_two_stamps(
        self, simple_interval_claim: MatchClaim
    ) -> None:
        """Interval claim yields two MatchStamps."""
        graph = MatchGraph([simple_interval_claim])
        start_stamp, end_stamp = graph.get_match_stamps()

        assert start_stamp is not None
        assert end_stamp is not None

        # Start stamp
        assert start_stamp.get_coordinate("tl_a") == 0.0
        assert start_stamp.get_coordinate("tl_b") == 0.0

        # End stamp
        assert end_stamp.get_coordinate("tl_a") == 100.0
        assert end_stamp.get_coordinate("tl_b") == 50.0

    def test_get_all_stamps(self, three_timeline_claims: list[MatchClaim]) -> None:
        """Get all stamps from graph with multiple connected components."""
        # These claims create a single connected component (A-B-C chain)
        graph = MatchGraph(three_timeline_claims)
        stamps = graph.get_all_stamps()

        # Should be 1 stamp since all nodes are connected
        assert len(stamps) == 1
        stamp = stamps[0]
        assert stamp.n_timelines == 3

    def test_disconnected_components_yield_multiple_stamps(self) -> None:
        """Disconnected components yield separate stamps."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
            ),
            MatchClaim(
                timeline_a_id="tl_c",
                timeline_b_id="tl_d",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_c",
                    coordinate_a=200.0,
                    timeline_b_id="tl_d",
                    coordinate_b=75.0,
                ),
            ),  # Disconnected
        ]
        graph = MatchGraph(claims)
        stamps = graph.get_all_stamps()

        assert len(stamps) == 2
        # Each stamp has 2 timelines
        assert all(s.n_timelines == 2 for s in stamps)


# endregion


# region MatchGraph Group Extension Tests


class TestMatchGraphGroupExtension:
    """Tests for extend_to_groups() method."""

    def test_extend_to_groups_adds_inferred_edges(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """Extending to groups adds inferred edges."""
        # Claim between dgt1 and some external timeline
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        # Set up group mapping
        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)

        # Original graph: 2 nodes, 1 edge
        # Extended graph should have 3 nodes (dgt1, external, audio)
        # and 2 edges (dgt1-external explicit, dgt1-audio inferred)
        assert extended.n_nodes == 3
        assert extended.n_edges == 2

    def test_extend_creates_correct_coordinates(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """Extended edges have correct converted coordinates."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,  # Midpoint of 1000px
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)

        # Get stamp and check audio coordinate
        # 500px in dgt1 (0-1000) should be 50s in audio (0-100)
        stamp, _ = extended.get_match_stamps()
        assert stamp.get_coordinate("audio") == pytest.approx(50.0)

    def test_extend_marks_inferred_edges(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """Extended edges are marked as inferred, not explicit."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)
        stamp, _ = extended.get_match_stamps()

        # Should have 1 explicit edge (dgt1-external)
        # and 1 inferred edge (dgt1-audio or audio-external)
        assert stamp.n_explicit_edges == 1
        assert stamp.n_inferred_edges == 1

    def test_extend_with_include_inferred_false(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """include_inferred=False returns original graph."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(
            groups, timeline_to_group, include_inferred=False
        )

        # Should be same as original
        assert extended.n_nodes == 2
        assert extended.n_edges == 1


# endregion


# region MatchGraph Filter Tests


class TestMatchGraphFilter:
    """Tests for MatchGraph.filter() method."""

    def test_filter_by_include_timelines(self) -> None:
        """Filter to include only specific timelines."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
            ),
            MatchClaim(
                timeline_a_id="tl_b",
                timeline_b_id="tl_c",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_b",
                    coordinate_a=50.0,
                    timeline_b_id="tl_c",
                    coordinate_b=25.0,
                ),
            ),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(include_timelines={"tl_a", "tl_b"})

        assert filtered.timeline_ids == {"tl_a", "tl_b"}
        assert filtered.n_edges == 1

    def test_filter_by_exclude_timelines(self) -> None:
        """Filter to exclude specific timelines."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
            ),
            MatchClaim(
                timeline_a_id="tl_b",
                timeline_b_id="tl_c",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_b",
                    coordinate_a=50.0,
                    timeline_b_id="tl_c",
                    coordinate_b=25.0,
                ),
            ),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(exclude_timelines={"tl_c"})

        assert "tl_c" not in filtered.timeline_ids
        assert filtered.n_edges == 1

    def test_filter_synchronous_only(self) -> None:
        """Filter to include only synchronous edges."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
                is_synchronous=True,
            ),
            MatchClaim(
                timeline_a_id="tl_b",
                timeline_b_id="tl_c",
                start_anchor=None,
                end_anchor=None,
                is_synchronous=False,
                metadata=MatchMetadata(agent="test", decision_criteria="structural"),
            ),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(synchronous_only=True)

        # Only the synchronous edge should remain
        assert filtered.n_edges == 1
        # tl_c should be removed (isolated after edge removal)
        assert "tl_c" not in filtered.timeline_ids

    def test_filter_explicit_only(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """Filter to include only explicit edges (remove inferred)."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)
        filtered = extended.filter(explicit_only=True)

        # Should only have the explicit edge
        assert filtered.n_edges == 1
        # Audio should be removed (only connected via inferred edge)
        assert "audio" not in filtered.timeline_ids

    def test_filter_removes_isolated_nodes(self) -> None:
        """Filtering edges removes nodes that become isolated."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
                is_synchronous=True,
            ),
            MatchClaim(
                timeline_a_id="tl_c",
                timeline_b_id="tl_d",
                start_anchor=None,
                end_anchor=None,
                is_synchronous=False,
            ),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(synchronous_only=True)

        # tl_c and tl_d should be removed
        assert filtered.timeline_ids == {"tl_a", "tl_b"}


# endregion


# region MatchGraph Serialization Tests


class TestMatchGraphSerialization:
    """Tests for MatchGraph serialization."""

    def test_to_dict_roundtrip(self, simple_interval_claim: MatchClaim) -> None:
        """Serialize and deserialize MatchGraph."""
        graph = MatchGraph([simple_interval_claim])
        data = graph.to_dict()
        restored = MatchGraph.from_dict(data)

        assert restored.n_claims == graph.n_claims
        assert restored.n_nodes == graph.n_nodes
        assert restored.n_edges == graph.n_edges

    def test_repr(self, simple_instant_claim: MatchClaim) -> None:
        """Test string representation."""
        graph = MatchGraph([simple_instant_claim])
        repr_str = repr(graph)

        assert "MatchGraph" in repr_str
        assert "claims=1" in repr_str
        assert "nodes=2" in repr_str
        assert "edges=1" in repr_str


# endregion


# region Integration with Thoresen PoC


class TestMatchGraphThoresenIntegration:
    """Integration tests using Thoresen PoC data."""

    # thoresen_segment_claims fixture is provided by conftest.py

    def test_thoresen_graph_structure(
        self, thoresen_segment_claims: list[MatchClaim]
    ) -> None:
        """Thoresen segment claims create correct graph structure."""
        graph = MatchGraph(thoresen_segment_claims)

        assert graph.n_claims == 5
        # Each interval claim has 2 anchors, but adjacent segments share
        # boundary coordinates. So we have 6 unique boundary points
        # (0, 967, 1934, 2901, 3868, 4835) for DGT1 and
        # (0, 866, 1733, 2600, 3464, 4328) for DGT2.
        # This gives 12 nodes and 6 unique edges.
        assert graph.n_nodes == 12
        assert graph.n_edges == 6
        assert graph.timeline_ids == {"dgt1", "dgt2"}

    def test_thoresen_coordinates(
        self, thoresen_segment_claims: list[MatchClaim]
    ) -> None:
        """Thoresen graph has correct boundary coordinates."""
        graph = MatchGraph(thoresen_segment_claims)

        dgt1_coords = graph.get_coordinates_for_timeline("dgt1")
        dgt2_coords = graph.get_coordinates_for_timeline("dgt2")

        # DGT1: 5 segments of 967 each = 4835 total
        assert dgt1_coords[0] == 0.0
        assert dgt1_coords[-1] == 4835.0

        # DGT2: segments of [866, 867, 867, 864, 864] = 4328 total
        assert dgt2_coords[0] == 0.0
        assert dgt2_coords[-1] == 4328.0

    def test_thoresen_stamps_at_segment_boundaries(
        self, thoresen_segment_claims: list[MatchClaim]
    ) -> None:
        """MatchStamps align at segment boundaries."""
        graph = MatchGraph(thoresen_segment_claims)

        # Get stamps from first claim (segment 1)
        start_stamp, end_stamp = graph.get_match_stamps()

        # Segment 1 starts at 0 in both
        assert start_stamp.get_coordinate("dgt1") == 0.0
        assert start_stamp.get_coordinate("dgt2") == 0.0

        # Segment 1 ends at 967 in DGT1, 866 in DGT2
        assert end_stamp.get_coordinate("dgt1") == 967.0
        assert end_stamp.get_coordinate("dgt2") == 866.0


# endregion


# region MatchGraph Overhaul Tests


class TestMatchGraphNonSynchronousClaims:
    """Non-synchronous claims stored as metadata, no edges."""

    def test_non_synchronous_claims_no_edges(self) -> None:
        """Non-synchronous claims do not create graph edges."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
                is_synchronous=True,
            ),
            MatchClaim.nomatch(
                event={"start": 200.0},
                source_tl_id="tl_a",
                target_tl_id="tl_b",
            ),
        ]
        graph = MatchGraph(claims)

        # Only the synchronous claim creates edges
        assert graph.n_claims == 2
        assert graph.n_nodes == 2  # Only from the synchronous claim
        assert graph.n_edges == 1

    def test_non_synchronous_claims_accessible_via_claims(self) -> None:
        """Non-synchronous claims are accessible via claims property."""
        sync_claim = MatchClaim(
            timeline_a_id="tl_a",
            timeline_b_id="tl_b",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl_a",
                coordinate_a=100.0,
                timeline_b_id="tl_b",
                coordinate_b=50.0,
            ),
        )
        nomatch_claim = MatchClaim.nomatch(
            event={"start": 200.0},
            source_tl_id="tl_a",
            target_tl_id="tl_c",
        )
        graph = MatchGraph([sync_claim, nomatch_claim])

        assert len(graph.claims) == 2
        assert len(graph.synchronous_claims) == 1
        assert len(graph.non_synchronous_claims) == 1
        assert graph.non_synchronous_claims[0] is nomatch_claim

    def test_only_non_synchronous_claims_empty_graph(self) -> None:
        """Graph with only non-synchronous claims has no nodes or edges."""
        claims = [
            MatchClaim.nomatch(
                event={"start": 100.0},
                source_tl_id="tl_a",
                target_tl_id="tl_b",
            ),
            MatchClaim.nomatch(
                event={"start": 200.0},
                source_tl_id="tl_c",
                target_tl_id="tl_d",
            ),
        ]
        graph = MatchGraph(claims)

        assert graph.n_claims == 2
        assert graph.n_nodes == 0
        assert graph.n_edges == 0
        assert len(graph.timeline_ids) == 0


class TestMatchGraphGetStamps:
    """Tests for get_stamps() method."""

    def test_get_stamps_returns_list(self, simple_instant_claim: MatchClaim) -> None:
        """get_stamps() returns a list of MatchStamps."""
        graph = MatchGraph([simple_instant_claim])
        stamps = graph.get_stamps()

        assert isinstance(stamps, list)
        assert len(stamps) == 1
        assert stamps[0].get_coordinate("tl_a") == 100.0
        assert stamps[0].get_coordinate("tl_b") == 50.0

    def test_get_stamps_one_per_component(self) -> None:
        """get_stamps() returns one MatchStamp per connected component."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_a",
                    coordinate_a=100.0,
                    timeline_b_id="tl_b",
                    coordinate_b=50.0,
                ),
            ),
            MatchClaim(
                timeline_a_id="tl_c",
                timeline_b_id="tl_d",
                start_anchor=AlignmentAnchor(
                    timeline_a_id="tl_c",
                    coordinate_a=200.0,
                    timeline_b_id="tl_d",
                    coordinate_b=75.0,
                ),
            ),  # Disconnected
        ]
        graph = MatchGraph(claims)
        stamps = graph.get_stamps()

        assert len(stamps) == 2
        assert all(s.n_timelines == 2 for s in stamps)

    def test_get_stamps_connected_chain(
        self, three_timeline_claims: list[MatchClaim]
    ) -> None:
        """get_stamps() merges connected chain into single stamp."""
        graph = MatchGraph(three_timeline_claims)
        stamps = graph.get_stamps()

        assert len(stamps) == 1
        assert stamps[0].n_timelines == 3

    def test_get_stamps_empty_graph(self) -> None:
        """get_stamps() on empty graph returns empty list."""
        graph = MatchGraph()
        stamps = graph.get_stamps()
        assert stamps == []

    def test_get_all_stamps_is_alias(self, simple_instant_claim: MatchClaim) -> None:
        """get_all_stamps() is an alias for get_stamps()."""
        graph = MatchGraph([simple_instant_claim])
        stamps = graph.get_stamps()
        all_stamps = graph.get_all_stamps()

        assert len(stamps) == len(all_stamps)
        # Same coordinates
        for s, a in zip(stamps, all_stamps):
            assert s.coordinates == a.coordinates


class TestMatchGraphExtendToGroupsImplicitClaims:
    """Tests for extend_to_groups() creating implicit MatchClaim objects."""

    def test_extension_creates_implicit_claims(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """extend_to_groups() adds implicit MatchClaims (case d)."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)

        # Original had 1 claim, extended should have 1 original + 1 implicit
        assert extended.n_claims == 2

        # Check that implicit claims exist
        implicit = [c for c in extended.claims if not c.is_explicit]
        assert len(implicit) == 1

        # Implicit claims should be synchronous
        for ic in implicit:
            assert ic.is_synchronous is True
            assert ic.is_explicit is False
            assert ic.start_anchor is not None

    def test_implicit_claims_have_source_claim_id(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """Implicit claims have source_claim_id for traceability."""
        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)

        implicit = [c for c in extended.claims if not c.is_explicit]
        assert len(implicit) == 1

        for ic in implicit:
            assert ic.source_claim_id == claim.id

    def test_two_groups_five_implicit_claims(self) -> None:
        """Two groups {TL1, TL4, TL5} and {TL2, TL6}: all implicit claims added.

        Scenario:
        - Group A: tl1 (1000px), tl4 (500px), tl5 (200px)
        - Group B: tl2 (800px), tl6 (400px)
        - Explicit claim: tl1@500 <-> tl2@400
        - Extension should add:
          - tl4 via group A (from tl1@500 -> tl4@250)
          - tl5 via group A (from tl1@500 -> tl5@100)
          - tl6 via group B (from tl2@400 -> tl6@200)
        """
        # Build group A: tl1, tl4, tl5
        tl1 = DiscreteGraphicalTimeline(length=1000, unit="pixels", uid="tl1")
        tl4 = DiscreteGraphicalTimeline(length=500, unit="pixels", uid="tl4")
        tl5 = DiscreteGraphicalTimeline(length=200, unit="pixels", uid="tl5")

        group_a = TimelineGroup(id="group_a")
        group_a.add_timeline(tl1)
        group_a.add_timeline(tl4)
        group_a.add_timeline(tl5)

        # Build group B: tl2, tl6
        tl2 = DiscreteGraphicalTimeline(length=800, unit="pixels", uid="tl2")
        tl6 = DiscreteGraphicalTimeline(length=400, unit="pixels", uid="tl6")

        group_b = TimelineGroup(id="group_b")
        group_b.add_timeline(tl2)
        group_b.add_timeline(tl6)

        # Explicit claim: tl1@500 <-> tl2@400
        claim = MatchClaim(
            timeline_a_id="tl1",
            timeline_b_id="tl2",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl1",
                coordinate_a=500.0,
                timeline_b_id="tl2",
                coordinate_b=400.0,
            ),
        )
        graph = MatchGraph([claim])

        groups = {"group_a": group_a, "group_b": group_b}
        timeline_to_group = {
            "tl1": "group_a",
            "tl4": "group_a",
            "tl5": "group_a",
            "tl2": "group_b",
            "tl6": "group_b",
        }

        extended = graph.extend_to_groups(groups, timeline_to_group)

        # All 5 timelines should be present
        assert extended.timeline_ids == {"tl1", "tl2", "tl4", "tl5", "tl6"}

        # Check stamps: all 5 timelines should be in one connected component
        stamps = extended.get_stamps()
        assert len(stamps) == 1
        stamp = stamps[0]
        assert stamp.n_timelines == 5

        # Verify coordinates via linear interpolation
        # tl1: 1000px, tl4: 500px, tl5: 200px (all linear from 0)
        # tl1@500 -> tl4: 500 * (500/1000) = 250
        assert stamp.get_coordinate("tl4") == pytest.approx(250.0)
        # tl1@500 -> tl5: 500 * (200/1000) = 100
        assert stamp.get_coordinate("tl5") == pytest.approx(100.0)
        # tl2@400 -> tl6: 400 * (400/800) = 200
        assert stamp.get_coordinate("tl6") == pytest.approx(200.0)

        # Count implicit claims
        implicit = [c for c in extended.claims if not c.is_explicit]
        # Exactly 3: tl1->tl4, tl1->tl5, tl2->tl6
        assert len(implicit) == 3


class TestMatchGraphExtendToGroupsFilters:
    """Tests for extend_to_groups() filter parameters."""

    @pytest.fixture
    def multi_group_setup(
        self,
    ) -> tuple[
        MatchClaim,
        dict[str, TimelineGroup],
        dict[str, str],
        dict[str, DiscreteGraphicalTimeline | ContinuousPhysicalTimeline],
    ]:
        """Set up a multi-group scenario for filter tests.

        Group A: dgt1 (1000 pixels), audio (100 seconds)
        External claim: dgt1@500 <-> external@25
        """
        dgt1 = DiscreteGraphicalTimeline(length=1000, unit="pixels", uid="dgt1")
        audio = ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="audio")

        group_a = TimelineGroup(id="group_a")
        group_a.add_timeline(dgt1)
        group_a.add_timeline(audio)

        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="external",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="external",
                coordinate_b=25.0,
            ),
        )

        groups = {"group_a": group_a}
        timeline_to_group = {"dgt1": "group_a", "audio": "group_a"}
        timelines = {"dgt1": dgt1, "audio": audio}

        return claim, groups, timeline_to_group, timelines

    def test_include_timelines_filter(
        self,
        multi_group_setup: tuple,
    ) -> None:
        """include_timelines restricts which timelines get implicit claims."""
        claim, groups, timeline_to_group, timelines = multi_group_setup
        graph = MatchGraph([claim])

        # Only extend to dgt1 (should NOT add audio)
        extended = graph.extend_to_groups(
            groups,
            timeline_to_group,
            include_timelines={"dgt1", "external"},
        )

        # Audio should NOT be in the graph
        assert "audio" not in extended.timeline_ids
        assert extended.n_nodes == 2
        assert extended.n_edges == 1

    def test_exclude_timelines_filter(
        self,
        multi_group_setup: tuple,
    ) -> None:
        """exclude_timelines prevents specific timelines from extension."""
        claim, groups, timeline_to_group, timelines = multi_group_setup
        graph = MatchGraph([claim])

        # Exclude audio
        extended = graph.extend_to_groups(
            groups,
            timeline_to_group,
            exclude_timelines={"audio"},
        )

        assert "audio" not in extended.timeline_ids

    def test_include_domains_filter(
        self,
        multi_group_setup: tuple,
    ) -> None:
        """include_domains restricts extension by timeline domain."""
        claim, groups, timeline_to_group, timelines = multi_group_setup
        graph = MatchGraph([claim])

        # Only extend to graphical domain (should NOT add audio)
        extended = graph.extend_to_groups(
            groups,
            timeline_to_group,
            include_domains={Domain.graphical},
            timelines=timelines,
        )

        # Audio (physical) should NOT be extended into the graph
        assert "audio" not in extended.timeline_ids

    def test_include_units_filter(
        self,
        multi_group_setup: tuple,
    ) -> None:
        """include_units restricts extension by timeline unit."""
        claim, groups, timeline_to_group, timelines = multi_group_setup
        graph = MatchGraph([claim])

        # Only extend to pixels (should NOT add audio/seconds)
        extended = graph.extend_to_groups(
            groups,
            timeline_to_group,
            include_units={TimeUnit.pixels},
            timelines=timelines,
        )

        # Audio (seconds) should NOT be extended
        assert "audio" not in extended.timeline_ids


class TestMatchGraphFilterPhase64:
    """Tests for filter() method with domain/unit filters."""

    def test_filter_by_include_domains(self) -> None:
        """filter() with include_domains removes timelines of wrong domain."""
        dgt1 = DiscreteGraphicalTimeline(length=1000, unit="pixels", uid="dgt1")
        audio = ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="audio")

        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="audio",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="audio",
                coordinate_b=50.0,
            ),
        )
        graph = MatchGraph([claim])

        # Filter to only graphical
        filtered = graph.filter(
            include_domains={Domain.graphical},
            timelines={"dgt1": dgt1, "audio": audio},
        )

        # Audio should be removed
        assert "audio" not in filtered.timeline_ids
        # Graph should have no edges (only dgt1 remains, isolated)
        assert filtered.n_edges == 0

    def test_filter_by_include_units(self) -> None:
        """filter() with include_units removes timelines of wrong unit."""
        dgt1 = DiscreteGraphicalTimeline(length=1000, unit="pixels", uid="dgt1")
        audio = ContinuousPhysicalTimeline(length=100.0, unit="seconds", uid="audio")

        claim = MatchClaim(
            timeline_a_id="dgt1",
            timeline_b_id="audio",
            start_anchor=AlignmentAnchor(
                timeline_a_id="dgt1",
                coordinate_a=500.0,
                timeline_b_id="audio",
                coordinate_b=50.0,
            ),
        )
        graph = MatchGraph([claim])

        filtered = graph.filter(
            include_units={TimeUnit.seconds},
            timelines={"dgt1": dgt1, "audio": audio},
        )

        # dgt1 (pixels) should be removed, audio should remain but isolated
        assert "dgt1" not in filtered.timeline_ids
        # No edges remain (isolated nodes removed)
        assert filtered.n_edges == 0

    def test_filter_keeps_non_synchronous_claims(self) -> None:
        """filter() preserves non-sync claims connecting remaining timelines."""
        sync_claim = MatchClaim(
            timeline_a_id="tl_a",
            timeline_b_id="tl_b",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl_a",
                coordinate_a=100.0,
                timeline_b_id="tl_b",
                coordinate_b=50.0,
            ),
        )
        nomatch_claim = MatchClaim.nomatch(
            event={"start": 200.0},
            source_tl_id="tl_a",
            target_tl_id="tl_b",
        )
        unrelated_nomatch = MatchClaim.nomatch(
            event={"start": 300.0},
            source_tl_id="tl_a",
            target_tl_id="tl_c",
        )
        graph = MatchGraph([sync_claim, nomatch_claim, unrelated_nomatch])

        filtered = graph.filter(include_timelines={"tl_a", "tl_b"})

        # The sync claim and the nomatch between tl_a and tl_b should remain
        # The nomatch involving tl_c should be dropped
        assert len(filtered.claims) == 2
        claim_tl_sets = [{c.timeline_a_id, c.timeline_b_id} for c in filtered.claims]
        assert {"tl_a", "tl_b"} in claim_tl_sets
        assert {"tl_a", "tl_c"} not in claim_tl_sets


class TestMatchStampGetGroupCoordinates:
    """Tests for MatchStamp.get_group_coordinates() fix."""

    def test_get_group_coordinates(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """get_group_coordinates uses timeline_ids, not timelines dict."""
        stamp = MatchStamp(
            coordinates={"dgt1": 500.0, "audio": 50.0, "external": 25.0},
            anchor_edges=[("dgt1", "external")],
            inferred_edges=[("dgt1", "audio")],
        )

        group_coords = stamp.get_group_coordinates(dgt1_group)

        assert group_coords == {"dgt1": 500.0, "audio": 50.0}
        assert "external" not in group_coords


# endregion
