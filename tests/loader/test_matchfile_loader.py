"""Tests for MatchfileLoader — Vienna Match (.match) alignment files.

This module tests the MatchfileLoader against the Vienna 1x22 dataset
(Chopin Op. 10 No. 3, 22 performances). It verifies:

- Header parsing and raw file format handling
- Score timeline construction (quarter-beat coordinates, C-Maps)
- Performance timeline construction (tick coordinates, C-Maps)
- MatchClaim generation (matched notes and deletion NOMATCH sentinels)
- AlignmentBundle assembly (single-file and multi-file)

All counts are exact per the Zero Tolerance Validation Policy.
See tests/data/vienna_1x22/README.md for gold standard values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from timetoalign.alignment.anchors import _reset_anchor_ids, _reset_claim_ids
from timetoalign.alignment.bundle import AlignmentBundle, _reset_bundle_ids
from timetoalign.alignment.groups import _reset_group_ids
from timetoalign.core import TimeUnit
from timetoalign.loader.alignment.matchfile import MatchfileLoader
from timetoalign.maps.linear import ScalarMap, ShiftMap
from timetoalign.timelines.types import (
    ContinuousLogicalTimeline,
    DiscreteLogicalTimeline,
)

# region Test Data

VIENNA_DATA_DIR = Path(__file__).parent.parent / "data" / "vienna_1x22"
P01_MATCH = VIENNA_DATA_DIR / "Chopin_op10_no3_p01.match"
ALL_MATCH_FILES = sorted(VIENNA_DATA_DIR.glob("*.match"))

# Gold standard counts (from README.md)
SNOTE_COUNT = 454  # snote records per .match file (all 22 identical)
P01_DELETION_COUNT = 3  # deletions in p01 (n356, n359, n454)
P01_MATCH_COUNT = 451  # matched notes in p01 (454 - 3)
P01_PERF_NOTE_COUNT = 451  # performance notes in p01
MIDI_CLOCK_UNITS = 480  # ticks per quarter
MIDI_CLOCK_RATE = 500000  # microseconds per quarter (120 BPM)
TOTAL_MATCH_FILES = 22  # number of performances

# endregion


# region Fixtures


@pytest.fixture(autouse=True)
def reset_ids():
    """Reset all ID generators before each test for isolation."""
    _reset_group_ids()
    _reset_anchor_ids()
    _reset_claim_ids()
    _reset_bundle_ids()


@pytest.fixture
def p01_loader() -> MatchfileLoader:
    """MatchfileLoader with p01 loaded."""
    loader = MatchfileLoader()
    loader.load(P01_MATCH)
    return loader


@pytest.fixture
def all_loader() -> MatchfileLoader:
    """MatchfileLoader with all 22 files loaded."""
    loader = MatchfileLoader()
    loader.load(*ALL_MATCH_FILES)
    return loader


# endregion


# region TestMatchfileFormat


class TestMatchfileFormat:
    """Unit tests for raw file parsing, independent of TTA domain objects."""

    def test_header_parsing(self):
        """Header fields are parsed correctly from p01."""
        header = MatchfileLoader._parse_header(P01_MATCH)
        assert header["midiClockUnits"] == MIDI_CLOCK_UNITS
        assert header["midiClockRate"] == MIDI_CLOCK_RATE
        assert header["piece"] == "Chopin_op10_no3"
        assert "scoreFileName" in header
        assert "midiFileName" in header

    def test_header_version(self):
        """Match file version is extracted."""
        header = MatchfileLoader._parse_header(P01_MATCH)
        assert header.get("matchFileVersion") == "1.0.0"

    def test_file_not_found_raises(self):
        """FileNotFoundError raised for nonexistent file."""
        loader = MatchfileLoader()
        with pytest.raises(FileNotFoundError):
            loader.load(VIENNA_DATA_DIR / "nonexistent.match")

    def test_wrong_extension_raises(self):
        """ValueError raised for non-.match file."""
        loader = MatchfileLoader()
        musicxml = VIENNA_DATA_DIR / "Chopin_op10_no3.musicxml"
        with pytest.raises(ValueError, match="Not a .match file"):
            loader.load(musicxml)

    def test_load_returns_self(self):
        """load() returns Self for method chaining."""
        loader = MatchfileLoader()
        result = loader.load(P01_MATCH)
        assert result is loader


# endregion


# region TestMatchfileLoaderSingle


class TestMatchfileLoaderSingle:
    """Tests for single-file loading (p01)."""

    def test_score_timeline_type(self, p01_loader: MatchfileLoader):
        """Score timeline is ContinuousLogicalTimeline."""
        score_tl = p01_loader.create_timeline("score")
        assert isinstance(score_tl, ContinuousLogicalTimeline)

    def test_score_timeline_unit(self, p01_loader: MatchfileLoader):
        """Score timeline uses TimeUnit.quarters by default."""
        score_tl = p01_loader.create_timeline("score")
        assert score_tl.unit == TimeUnit.quarters

    def test_score_timeline_uid(self, p01_loader: MatchfileLoader):
        """Score timeline uid is derived from piece name."""
        score_tl = p01_loader.create_timeline("score")
        assert score_tl.id == "score:Chopin_op10_no3"

    def test_score_timeline_note_count(self, p01_loader: MatchfileLoader):
        """Score timeline has exactly 454 events (snote subset)."""
        score_tl = p01_loader.create_timeline("score")
        assert len(score_tl) == SNOTE_COUNT

    def test_score_timeline_nonnegative_coordinates(self, p01_loader: MatchfileLoader):
        """All score event coordinates are >= 0 after normalisation."""
        score_tl = p01_loader.create_timeline("score")
        events = score_tl.events
        table = events.table
        # start is a struct<value, numerator, denominator>; flatten to get
        # the 'value' sub-column at index 0.
        starts = table.column("start").combine_chunks().flatten()[0].to_pylist()
        assert all(s >= 0.0 for s in starts), (
            f"Found negative start coordinates after normalisation: "
            f"{[s for s in starts if s < 0.0]}"
        )

    def test_anacrusis_offset(self, p01_loader: MatchfileLoader):
        """Anacrusis offset is 0.5 (the negation of min raw onset -0.5)."""
        assert p01_loader.anacrusis_offset == 0.5

    def test_score_cmap_shift(self, p01_loader: MatchfileLoader):
        """raw_to_normalised ShiftMap is attached to score timeline."""
        score_tl = p01_loader.create_timeline("score")
        shift_map = score_tl._conversion_maps.get("raw_to_normalised")
        assert shift_map is not None
        assert isinstance(shift_map, ShiftMap)
        assert shift_map.offset == 0.5

    def test_score_cmap_divs(self, p01_loader: MatchfileLoader):
        """quarters_to_divs ScalarMap is attached, maps 1.0 -> 480."""
        score_tl = p01_loader.create_timeline("score")
        divs_map = score_tl._conversion_maps.get("quarters_to_divs")
        assert divs_map is not None
        assert isinstance(divs_map, ScalarMap)
        assert divs_map(1.0) == MIDI_CLOCK_UNITS

    def test_perf_timeline_type(self, p01_loader: MatchfileLoader):
        """Performance timeline is DiscreteLogicalTimeline."""
        perf_tl = p01_loader.create_timeline("perf:1")
        assert isinstance(perf_tl, DiscreteLogicalTimeline)

    def test_perf_timeline_unit(self, p01_loader: MatchfileLoader):
        """Performance timeline uses TimeUnit.ticks."""
        perf_tl = p01_loader.create_timeline("perf:1")
        assert perf_tl.unit == TimeUnit.ticks

    def test_perf_timeline_uid(self, p01_loader: MatchfileLoader):
        """Performance timeline uid is derived from MIDI filename."""
        perf_tl = p01_loader.create_timeline("perf:1")
        assert perf_tl.id == "perf:Chopin_op10_no3_p01"

    def test_perf_timeline_note_count(self, p01_loader: MatchfileLoader):
        """Performance timeline has exactly 451 events (454 - 3 deletions)."""
        perf_tl = p01_loader.create_timeline("perf:1")
        assert len(perf_tl) == P01_PERF_NOTE_COUNT

    def test_perf_cmap_seconds(self, p01_loader: MatchfileLoader):
        """ticks_to_seconds ScalarMap attached; 480 ticks = 0.5s at 120 BPM."""
        perf_tl = p01_loader.create_timeline("perf:1")
        secs_map = perf_tl.get_conversion_map(TimeUnit.seconds)
        assert secs_map is not None
        assert isinstance(secs_map, ScalarMap)
        # At 120 BPM: 480 ticks = 1 quarter = 0.5 seconds
        expected = MIDI_CLOCK_RATE / (MIDI_CLOCK_UNITS * 1_000_000) * 480
        assert abs(secs_map(480) - expected) < 1e-10

    def test_total_claims_count(self, p01_loader: MatchfileLoader):
        """Total MatchClaims = 454 (451 match + 3 NOMATCH)."""
        assert len(p01_loader._claims) == SNOTE_COUNT

    def test_synchronous_claims_count(self, p01_loader: MatchfileLoader):
        """451 synchronous (matched) claims."""
        sync_claims = [c for c in p01_loader._claims if c.is_synchronous]
        assert len(sync_claims) == P01_MATCH_COUNT

    def test_nomatch_claims_count(self, p01_loader: MatchfileLoader):
        """3 non-synchronous (deletion/NOMATCH) claims."""
        nomatch_claims = [c for c in p01_loader._claims if not c.is_synchronous]
        assert len(nomatch_claims) == P01_DELETION_COUNT

    def test_match_metadata_agent(self, p01_loader: MatchfileLoader):
        """All claims carry agent='vienna_match_v1.0.0'."""
        for claim in p01_loader._claims:
            assert claim.metadata is not None
            assert claim.metadata.agent == "vienna_match_v1.0.0"

    def test_match_metadata_criteria(self, p01_loader: MatchfileLoader):
        """All claims carry decision_criteria='automatic'."""
        for claim in p01_loader._claims:
            assert claim.metadata.decision_criteria == "automatic"

    def test_match_metadata_certainty(self, p01_loader: MatchfileLoader):
        """All claims carry certainty=1.0."""
        for claim in p01_loader._claims:
            assert claim.metadata.certainty == 1.0

    def test_synchronous_claims_have_anchors(self, p01_loader: MatchfileLoader):
        """Every synchronous claim has start_anchor and end_anchor."""
        sync_claims = [c for c in p01_loader._claims if c.is_synchronous]
        for claim in sync_claims:
            assert claim.start_anchor is not None
            assert claim.end_anchor is not None

    def test_nomatch_claims_have_no_anchors(self, p01_loader: MatchfileLoader):
        """Every NOMATCH claim has no anchors."""
        nomatch_claims = [c for c in p01_loader._claims if not c.is_synchronous]
        for claim in nomatch_claims:
            assert claim.start_anchor is None
            assert claim.end_anchor is None

    def test_claims_reference_correct_timelines(self, p01_loader: MatchfileLoader):
        """All claims connect score and p01 performance timelines."""
        score_id = "score:Chopin_op10_no3"
        perf_id = "perf:Chopin_op10_no3_p01"
        for claim in p01_loader._claims:
            assert claim.timeline_a_id == score_id
            assert claim.timeline_b_id == perf_id

    def test_no_rejected_files(self, p01_loader: MatchfileLoader):
        """Single file load should not reject any files."""
        assert len(p01_loader.rejected_files) == 0

    def test_sources_tracked(self, p01_loader: MatchfileLoader):
        """Sources list contains the loaded file."""
        assert len(p01_loader.sources) == 1
        assert p01_loader.sources[0] == P01_MATCH

    def test_loader_len(self, p01_loader: MatchfileLoader):
        """len(loader) returns number of performance timelines."""
        assert len(p01_loader) == 1

    def test_loader_repr(self, p01_loader: MatchfileLoader):
        """repr includes performance count and claim count."""
        r = repr(p01_loader)
        assert "performances=1" in r
        assert f"claims={SNOTE_COUNT}" in r


# endregion


# region TestMatchfileLoaderNormalization


class TestMatchfileLoaderNormalization:
    """Tests for anacrusis normalisation behaviour."""

    def test_no_normalisation_flag(self):
        """When normalize_anacrusis=False, no ShiftMap is attached."""
        loader = MatchfileLoader(normalize_anacrusis=False)
        loader.load(P01_MATCH)
        score_tl = loader.create_timeline("score")
        shift_map = score_tl._conversion_maps.get("raw_to_normalised")
        assert shift_map is None

    def test_normalisation_still_shifts_coordinates(self):
        """Even with normalize_anacrusis=False, coordinates are still
        non-negative (normalisation is always applied to stored coords;
        the flag controls only whether the ShiftMap is attached)."""
        loader = MatchfileLoader(normalize_anacrusis=False)
        loader.load(P01_MATCH)
        score_tl = loader.create_timeline("score")
        events = score_tl.events
        starts = events.table.column("start").combine_chunks().flatten()[0].to_pylist()
        assert all(s >= 0.0 for s in starts)

    def test_anacrusis_offset_computed_from_file(self):
        """Offset is computed dynamically, not hardcoded."""
        loader = MatchfileLoader()
        loader.load(P01_MATCH)
        # Offset should be 0.5 for this piece (min onset = -0.5)
        assert loader.anacrusis_offset == 0.5


# endregion


# region TestMatchfileLoaderCreateTimeline


class TestMatchfileLoaderCreateTimeline:
    """Tests for create_timeline() role-based lookup."""

    def test_score_role(self, p01_loader: MatchfileLoader):
        """'score' role returns score timeline."""
        tl = p01_loader.create_timeline("score")
        assert tl.id == "score:Chopin_op10_no3"

    def test_perf_numeric_role(self, p01_loader: MatchfileLoader):
        """'perf:1' returns first performance timeline."""
        tl = p01_loader.create_timeline("perf:1")
        assert tl.id == "perf:Chopin_op10_no3_p01"

    def test_perf_uid_lookup(self, p01_loader: MatchfileLoader):
        """Full uid lookup works."""
        tl = p01_loader.create_timeline("perf:Chopin_op10_no3_p01")
        assert tl.id == "perf:Chopin_op10_no3_p01"

    def test_score_uid_lookup(self, p01_loader: MatchfileLoader):
        """Score timeline accessible by full uid."""
        tl = p01_loader.create_timeline("score:Chopin_op10_no3")
        assert tl.id == "score:Chopin_op10_no3"

    def test_invalid_role_raises(self, p01_loader: MatchfileLoader):
        """KeyError raised for unknown role/uid."""
        with pytest.raises(KeyError):
            p01_loader.create_timeline("nonexistent")

    def test_no_load_raises(self):
        """RuntimeError raised if load() not called."""
        loader = MatchfileLoader()
        with pytest.raises(RuntimeError, match="No files loaded"):
            loader.create_timeline("score")


# endregion


# region TestMatchfileLoaderCreateBundle


class TestMatchfileLoaderCreateBundle:
    """Tests for create_alignment_bundle() — single-file."""

    def test_returns_alignment_bundle(self, p01_loader: MatchfileLoader):
        """Returns an AlignmentBundle."""
        bundle = p01_loader.create_alignment_bundle()
        assert isinstance(bundle, AlignmentBundle)

    def test_bundle_timeline_count(self, p01_loader: MatchfileLoader):
        """Bundle has 2 timelines (1 score + 1 performance)."""
        bundle = p01_loader.create_alignment_bundle()
        assert len(bundle.timelines) == 2

    def test_bundle_score_timeline(self, p01_loader: MatchfileLoader):
        """Score timeline is in the bundle under uid 'score'."""
        bundle = p01_loader.create_alignment_bundle()
        assert "score" in bundle.timelines

    def test_bundle_cross_group_claims(self, p01_loader: MatchfileLoader):
        """Bundle has 454 cross-group claims."""
        bundle = p01_loader.create_alignment_bundle()
        assert len(bundle.cross_group_claims) == SNOTE_COUNT

    def test_no_load_raises(self):
        """RuntimeError raised if load() not called."""
        loader = MatchfileLoader()
        with pytest.raises(RuntimeError, match="No files loaded"):
            loader.create_alignment_bundle()

    def test_bundle_score_in_group(self, p01_loader: MatchfileLoader):
        """Score timeline is in the 'score' group."""
        bundle = p01_loader.create_alignment_bundle()
        assert "score" in bundle.timeline_to_group
        assert bundle.timeline_to_group["score"] == "score"


# endregion


# region TestMatchfileLoaderCreateTimelines


class TestMatchfileLoaderCreateTimelines:
    """Tests for create_timelines() — all-at-once retrieval."""

    def test_returns_list(self, p01_loader: MatchfileLoader):
        """create_timelines() returns a list."""
        tls = p01_loader.create_timelines()
        assert isinstance(tls, list)

    def test_single_file_gives_two(self, p01_loader: MatchfileLoader):
        """Single file produces [score, perf] = 2 timelines."""
        tls = p01_loader.create_timelines()
        assert len(tls) == 2

    def test_score_is_first(self, p01_loader: MatchfileLoader):
        """Score timeline is always first."""
        tls = p01_loader.create_timelines()
        assert isinstance(tls[0], ContinuousLogicalTimeline)
        assert tls[0].id == "score:Chopin_op10_no3"

    def test_empty_before_load(self):
        """Empty list before load()."""
        loader = MatchfileLoader()
        assert loader.create_timelines() == []


# endregion


# region TestMatchfileLoaderMulti


class TestMatchfileLoaderMulti:
    """Tests for multi-file loading (all 22 performances)."""

    def test_22_performances_loaded(self, all_loader: MatchfileLoader):
        """All 22 performances produce distinct timelines."""
        assert len(all_loader) == TOTAL_MATCH_FILES

    def test_22_sources_tracked(self, all_loader: MatchfileLoader):
        """All 22 source files tracked."""
        assert len(all_loader.sources) == TOTAL_MATCH_FILES

    def test_no_rejected_files(self, all_loader: MatchfileLoader):
        """All 22 files are compatible (no rejections)."""
        assert len(all_loader.rejected_files) == 0

    def test_shared_score_timeline(self, all_loader: MatchfileLoader):
        """All 22 performances share the same score timeline object."""
        score_tl = all_loader.create_timeline("score")
        tls = all_loader.create_timelines()
        # First element is the score timeline
        assert tls[0] is score_tl

    def test_score_note_count_unchanged(self, all_loader: MatchfileLoader):
        """Score timeline still has 454 events after 22 loads."""
        score_tl = all_loader.create_timeline("score")
        assert len(score_tl) == SNOTE_COUNT

    def test_distinct_performance_uids(self, all_loader: MatchfileLoader):
        """22 performance timelines have distinct UIDs."""
        tls = all_loader.create_timelines()
        perf_tls = tls[1:]  # skip score
        uids = [tl.id for tl in perf_tls]
        assert len(set(uids)) == TOTAL_MATCH_FILES

    def test_total_claims_count(self, all_loader: MatchfileLoader):
        """Total claims = sum of per-file claims across 22 files."""
        # Each file produces snote_count claims (matched + deletions)
        total = len(all_loader._claims)
        # Must be exactly 22 * snote_count = 9,988
        assert total == TOTAL_MATCH_FILES * SNOTE_COUNT

    def test_all_claims_reference_same_score(self, all_loader: MatchfileLoader):
        """All claims reference the shared score timeline ID."""
        score_id = "score:Chopin_op10_no3"
        for claim in all_loader._claims:
            assert claim.timeline_a_id == score_id

    def test_create_timelines_gives_23(self, all_loader: MatchfileLoader):
        """create_timelines() returns 23 (1 score + 22 performances)."""
        tls = all_loader.create_timelines()
        assert len(tls) == 1 + TOTAL_MATCH_FILES

    def test_bundle_timeline_count(self, all_loader: MatchfileLoader):
        """Bundle has 23 timelines."""
        bundle = all_loader.create_alignment_bundle()
        assert len(bundle.timelines) == 1 + TOTAL_MATCH_FILES

    def test_bundle_cross_group_claims_count(self, all_loader: MatchfileLoader):
        """Bundle has 9,988 cross-group claims."""
        bundle = all_loader.create_alignment_bundle()
        assert len(bundle.cross_group_claims) == TOTAL_MATCH_FILES * SNOTE_COUNT

    def test_perf_numeric_lookup_all(self, all_loader: MatchfileLoader):
        """perf:1 through perf:22 all resolve correctly."""
        for i in range(1, TOTAL_MATCH_FILES + 1):
            tl = all_loader.create_timeline(f"perf:{i}")
            assert tl is not None
            assert isinstance(tl, DiscreteLogicalTimeline)

    def test_incremental_load(self):
        """Loading files incrementally produces same result as batch."""
        batch_loader = MatchfileLoader()
        batch_loader.load(*ALL_MATCH_FILES)

        incremental_loader = MatchfileLoader()
        for f in ALL_MATCH_FILES:
            incremental_loader.load(f)

        assert len(batch_loader) == len(incremental_loader)
        assert len(batch_loader._claims) == len(incremental_loader._claims)


# endregion


# region TestMatchfileLoaderExternalScore


class TestMatchfileLoaderExternalScore:
    """Tests for external score timeline binding via
    create_alignment_bundle(score_timeline=...)."""

    def test_external_score_used_in_bundle(self):
        """Bundle uses the externally supplied score timeline."""
        loader = MatchfileLoader()
        loader.load(P01_MATCH)

        # Create an external score TL with the same uid
        external_score = ContinuousLogicalTimeline(
            length=100.0,
            unit=TimeUnit.quarters,
            uid="score:Chopin_op10_no3",
        )

        bundle = loader.create_alignment_bundle(score_timeline=external_score)
        assert bundle.timelines["score"] is external_score

    def test_claims_still_reference_internal_uid(self):
        """MatchClaims are never rebound — they reference the internal
        score timeline's uid, which must match the external one."""
        loader = MatchfileLoader()
        loader.load(P01_MATCH)

        external_score = ContinuousLogicalTimeline(
            length=100.0,
            unit=TimeUnit.quarters,
            uid="score:Chopin_op10_no3",
        )

        bundle = loader.create_alignment_bundle(score_timeline=external_score)
        for claim in bundle.cross_group_claims:
            assert claim.timeline_a_id == "score:Chopin_op10_no3"


# endregion
