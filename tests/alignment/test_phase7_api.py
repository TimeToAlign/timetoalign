"""Tests for Phase 7: Unified Stamp & Query API.

Covers:
- Step 7.3: AlignmentBundle.get_match_claims()
- Step 7.4: MatchClaim.get_matchstamp()
- Step 7.4a: AlignmentBundle MatchGraph cache
- Step 7.5: AlignmentBundle.get_matchstamp_at()
- Step 7.6: MatchGraph.get_matchstamp() + split_components()
- Step 7.7a: MatchStamp __str__ and _repr_html_
- Step 7.7b: MatchClaim __str__ and _repr_html_
- Step 7.9: transfer() docstring fix
- Step 7.11: Top-level exports
"""

from __future__ import annotations

import pytest

from timetoalign.alignment.anchors import (
    AlignmentAnchor,
    MatchClaim,
    MatchMetadata,
)
from timetoalign.alignment.bundle import AlignmentBundle
from timetoalign.alignment.graph import MatchGraph, MatchStamp
from timetoalign.timelines import Timeline

# region Helpers


def _make_star_bundle():
    """Build a star-topology bundle: 1 score + 3 performers.

    score_tl (length=100) in "score_group"
    perf1_tl (length=200) standalone
    perf2_tl (length=200) standalone
    perf3_tl (length=200) standalone

    Claims: score <-> each perf at coordinates 0, 25, 50, 75, 100
    Plus one NOMATCH claim: score <-> perf3 (non-synchronous).

    Bundle UIDs = actual timeline IDs (no UID mapping needed since
    add_match_claims uses actual timeline IDs in claims).
    """
    score_tl = Timeline(length=100, uid="score:clt1", name="Score")
    perf1_tl = Timeline(length=200, uid="perf:dlt1", name="Perf1")
    perf2_tl = Timeline(length=200, uid="perf:dlt2", name="Perf2")
    perf3_tl = Timeline(length=200, uid="perf:dlt3", name="Perf3")

    bundle = AlignmentBundle(id="star_test")
    bundle.add_timeline(score_tl, uid="score:clt1", as_group="score_group")
    bundle.add_timeline(perf1_tl, uid="perf:dlt1", as_group="perf1_group")
    bundle.add_timeline(perf2_tl, uid="perf:dlt2", as_group="perf2_group")
    bundle.add_timeline(perf3_tl, uid="perf:dlt3", as_group="perf3_group")

    claims = []
    # 5 coordinates per performer
    for i in range(5):
        coord_s = float(i * 25)
        for perf_id, factor in [
            ("perf:dlt1", 2.0),
            ("perf:dlt2", 1.5),
            ("perf:dlt3", 1.8),
        ]:
            coord_p = coord_s * factor
            claims.append(
                MatchClaim(
                    timeline_a_id="score:clt1",
                    timeline_b_id=perf_id,
                    start_anchor=AlignmentAnchor(
                        timeline_a_id="score:clt1",
                        coordinate_a=coord_s,
                        timeline_b_id=perf_id,
                        coordinate_b=coord_p,
                    ),
                    is_synchronous=True,
                )
            )

    # One NOMATCH claim
    claims.append(
        MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt3",
            is_synchronous=False,
        )
    )

    bundle.add_match_claims(claims)
    return bundle, claims


# endregion


# region Step 7.3: AlignmentBundle.get_match_claims()


class TestGetMatchClaims:
    """Tests for AlignmentBundle.get_match_claims()."""

    def test_no_filters_returns_all(self):
        """No filters returns all claims."""
        bundle, claims = _make_star_bundle()
        result = bundle.get_match_claims()
        assert len(result) == len(claims)

    def test_filter_by_timeline_id(self):
        """Filter by single timeline ID."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(timeline_id="perf:dlt1")
        # 5 synchronous claims: score <-> perf:dlt1 at 5 coordinates
        assert len(result) == 5
        for c in result:
            assert c.connects("perf:dlt1")

    def test_filter_by_id_pattern(self):
        """Filter by regex pattern."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(id_pattern=r"^perf:")
        # All 15 synchronous + 1 NOMATCH involve perf: timelines
        assert len(result) == 16

    def test_filter_synchronous_only(self):
        """synchronous_only excludes NOMATCH."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(synchronous_only=True)
        assert len(result) == 15  # 5 claims * 3 performers
        for c in result:
            assert c.is_synchronous

    def test_filter_nomatch_only(self):
        """nomatch_only returns only NOMATCH claims."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(nomatch_only=True)
        assert len(result) == 1
        assert not result[0].is_synchronous

    def test_filter_between(self):
        """between filter for exact timeline pair."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(
            between=("score:clt1", "perf:dlt2"),
            synchronous_only=True,
        )
        assert len(result) == 5
        for c in result:
            assert c.connects_both("score:clt1", "perf:dlt2")

    def test_filter_combined(self):
        """Multiple filters are AND-combined."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(
            timeline_id="perf:dlt3",
            synchronous_only=True,
        )
        # 5 synchronous claims for perf:dlt3 (the NOMATCH is excluded)
        assert len(result) == 5

    def test_filter_pattern_and_nomatch(self):
        """Pattern + nomatch_only."""
        bundle, _ = _make_star_bundle()
        result = bundle.get_match_claims(
            id_pattern=r"dlt3$",
            nomatch_only=True,
        )
        assert len(result) == 1


