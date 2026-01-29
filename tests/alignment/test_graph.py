"""Tests for MatchGraph and MatchStamp classes.

This module tests the graph-building layer of the alignment infrastructure:
- MatchStamp: Cross-group timestamp representation
- MatchGraph: Graph of MatchClaims with networkx integration
"""

from __future__ import annotations

import pytest

from timetoalign.alignment import (
    MatchClaim,
    MatchMetadata,
    TimelineGroup,
)
from timetoalign.alignment.anchors import _reset_anchor_ids, _reset_claim_ids
from timetoalign.alignment.graph import MatchGraph, MatchStamp
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
    _reset_anchor_ids()
    _reset_claim_ids()


@pytest.fixture
def simple_instant_claim() -> MatchClaim:
    """Simple instant match between two timelines."""
    return MatchClaim.instant(
        timeline_a_id="tl_a",
        coordinate_a=100.0,
        timeline_b_id="tl_b",
        coordinate_b=50.0,
        metadata=MatchMetadata(agent="test", decision_criteria="manual"),
    )


@pytest.fixture
def simple_interval_claim() -> MatchClaim:
    """Simple interval match between two timelines."""
    return MatchClaim.interval(
        timeline_a_id="tl_a",
        start_a=0.0,
        end_a=100.0,
        timeline_b_id="tl_b",
        start_b=0.0,
        end_b=50.0,
        metadata=MatchMetadata(agent="test", decision_criteria="manual"),
    )


@pytest.fixture
def three_timeline_claims() -> list[MatchClaim]:
    """Claims connecting three timelines: A <-> B <-> C."""
    return [
        MatchClaim.instant(
            timeline_a_id="tl_a",
            coordinate_a=100.0,
            timeline_b_id="tl_b",
            coordinate_b=50.0,
        ),
        MatchClaim.instant(
            timeline_a_id="tl_b",
            coordinate_a=50.0,
            timeline_b_id="tl_c",
            coordinate_b=25.0,
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
            MatchClaim.instant("tl_a", 100.0, "tl_b", 50.0),
            MatchClaim.instant("tl_c", 200.0, "tl_d", 75.0),  # Disconnected
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
        claim = MatchClaim.instant(
            timeline_a_id="dgt1",
            coordinate_a=500.0,
            timeline_b_id="external",
            coordinate_b=25.0,
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
        claim = MatchClaim.instant(
            timeline_a_id="dgt1",
            coordinate_a=500.0,  # Midpoint of 1000px
            timeline_b_id="external",
            coordinate_b=25.0,
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
        claim = MatchClaim.instant("dgt1", 500.0, "external", 25.0)
        graph = MatchGraph([claim])

        groups = {"group1": dgt1_group}
        timeline_to_group = {"dgt1": "group1", "audio": "group1"}

        extended = graph.extend_to_groups(groups, timeline_to_group)
        stamp, _ = extended.get_match_stamps()

        # Should have 1 explicit edge (dgt1-external)
        # and 1 inferred edge (dgt1-audio or audio-external)
        assert stamp.n_explicit_edges == 1
        assert stamp.n_inferred_edges >= 1

    def test_extend_with_include_inferred_false(
        self,
        dgt1_group: TimelineGroup,
    ) -> None:
        """include_inferred=False returns original graph."""
        claim = MatchClaim.instant("dgt1", 500.0, "external", 25.0)
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
            MatchClaim.instant("tl_a", 100.0, "tl_b", 50.0),
            MatchClaim.instant("tl_b", 50.0, "tl_c", 25.0),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(include_timelines={"tl_a", "tl_b"})

        assert filtered.timeline_ids == {"tl_a", "tl_b"}
        assert filtered.n_edges == 1

    def test_filter_by_exclude_timelines(self) -> None:
        """Filter to exclude specific timelines."""
        claims = [
            MatchClaim.instant("tl_a", 100.0, "tl_b", 50.0),
            MatchClaim.instant("tl_b", 50.0, "tl_c", 25.0),
        ]
        graph = MatchGraph(claims)

        filtered = graph.filter(exclude_timelines={"tl_c"})

        assert "tl_c" not in filtered.timeline_ids
        assert filtered.n_edges == 1

    def test_filter_synchronous_only(self) -> None:
        """Filter to include only synchronous edges."""
        claims = [
            MatchClaim.instant("tl_a", 100.0, "tl_b", 50.0, is_synchronous=True),
            MatchClaim.instant(
                "tl_b",
                50.0,
                "tl_c",
                25.0,
                metadata=MatchMetadata(agent="test", decision_criteria="structural"),
                is_synchronous=False,
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
        claim = MatchClaim.instant("dgt1", 500.0, "external", 25.0)
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
            MatchClaim.instant("tl_a", 100.0, "tl_b", 50.0, is_synchronous=True),
            MatchClaim.instant("tl_c", 200.0, "tl_d", 75.0, is_synchronous=False),
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

    @pytest.fixture
    def thoresen_segment_claims(self) -> list[MatchClaim]:
        """5 segment claims from Thoresen PoC."""
        # Exact values from test_thoresen_poc.py
        dgt1_lengths = [967, 967, 967, 967, 967]
        dgt2_lengths = [866, 867, 867, 864, 864]

        claims = []
        offset_dgt1 = 0
        offset_dgt2 = 0

        for i in range(5):
            claim = MatchClaim.interval(
                timeline_a_id="dgt1",
                start_a=float(offset_dgt1),
                end_a=float(offset_dgt1 + dgt1_lengths[i]),
                timeline_b_id="dgt2",
                start_b=float(offset_dgt2),
                end_b=float(offset_dgt2 + dgt2_lengths[i]),
            )
            claims.append(claim)
            offset_dgt1 += dgt1_lengths[i]
            offset_dgt2 += dgt2_lengths[i]

        return claims

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