# endregion


# region Step 7.6: MatchGraph.get_matchstamp() + split_components()


class TestMatchGraphGetMatchstamp:
    """Tests for MatchGraph.get_matchstamp()."""

    def test_single_component(self):
        """Single connected component returns one MatchStamp."""
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
        mg = MatchGraph(claims=claims)
        stamp = mg.get_matchstamp()
        assert stamp.n_timelines == 3
        assert stamp.get_coordinate("tl_a") == 100.0
        assert stamp.get_coordinate("tl_b") == 50.0
        assert stamp.get_coordinate("tl_c") == 25.0

    def test_multi_component_raises(self):
        """Multiple disconnected components raise ValueError."""
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
            ),
        ]
        mg = MatchGraph(claims=claims)
        assert mg.n_components == 2
        with pytest.raises(ValueError, match="disconnected components"):
            mg.get_matchstamp()

    def test_empty_graph_raises(self):
        """Empty graph raises ValueError."""
        mg = MatchGraph()
        with pytest.raises(ValueError, match="no synchronous claims"):
            mg.get_matchstamp()

    def test_only_nomatch_raises(self):
        """Graph with only NOMATCH claims raises ValueError."""
        claims = [
            MatchClaim(
                timeline_a_id="tl_a",
                timeline_b_id="tl_b",
                is_synchronous=False,
            ),
        ]
        mg = MatchGraph(claims=claims)
        with pytest.raises(ValueError, match="no synchronous claims"):
            mg.get_matchstamp()


class TestMatchGraphSplitComponents:
    """Tests for MatchGraph.split_components()."""

    def test_single_component(self):
        """Single component returns list of one MatchGraph."""
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
        ]
        mg = MatchGraph(claims=claims)
        components = mg.split_components()
        assert len(components) == 1
        stamp = components[0].get_matchstamp()
        assert stamp.n_timelines == 2

    def test_two_components(self):
        """Two disconnected components split correctly."""
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
            ),
        ]
        mg = MatchGraph(claims=claims)
        components = mg.split_components()
        assert len(components) == 2
        # Each component can produce a single matchstamp
        for comp in components:
            stamp = comp.get_matchstamp()
            assert stamp.n_timelines == 2

    def test_empty_graph(self):
        """Empty graph splits to empty list."""
        mg = MatchGraph()
        assert mg.split_components() == []

    def test_n_components_property(self):
        """n_components property works correctly."""
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
        ]
        mg = MatchGraph(claims=claims)
        assert mg.n_components == 1


class TestMatchGraphStarTopology:
    """Test MatchGraph with star topology (1 score + N performers).

    Simulates the Vienna 1xN pattern: all performers connect to the
    score at the same coordinate, forming one connected component.
    """

    def test_star_single_coordinate(self):
        """All claims at one coordinate form one component."""
        claims = []
        for i in range(5):
            perf_id = f"perf:dlt{i + 1}"
            claims.append(
                MatchClaim(
                    timeline_a_id="score:clt1",
                    timeline_b_id=perf_id,
                    start_anchor=AlignmentAnchor(
                        timeline_a_id="score:clt1",
                        coordinate_a=0.0,
                        timeline_b_id=perf_id,
                        coordinate_b=float(i * 10),
                    ),
                )
            )
        mg = MatchGraph(claims=claims)
        assert mg.n_components == 1
        stamp = mg.get_matchstamp()
        assert stamp.n_timelines == 6  # 1 score + 5 performers
        assert stamp.get_coordinate("score:clt1") == 0.0

    def test_star_determinism(self):
        """Building graph from any single claim gives same stamp.

        This tests the Vienna critical requirement: the same MatchGraph
        (and thus MatchStamp) must result regardless of which claim
        seeds the graph.
        """
        claims = []
        for i in range(5):
            perf_id = f"perf:dlt{i + 1}"
            claims.append(
                MatchClaim(
                    timeline_a_id="score:clt1",
                    timeline_b_id=perf_id,
                    start_anchor=AlignmentAnchor(
                        timeline_a_id="score:clt1",
                        coordinate_a=0.0,
                        timeline_b_id=perf_id,
                        coordinate_b=float(i * 10),
                    ),
                )
            )
        # Build from ALL claims
        mg_full = MatchGraph(claims=claims)
        stamp_full = mg_full.get_matchstamp()

        # Each individual claim should produce a 2-timeline stamp alone
        # (without transitive closure). But building from all claims
        # at the same score coordinate gives the full star.
        assert stamp_full.n_timelines == 6


# endregion


# region Step 7.4: MatchClaim.get_matchstamp()


class TestMatchClaimGetMatchstamp:
    """Tests for MatchClaim.get_matchstamp()."""

    def test_reduced_stamp(self):
        """from_graph=False returns 2-timeline MatchStamp."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
        )
        stamp = claim.get_matchstamp(from_graph=False)
        assert stamp is not None
        assert stamp.n_timelines == 2
        assert stamp.get_coordinate("score:clt1") == 10.0
        assert stamp.get_coordinate("perf:dlt1") == 128.0

    def test_nomatch_returns_none(self):
        """NOMATCH claim returns None."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            is_synchronous=False,
        )
        assert claim.get_matchstamp(from_graph=False) is None

    def test_from_graph_without_bundle_raises(self):
        """from_graph=True without bundle raises ValueError."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
        )
        with pytest.raises(ValueError, match="bundle is required"):
            claim.get_matchstamp()  # from_graph=True by default

    def test_from_graph_with_bundle(self):
        """from_graph=True with bundle returns full stamp."""
        bundle, claims = _make_star_bundle()
        # Pick the first synchronous claim
        sync_claims = [c for c in claims if c.is_synchronous]
        claim = sync_claims[0]
        stamp = claim.get_matchstamp(bundle=bundle)
        assert stamp is not None
        # At coordinate 0.0 on score, all 3 performers are connected
        assert stamp.n_timelines == 4  # score + 3 performers


# endregion


# region Step 7.4a: AlignmentBundle MatchGraph cache


class TestMatchGraphCache:
    """Tests for AlignmentBundle MatchGraph cache."""

    def test_cache_hit(self):
        """Second lookup returns cached MatchGraph."""
        bundle, _ = _make_star_bundle()
        mg1 = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        mg2 = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        assert mg1 is mg2  # Same object

    def test_cache_via_different_key(self):
        """Lookup via performer node returns same graph as score node."""
        bundle, _ = _make_star_bundle()
        mg_score = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        # perf:dlt1 at coordinate 0.0 should map to the same graph
        mg_perf = bundle._get_or_build_matchgraph("perf:dlt1", 0.0)
        assert mg_score is mg_perf

    def test_cache_invalidation(self):
        """add_match_claims() clears the cache."""
        bundle, _ = _make_star_bundle()
        mg1 = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        # Add more claims
        bundle.add_match_claims(
            [
                MatchClaim(
                    timeline_a_id="score:clt1",
                    timeline_b_id="perf:dlt1",
                    start_anchor=AlignmentAnchor(
                        timeline_a_id="score:clt1",
                        coordinate_a=99.0,
                        timeline_b_id="perf:dlt1",
                        coordinate_b=198.0,
                    ),
                ),
            ]
        )
        mg2 = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        assert mg1 is not mg2  # Cache was invalidated

    def test_cache_no_claims_raises(self):
        """Cache miss with no matching claims raises ValueError."""
        bundle, _ = _make_star_bundle()
        with pytest.raises(ValueError, match="No synchronous claims"):
            bundle._get_or_build_matchgraph("score:clt1", 999.0)

    def test_different_coordinates_different_graphs(self):
        """Different coordinates produce different cached graphs."""
        bundle, _ = _make_star_bundle()
        mg0 = bundle._get_or_build_matchgraph("score:clt1", 0.0)
        mg25 = bundle._get_or_build_matchgraph("score:clt1", 25.0)
        assert mg0 is not mg25


# endregion


# region Step 7.5: AlignmentBundle.get_matchstamp_at()


class TestGetMatchstampAt:
    """Tests for AlignmentBundle.get_matchstamp_at()."""

    def test_basic(self):
        """Basic cross-group MatchStamp at a coordinate."""
        bundle, _ = _make_star_bundle()
        stamp = bundle.get_matchstamp_at(0.0, "score:clt1")
        assert stamp.n_timelines == 4  # score + 3 performers
        assert stamp.get_coordinate("score:clt1") == 0.0
        assert stamp.get_coordinate("perf:dlt1") == 0.0
        assert stamp.get_coordinate("perf:dlt2") == 0.0
        assert stamp.get_coordinate("perf:dlt3") == 0.0

    def test_nonzero_coordinate(self):
        """MatchStamp at a non-zero coordinate."""
        bundle, _ = _make_star_bundle()
        stamp = bundle.get_matchstamp_at(50.0, "score:clt1")
        assert stamp.n_timelines == 4
        assert stamp.get_coordinate("score:clt1") == 50.0
        assert stamp.get_coordinate("perf:dlt1") == 100.0  # 50 * 2.0
        assert stamp.get_coordinate("perf:dlt2") == 75.0  # 50 * 1.5
        assert stamp.get_coordinate("perf:dlt3") == 90.0  # 50 * 1.8

    def test_not_in_bundle_raises(self):
        """Unknown timeline raises KeyError."""
        bundle, _ = _make_star_bundle()
        with pytest.raises(KeyError, match="not in bundle"):
            bundle.get_matchstamp_at(0.0, "nonexistent")

    def test_no_claims_at_coordinate_raises(self):
        """No claims at coordinate raises ValueError."""
        bundle, _ = _make_star_bundle()
        with pytest.raises(ValueError, match="No synchronous claims"):
            bundle.get_matchstamp_at(999.0, "score:clt1")

    def test_filtered_by_pattern(self):
        """Regex filter reduces output."""
        bundle, _ = _make_star_bundle()
        stamp = bundle.get_matchstamp_at(
            0.0,
            "score:clt1",
            id_pattern=r"dlt[12]$",
        )
        # Only perf:dlt1 and perf:dlt2 pass the filter
        # (score:clt1 does NOT match the pattern, so it's also excluded)
        assert "perf:dlt1" in stamp.coordinates
        assert "perf:dlt2" in stamp.coordinates
        assert "perf:dlt3" not in stamp.coordinates

    def test_filtered_by_timeline_ids(self):
        """timeline_ids filter reduces output."""
        bundle, _ = _make_star_bundle()
        stamp = bundle.get_matchstamp_at(
            0.0,
            "score:clt1",
            timeline_ids={"score:clt1", "perf:dlt1"},
        )
        assert stamp.n_timelines == 2
        assert "score:clt1" in stamp.coordinates
        assert "perf:dlt1" in stamp.coordinates


# endregion


# region Step 7.7a: MatchStamp display


class TestMatchStampDisplay:
    """Tests for MatchStamp __str__ and _repr_html_."""

    def test_str_header(self):
        """__str__ includes timeline count and edge count."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
            anchor_edges=[("tl_a", "tl_b")],
        )
        s = str(stamp)
        assert "MatchStamp" in s
        assert "2 timelines" in s
        assert "1 edges" in s

    def test_str_entries(self):
        """__str__ shows coordinate values."""
        stamp = MatchStamp(
            coordinates={"score": 10.0, "audio": 45.5},
            anchor_edges=[("score", "audio")],
        )
        s = str(stamp)
        assert "score" in s
        assert "10" in s
        assert "audio" in s
        assert "45.5" in s

    def test_str_empty(self):
        """Empty stamp shows just header."""
        stamp = MatchStamp()
        s = str(stamp)
        assert "0 timelines" in s

    def test_str_integer_formatting(self):
        """Integer-valued coordinates shown without decimals."""
        stamp = MatchStamp(
            coordinates={"tl_a": 100.0, "tl_b": 50.0},
            anchor_edges=[("tl_a", "tl_b")],
        )
        s = str(stamp)
        assert "100" in s
        assert "100.0" not in s

    def test_repr_html_valid(self):
        """_repr_html_ produces valid HTML."""
        stamp = MatchStamp(
            coordinates={"score": 10.0, "audio": 45.5},
            anchor_edges=[("score", "audio")],
        )
        html = stamp._repr_html_()
        assert "<table" in html
        assert "MatchStamp" in html
        assert "score" in html
        assert "audio" in html

    def test_repr_html_anchor_bold(self):
        """Anchor timelines are bold in HTML."""
        stamp = MatchStamp(
            coordinates={"score": 10.0, "audio": 45.5},
            anchor_edges=[("score", "audio")],
        )
        html = stamp._repr_html_()
        assert "<strong>score</strong>" in html

    def test_repr_html_inferred_greyed(self):
        """Inferred timelines are greyed in HTML."""
        stamp = MatchStamp(
            coordinates={"score": 10.0, "audio": 45.5, "video": 1000.0},
            anchor_edges=[("score", "audio")],
            inferred_edges=[("audio", "video")],
        )
        html = stamp._repr_html_()
        assert "color: #666" in html
        assert "inferred" in html


# endregion


# region Step 7.7b: MatchClaim display


class TestMatchClaimDisplay:
    """Tests for MatchClaim __str__ and _repr_html_."""

    def test_str_synchronous_instant(self):
        """__str__ for synchronous instant claim."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
        )
        s = str(claim)
        assert "synchronous, instant" in s
        assert "score:clt1" in s
        assert "perf:dlt1" in s
        assert "@10" in s
        assert "@128" in s

    def test_str_synchronous_interval(self):
        """__str__ for synchronous interval claim."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=0.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=0.0,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
        )
        s = str(claim)
        assert "synchronous, interval" in s
        assert "[0 -- 10]" in s
        assert "[0 -- 128]" in s

    def test_str_nomatch(self):
        """__str__ for NOMATCH claim."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            is_synchronous=False,
        )
        s = str(claim)
        assert "NOMATCH" in s
        assert "score:clt1" in s
        assert "perf:dlt1" in s

    def test_str_with_metadata(self):
        """__str__ shows metadata."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
            metadata=MatchMetadata(
                agent="partitura",
                decision_criteria="note_matching",
                certainty=0.95,
            ),
        )
        s = str(claim)
        assert "Metadata:" in s
        assert "partitura" in s
        assert "0.95" in s

    def test_str_inferred(self):
        """__str__ shows [inferred] flag."""
        claim = MatchClaim(
            timeline_a_id="tl_a",
            timeline_b_id="tl_b",
            start_anchor=AlignmentAnchor(
                timeline_a_id="tl_a",
                coordinate_a=0.0,
                timeline_b_id="tl_b",
                coordinate_b=0.0,
            ),
            is_explicit=False,
            source_claim_id="claim_1",
        )
        s = str(claim)
        assert "[inferred]" in s
        assert "Source:" in s
        assert "claim_1" in s

    def test_repr_html_valid(self):
        """_repr_html_ produces valid HTML."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            start_anchor=AlignmentAnchor(
                timeline_a_id="score:clt1",
                coordinate_a=10.0,
                timeline_b_id="perf:dlt1",
                coordinate_b=128.0,
            ),
        )
        html = claim._repr_html_()
        assert "<table" in html
        assert "MatchClaim" in html
        assert "score:clt1" in html

    def test_repr_html_nomatch_badge(self):
        """NOMATCH claim has red badge in HTML."""
        claim = MatchClaim(
            timeline_a_id="score:clt1",
            timeline_b_id="perf:dlt1",
            is_synchronous=False,
        )
        html = claim._repr_html_()
        assert "NOMATCH" in html
        assert "#ffcdd2" in html  # Red background


# endregion


# region Step 7.9: transfer() docstring fix


class TestTransferDocstring:
    """Verify transfer() docstring no longer claims to be primary."""

    def test_docstring_not_primary(self):
        """transfer() docstring must NOT say 'primary user-facing'."""
        docstring = AlignmentBundle.transfer.__doc__
        assert "primary user-facing" not in docstring.lower()
        assert "get_matchstamp_at" in docstring


# endregion


# region Step 7.11: Top-level exports


class TestTopLevelExports:
    """Verify that MatchGraph, MatchStamp, ClaimFilter are in top-level __all__."""

    def test_matchgraph_importable(self):
        """MatchGraph importable from top-level."""
        from timetoalign import MatchGraph as MG

        assert MG is MatchGraph

    def test_matchstamp_importable(self):
        """MatchStamp importable from top-level."""
        from timetoalign import MatchStamp as MS

        assert MS is MatchStamp

    def test_claimfilter_importable(self):
        """ClaimFilter importable from top-level."""
        from timetoalign import ClaimFilter
        from timetoalign.alignment.filters import ClaimFilter as CF

        assert ClaimFilter is CF

    def test_in_all(self):
        """All three are in __all__."""
        import timetoalign

        assert "MatchGraph" in timetoalign.__all__
        assert "MatchStamp" in timetoalign.__all__
        assert "ClaimFilter" in timetoalign.__all__


# endregion
