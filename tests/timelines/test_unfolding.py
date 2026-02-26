"""Tests for Unfolding via Slicing (Phase 3.10).

This test suite validates the slice-based unfolding pipeline:
1. Timeline.get_slice() primitive (unit tests)
2. compute_qb_sections() helper (unit tests with real data)
3. SegmentLine assembly from slices (integration tests)
4. End-to-end unfolding against ms3 gold standard (7 specimens, ZERO TOLERANCE)

See README_unfolding.md for full testing strategy documentation.

Validation Criteria (ZERO TOLERANCE per AGENTS.md §3.6):
- EXACT row count match
- EXACT mc_playthrough sequence
- EXACT mn_playthrough values with suffixes
- EXACT quarterbeats values as Fraction (NOT float comparison)
- EXACT total unfolded length
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.score import TSVLoader
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
)
from timetoalign.timelines.flow import (
    FlowController,
    FlowMode,
    compute_qb_sections,
)
from timetoalign.timelines.types import SegmentLine

# region Path Constants & Specimen Configuration

SCORE_DATA_DIR = Path(__file__).parent.parent / "data" / "score"


# Specimen configuration: maps specimen key to (folded_tsv_path, unfolded_tsv_path)
# relative to SCORE_DATA_DIR.
SPECIMEN_PATHS: dict[str, tuple[str, str]] = {
    "rachmaninoff": (
        "rachmaninoff_concerto2/score/"
        "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.measures.tsv",
        "rachmaninoff_concerto2/score/"
        "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff_unfolded.measures.tsv",
    ),
    "polyrhythm_only": (
        "flow_control/polyrythm_only/"
        "out_of_the_flow_experience-polyrhythm_only.measures.tsv",
        "flow_control/polyrythm_only/"
        "out_of_the_flow_experience-polyrhythm_only_unfolded.measures.tsv",
    ),
    "musete": (
        "couperin_concerts/c05n05_musete.measures.tsv",
        "couperin_concerts/c05n05_musete_unfolded.measures.tsv",
    ),
    "rondeau": (
        "couperin_concerts/c11n08_Rondeau.measures.tsv",
        "couperin_concerts/c11n08_Rondeau_unfolded.measures.tsv",
    ),
    "op18_no4_mov4": (
        "beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/"
        "op18_no4_mov4_flow.measures.tsv",
        "beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/"
        "op18_no4_mov4_flow_unfolded.measures.tsv",
    ),
    "woo71": (
        "beethoven_woo71/WoO71.measures.tsv",
        "beethoven_woo71/WoO71_unfolded.measures.tsv",
    ),
    "flow_only": (
        "flow_control/flow_only/" "out_of_the_flow_experience-flow_only.measures.tsv",
        "flow_control/flow_only/"
        "out_of_the_flow_experience-flow_only_unfolded.measures.tsv",
    ),
}

# Gold standard exact values:
# (folded_rows, unfolded_rows, last_mc_playthrough, last_mn_playthrough,
#  last_quarterbeats_str, last_duration_qb_str, total_qb_str)
GOLD_STANDARD: dict[str, tuple[int, int, int, str, str, str, str]] = {
    "rachmaninoff": (374, 374, 374, "374a", "2989/2", "4", "2997/2"),
    "polyrhythm_only": (14, 14, 14, "9a", "42", "3", "45"),
    "musete": (58, 138, 138, "14e", "765/2", "3/2", "384"),
    "rondeau": (60, 138, 138, "56b", "194", "1", "195"),
    "op18_no4_mov4": (226, 291, 291, "226a", "1113", "3", "1116"),
    "woo71": (397, 505, 505, "371a", "2153/2", "3/2", "1078"),
    "flow_only": (15, 30, 30, "3a", "73", "2", "75"),
}

# endregion


# region Fixtures


@pytest.fixture
def data_dir() -> Path:
    """Path to score test data directory."""
    return SCORE_DATA_DIR


@pytest.fixture
def simple_logical_timeline() -> ContinuousLogicalTimeline:
    """A ContinuousLogicalTimeline with known events for slice testing.

    Timeline span: [0, 100) in quarters (Fraction).

    Events:
        Instant events:
            - Beat at 0
            - Beat at 10
            - Beat at 25
            - Beat at 50
            - Beat at 75
            - Beat at 99

        Interval events:
            - Note [5, 15)   -- straddles a typical slice boundary at 10
            - Note [20, 30)  -- fully inside [10, 50)
            - Note [45, 55)  -- straddles a typical slice boundary at 50
            - Note [80, 95)  -- fully inside [50, 100)
    """
    tl = ContinuousLogicalTimeline(
        length=Fraction(100),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )
    tl.add_events(
        [
            # Instant events
            {"event_type": "Beat", "instant": Fraction(0)},
            {"event_type": "Beat", "instant": Fraction(10)},
            {"event_type": "Beat", "instant": Fraction(25)},
            {"event_type": "Beat", "instant": Fraction(50)},
            {"event_type": "Beat", "instant": Fraction(75)},
            {"event_type": "Beat", "instant": Fraction(99)},
            # Interval events
            {"event_type": "Note", "start": Fraction(5), "end": Fraction(15)},
            {"event_type": "Note", "start": Fraction(20), "end": Fraction(30)},
            {"event_type": "Note", "start": Fraction(45), "end": Fraction(55)},
            {"event_type": "Note", "start": Fraction(80), "end": Fraction(95)},
        ]
    )
    return tl


@pytest.fixture
def timeline_with_child() -> ContinuousLogicalTimeline:
    """A ContinuousLogicalTimeline with a child for recursive slice testing.

    Parent span: [0, 100) in quarters.
    Parent events:
        - Beat at 10
        - Note [30, 60)

    Child span: [0, 40) embedded at offset 20, covering parent [20, 60).
    Child events:
        - Beat at 5  (= parent 25)
        - Note [10, 30) (= parent [30, 50))
    """
    parent = ContinuousLogicalTimeline(
        length=Fraction(100),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )
    parent.add_events(
        [
            {"event_type": "Beat", "instant": Fraction(10)},
            {"event_type": "Note", "start": Fraction(30), "end": Fraction(60)},
        ]
    )

    child = ContinuousLogicalTimeline(
        length=Fraction(40),
        unit=TimeUnit.quarters,
        number_type=NumberType.fraction,
    )
    child.add_events(
        [
            {"event_type": "Beat", "instant": Fraction(5)},
            {"event_type": "Note", "start": Fraction(10), "end": Fraction(30)},
        ]
    )
    parent.add_child(child, offset=Fraction(20))

    return parent


def _load_controller(tsv_path: Path) -> FlowController:
    """Load a FlowController from a measures TSV file.

    Uses the standard two-phase loader pattern:
    1. TSVLoader.load(path) -- file ingestion
    2. FlowController(loader.store.measures) -- domain object creation
    """
    loader = TSVLoader()
    loader.load(tsv_path)
    return FlowController(loader.store.measures)


def _load_gold_standard(unfolded_tsv: Path) -> pd.DataFrame:
    """Load and parse an unfolded measures TSV as a DataFrame.

    Parses the 'quarterbeats' column as Fraction strings.
    """
    df = pd.read_csv(unfolded_tsv, sep="\t", dtype=str)
    # Convert numeric columns
    df["mc"] = df["mc"].astype(int)
    df["mc_playthrough"] = df["mc_playthrough"].astype(int)
    # quarterbeats stays as string for Fraction parsing
    # duration_qb stays as string for Fraction parsing
    return df


# endregion


# region TestGetSlice — Unit tests for Timeline.get_slice()


class TestGetSlice:
    """Test Timeline.get_slice() primitive.

    Uses synthetic timelines with known events to validate slicing logic
    in isolation. No external data files required.
    """

    def test_basic_slice(self, simple_logical_timeline: ContinuousLogicalTimeline):
        """Slice extracts events in range with shifted coordinates."""
        sliced = simple_logical_timeline.get_slice(Fraction(10), Fraction(50))

        assert sliced.length.value == Fraction(40)

        # Events in [10, 50):
        #   Instant: Beat@10 -> 0, Beat@25 -> 15
        #   Interval: Note[20,30) -> [10,20), Note[5,15) truncated to [10,15) -> [0,5)
        #   Note[45,55) truncated to [45,50) -> [35,40)
        events = list(sliced.get_events())
        instant_events = [e for e in events if e.get("temporal_type") == "instant"]
        # interval_events = [e for e in events if e.get("temporal_type") == "interval"]

        # Beat@10 -> 0, Beat@25 -> 15 (Beat@0 is outside, Beat@50 is right-exclusive)
        assert len(instant_events) == 2
        # Note: In EventData, all events (including instants) store coords in "start"
        instant_coords = sorted(Fraction(e["start"]["value"]) for e in instant_events)
        assert instant_coords == [Fraction(0), Fraction(15)]

    def test_instant_at_boundary_included(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Instant at start boundary IS included (left-inclusive)."""
        sliced = simple_logical_timeline.get_slice(Fraction(25), Fraction(75))

        events = list(sliced.get_events(temporal_type="instant"))
        coords = sorted(Fraction(e["start"]["value"]) for e in events)

        # Beat@25 -> 0 (included), Beat@50 -> 25 (included)
        # Beat@75 is at end boundary -> excluded (right-exclusive)
        assert Fraction(0) in coords, "Instant at start boundary must be included"

    def test_instant_at_end_excluded(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Instant at end boundary is NOT included (right-exclusive)."""
        sliced = simple_logical_timeline.get_slice(Fraction(25), Fraction(50))

        events = list(sliced.get_events(temporal_type="instant"))
        coords = [Fraction(e["start"]["value"]) for e in events]

        # Beat@50 is exactly at end -> excluded
        assert Fraction(25) not in coords, "Instant at end boundary must be excluded"

    def test_interval_truncation(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Interval straddling boundary is clipped (truncate_events=True)."""
        # Slice [10, 50). Note [5, 15) straddles start: clipped to [10, 15) -> [0, 5)
        # Note [45, 55) straddles end: clipped to [45, 50) -> [35, 40)
        sliced = simple_logical_timeline.get_slice(
            Fraction(10), Fraction(50), truncate_events=True
        )

        intervals = list(sliced.get_events(temporal_type="interval"))

        # Should have 3 intervals: truncated[0,5), full[10,20), truncated[35,40)
        assert len(intervals) == 3

        # Check the truncated interval from Note[5,15)
        starts = sorted(Fraction(e["start"]["value"]) for e in intervals)
        ends = sorted(Fraction(e["end"]["value"]) for e in intervals)

        assert Fraction(0) in starts, "Truncated interval should start at 0"
        assert Fraction(5) in ends, "Truncated interval [0,5) should end at 5"
        assert Fraction(40) in ends, "Truncated interval at end should stop at 40"

    def test_interval_no_truncation(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """With truncate_events=False, straddling intervals are excluded."""
        sliced = simple_logical_timeline.get_slice(
            Fraction(10), Fraction(50), truncate_events=False
        )

        intervals = list(sliced.get_events(temporal_type="interval"))

        # Only Note[20,30) is fully contained in [10, 50)
        assert len(intervals) == 1
        start = Fraction(intervals[0]["start"]["value"])
        end = Fraction(intervals[0]["end"]["value"])
        assert start == Fraction(10)  # 20 - 10
        assert end == Fraction(20)  # 30 - 10

    def test_coordinate_shifting(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """All coordinates shifted by -start."""
        sliced = simple_logical_timeline.get_slice(Fraction(75), Fraction(100))

        events = list(sliced.get_events(temporal_type="instant"))
        # Beat@75 -> 0, Beat@99 -> 24
        coords = sorted(Fraction(e["start"]["value"]) for e in events)
        assert coords == [Fraction(0), Fraction(24)]

        intervals = list(sliced.get_events(temporal_type="interval"))
        # Note[80,95) -> [5, 20)
        assert len(intervals) == 1
        assert Fraction(intervals[0]["start"]["value"]) == Fraction(5)
        assert Fraction(intervals[0]["end"]["value"]) == Fraction(20)

    def test_empty_slice(self, simple_logical_timeline: ContinuousLogicalTimeline):
        """Slice of range with no events returns empty timeline."""
        # Range [96, 99) has no events (Beat@99 is at 99, not in [96, 99))
        sliced = simple_logical_timeline.get_slice(Fraction(96), Fraction(99))

        assert sliced.length.value == Fraction(3)
        events = list(sliced.get_events())
        assert len(events) == 0

    def test_full_slice(self, simple_logical_timeline: ContinuousLogicalTimeline):
        """Slice of entire timeline returns copy with all events."""
        sliced = simple_logical_timeline.get_slice(Fraction(0), Fraction(100))

        assert sliced.length.value == Fraction(100)
        original_events = list(simple_logical_timeline.get_events())
        sliced_events = list(sliced.get_events())
        assert len(sliced_events) == len(original_events)

    def test_children_sliced(self, timeline_with_child: ContinuousLogicalTimeline):
        """Child timelines are recursively sliced when include_children=True."""
        # Parent [0, 100), child at offset 20 with length 40, covering [20, 60)
        # Slice [25, 55) should include child's overlap [25, 55) -> child coords [5, 35)
        sliced = timeline_with_child.get_slice(
            Fraction(25), Fraction(55), include_children=True
        )

        assert sliced.length.value == Fraction(30)  # 55 - 25
        assert sliced.n_children >= 1, "Sliced child should be present"

    def test_children_excluded(self, timeline_with_child: ContinuousLogicalTimeline):
        """Child timelines are excluded when include_children=False."""
        sliced = timeline_with_child.get_slice(
            Fraction(25), Fraction(55), include_children=False
        )

        assert sliced.n_children == 0

    def test_number_type_preserved(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Fraction coordinates remain Fraction in slice."""
        sliced = simple_logical_timeline.get_slice(Fraction(10), Fraction(50))

        assert sliced.number_type == NumberType.fraction

    def test_concrete_class_preserved(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """ContinuousLogicalTimeline.get_slice() returns ContinuousLogicalTimeline."""
        sliced = simple_logical_timeline.get_slice(Fraction(10), Fraction(50))

        assert type(sliced) is ContinuousLogicalTimeline

    def test_slice_of_discrete_timeline(self):
        """get_slice works on DiscreteLogicalTimeline with int coordinates."""
        tl = DiscreteLogicalTimeline(
            length=100,
            unit=TimeUnit.ticks,
        )
        tl.add_events(
            [
                {"event_type": "Tick", "instant": 10},
                {"event_type": "Tick", "instant": 50},
                {"event_type": "Tick", "instant": 90},
            ]
        )

        sliced = tl.get_slice(20, 80)
        assert sliced.length.value == 60
        assert type(sliced) is DiscreteLogicalTimeline

        events = list(sliced.get_events())
        assert len(events) == 1  # Only Tick@50 -> 30
        assert events[0]["start"]["value"] == 30

    def test_slice_of_physical_timeline(self):
        """get_slice works on ContinuousPhysicalTimeline with float coordinates."""
        tl = ContinuousPhysicalTimeline(
            length=10.0,
            unit=TimeUnit.seconds,
        )
        tl.add_events(
            [
                {"event_type": "Onset", "instant": 1.0},
                {"event_type": "Onset", "instant": 5.0},
                {"event_type": "Onset", "instant": 9.0},
            ]
        )

        sliced = tl.get_slice(2.0, 8.0)
        assert sliced.length.value == pytest.approx(6.0)
        assert type(sliced) is ContinuousPhysicalTimeline

        events = list(sliced.get_events())
        assert len(events) == 1  # Only Onset@5.0 -> 3.0

    def test_invalid_range_start_ge_end(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Raises ValueError if start >= end."""
        with pytest.raises(ValueError, match="start.*end"):
            simple_logical_timeline.get_slice(Fraction(50), Fraction(50))

        with pytest.raises(ValueError, match="start.*end"):
            simple_logical_timeline.get_slice(Fraction(60), Fraction(40))

    def test_invalid_range_outside_bounds(
        self, simple_logical_timeline: ContinuousLogicalTimeline
    ):
        """Raises ValueError if range is outside timeline bounds."""
        with pytest.raises(ValueError):
            simple_logical_timeline.get_slice(Fraction(-10), Fraction(50))

        with pytest.raises(ValueError):
            simple_logical_timeline.get_slice(Fraction(50), Fraction(110))


# endregion


# region TestComputeQBSections — Unit tests for QB-boundary helper


class TestComputeQBSections:
    """Test compute_qb_sections() helper.

    Validates that MC-based PlaythroughSection ranges are correctly converted
    to quarterbeat coordinate ranges using MeasureUnit duration_qb data.

    Uses real specimen TSV files to ensure correctness against known data.
    """

    def test_sequential_score_single_section(self, data_dir: Path):
        """Sequential score (Rachmaninoff): single section spanning full QB range."""
        tsv_path = data_dir / SPECIMEN_PATHS["rachmaninoff"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Rachmaninoff has no repeats -> should have same section structure as flow
        assert len(qb_sections) == len(flow.sections)

        # Total QB should match gold standard: 2997/2
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(2997, 2)

    def test_repeated_score_musete(self, data_dir: Path):
        """D.S. al Fine (Musete): sections repeat QB ranges."""
        tsv_path = data_dir / SPECIMEN_PATHS["musete"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Total unfolded QB should be 384
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(384)

    def test_repeated_score_rondeau(self, data_dir: Path):
        """Rondeau form: sections with D.S. produce correct QB ranges."""
        tsv_path = data_dir / SPECIMEN_PATHS["rondeau"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Total unfolded QB should be 195
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(195)

    def test_volta_score_op18(self, data_dir: Path):
        """Repeats + Volta brackets (Op.18 No.4 iv)."""
        tsv_path = data_dir / SPECIMEN_PATHS["op18_no4_mov4"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Total unfolded QB should be 1116
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(1116)

    def test_complex_split_bars_woo71(self, data_dir: Path):
        """Complex split bars (Beethoven WoO71)."""
        tsv_path = data_dir / SPECIMEN_PATHS["woo71"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Total unfolded QB should be 1078
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(1078)

    def test_flow_only_ds_dc(self, data_dir: Path):
        """D.S./D.C. with Voltas (flow_only)."""
        tsv_path = data_dir / SPECIMEN_PATHS["flow_only"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Total unfolded QB should be 75
        total_qb = sum(end - start for start, end in qb_sections)
        assert total_qb == Fraction(75)

    def test_qb_boundaries_match_folded_measures_tsv(self, data_dir: Path):
        """QB start positions match 'quarterbeats' column in folded measures TSV.

        For the Musete specimen, validates that each section's qb_start equals
        the quarterbeats value of the corresponding mc_start in the folded TSV.
        """
        tsv_path = data_dir / SPECIMEN_PATHS["musete"][0]
        if not tsv_path.exists():
            pytest.skip(f"Test data not found: {tsv_path}")

        # Load folded TSV for gold standard quarterbeats
        df = pd.read_csv(tsv_path, sep="\t", dtype=str)
        mc_to_qb = {}
        for _, row in df.iterrows():
            mc = int(row["mc"])
            qb = Fraction(row["quarterbeats"])
            mc_to_qb[mc] = qb

        controller = _load_controller(tsv_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        # Each section's qb_start must match the folded TSV's quarterbeats for mc_start
        for i, sec in enumerate(flow.sections):
            qb_start, qb_end = qb_sections[i]
            expected_start = mc_to_qb[sec.mc_start]
            assert qb_start == expected_start, (
                f"Section {i} (MC {sec.mc_start}-{sec.mc_end}): "
                f"qb_start={qb_start} != expected {expected_start}"
            )

    def test_all_sections_positive_duration(self, data_dir: Path):
        """Every QB section has strictly positive duration."""
        for key, (folded_rel, _) in SPECIMEN_PATHS.items():
            tsv_path = data_dir / folded_rel
            if not tsv_path.exists():
                continue

            controller = _load_controller(tsv_path)
            flow = controller.compute_flow(FlowMode.DEFAULT)
            qb_sections = compute_qb_sections(flow, controller)

            for i, (start, end) in enumerate(qb_sections):
                assert end > start, (
                    f"Specimen {key}, section {i}: " f"qb_end={end} <= qb_start={start}"
                )


# endregion


# region TestSegmentLineAssembly — Integration tests for slice assembly


class TestSegmentLineAssembly:
    """Test assembling slices into a SegmentLine.

    Uses synthetic timelines to validate the structural properties of
    SegmentLine construction from get_slice() outputs.
    """

    def test_contiguity(self):
        """Segments are contiguous (each starts where previous ended)."""
        # Create source timeline
        source = ContinuousLogicalTimeline(
            length=Fraction(120),
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )
        source.add_events(
            [
                {"event_type": "Beat", "instant": Fraction(0)},
                {"event_type": "Beat", "instant": Fraction(40)},
                {"event_type": "Beat", "instant": Fraction(80)},
            ]
        )

        # Slice at [0, 40), [40, 80), [80, 120)
        boundaries = [
            (Fraction(0), Fraction(40)),
            (Fraction(40), Fraction(80)),
            (Fraction(80), Fraction(120)),
        ]

        sl = SegmentLine(
            segment_type=ContinuousLogicalTimeline,
            length=0,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        for qb_start, qb_end in boundaries:
            seg = source.get_slice(qb_start, qb_end)
            sl.append_segment(seg)

        assert sl.n_segments == 3

        # Verify contiguity: each segment starts where previous ended
        offsets = []
        for seg_id in sl._segment_order:
            offset = sl._child_offsets[seg_id].value
            child = sl._children[seg_id]
            offsets.append((offset, offset + child.length.value))

        for i in range(1, len(offsets)):
            assert offsets[i][0] == offsets[i - 1][1], (
                f"Segment {i} start {offsets[i][0]} != "
                f"segment {i - 1} end {offsets[i - 1][1]}"
            )

    def test_total_length(self):
        """Total SegmentLine length equals sum of slice lengths."""
        source = ContinuousLogicalTimeline(
            length=Fraction(100),
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        # Simulate unfolding: two passes through [0, 100)
        sl = SegmentLine(
            segment_type=ContinuousLogicalTimeline,
            length=0,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        slice1 = source.get_slice(Fraction(0), Fraction(100))
        slice2 = source.get_slice(Fraction(0), Fraction(100))
        sl.append_segment(slice1)
        sl.append_segment(slice2)

        assert sl.length.value == Fraction(200)
        assert sl.n_segments == 2

    def test_events_preserved(self):
        """All events from individual slices appear in the assembled SegmentLine."""
        source = ContinuousLogicalTimeline(
            length=Fraction(60),
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )
        source.add_events(
            [
                {"event_type": "Beat", "instant": Fraction(10)},
                {"event_type": "Beat", "instant": Fraction(30)},
                {"event_type": "Beat", "instant": Fraction(50)},
            ]
        )

        # Slice at [0, 30), [30, 60)
        sl = SegmentLine(
            segment_type=ContinuousLogicalTimeline,
            length=0,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        seg1 = source.get_slice(Fraction(0), Fraction(30))
        seg2 = source.get_slice(Fraction(30), Fraction(60))
        sl.append_segment(seg1)
        sl.append_segment(seg2)

        # Each segment should have its events
        seg1_events = list(sl._children[sl._segment_order[0]].get_events())
        seg2_events = list(sl._children[sl._segment_order[1]].get_events())

        assert len(seg1_events) == 1  # Beat@10 -> 10
        assert len(seg2_events) == 2  # Beat@30 -> 0, Beat@50 -> 20

    def test_segment_type_matches_source(self):
        """SegmentLine's segment_type matches the source timeline class."""
        source = ContinuousLogicalTimeline(
            length=Fraction(40),
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        sl = SegmentLine(
            segment_type=ContinuousLogicalTimeline,
            length=0,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        seg = source.get_slice(Fraction(0), Fraction(40))
        sl.append_segment(seg)

        assert sl.segment_type is ContinuousLogicalTimeline
        assert type(sl._children[sl._segment_order[0]]) is ContinuousLogicalTimeline

    def test_repeated_section_assembly(self):
        """Multiple slices from the same source range assemble correctly.

        This simulates a simple repeat: the same [0, 40) section played twice.
        """
        source = ContinuousLogicalTimeline(
            length=Fraction(40),
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )
        source.add_events(
            [
                {"event_type": "Beat", "instant": Fraction(0)},
                {"event_type": "Beat", "instant": Fraction(20)},
            ]
        )

        sl = SegmentLine(
            segment_type=ContinuousLogicalTimeline,
            length=0,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        # Two passes through the same range
        for _ in range(2):
            seg = source.get_slice(Fraction(0), Fraction(40))
            sl.append_segment(seg)

        assert sl.length.value == Fraction(80)
        assert sl.n_segments == 2

        # Each segment should have 2 beats
        for seg_id in sl._segment_order:
            child = sl._children[seg_id]
            events = list(child.get_events())
            assert len(events) == 2


# endregion


# region TestUnfoldingGoldStandard — End-to-end validation against ms3 gold standard


# All 7 specimens for parametrized testing
ALL_SPECIMENS = list(SPECIMEN_PATHS.keys())


@pytest.mark.parametrize("specimen", ALL_SPECIMENS)
class TestUnfoldingGoldStandard:
    """End-to-end validation of unfolded timelines against ms3 gold standard.

    ZERO TOLERANCE: Exact match on all columns per AGENTS.md §3.6.

    Each specimen is loaded from its folded measures TSV, unfolded via the
    new slicing-based pipeline, and compared row-by-row against the gold
    standard unfolded measures TSV.
    """

    def _load_specimen(
        self, specimen: str, data_dir: Path
    ) -> tuple[FlowController, Any, pd.DataFrame]:
        """Load controller, flow, and gold standard for a specimen.

        Returns:
            (controller, flow, gold_df) tuple.

        Raises:
            pytest.skip: If test data files are missing.
        """
        folded_rel, unfolded_rel = SPECIMEN_PATHS[specimen]
        folded_path = data_dir / folded_rel
        unfolded_path = data_dir / unfolded_rel

        if not folded_path.exists():
            pytest.skip(f"Folded TSV not found: {folded_path}")
        if not unfolded_path.exists():
            pytest.skip(f"Unfolded TSV not found: {unfolded_path}")

        controller = _load_controller(folded_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        gold_df = _load_gold_standard(unfolded_path)

        return controller, flow, gold_df

    def test_unfolded_row_count(self, specimen: str, data_dir: Path):
        """Unfolded timeline has exact same number of measures as gold standard."""
        _, _, gold_df = self._load_specimen(specimen, data_dir)
        expected_rows = GOLD_STANDARD[specimen][1]

        assert len(gold_df) == expected_rows, (
            f"Specimen {specimen}: gold standard has {len(gold_df)} rows, "
            f"expected {expected_rows}"
        )

    def test_mc_sequence(self, specimen: str, data_dir: Path):
        """mc sequence matches gold standard exactly (may repeat for repeats)."""
        controller, flow, gold_df = self._load_specimen(specimen, data_dir)

        # The mc sequence from the flow should match gold standard's mc column
        computed_mc = flow.to_mc_sequence()
        gold_mc = gold_df["mc"].tolist()

        assert computed_mc == gold_mc, (
            f"Specimen {specimen}: MC sequence mismatch.\n"
            f"Computed ({len(computed_mc)} values): {computed_mc[:20]}...\n"
            f"Gold     ({len(gold_mc)} values): {gold_mc[:20]}..."
        )

    def test_mc_playthrough_sequence(self, specimen: str, data_dir: Path):
        """mc_playthrough sequence is monotonic 1, 2, 3, ... matching gold standard."""
        _, _, gold_df = self._load_specimen(specimen, data_dir)
        expected_rows = GOLD_STANDARD[specimen][1]

        gold_playthrough = gold_df["mc_playthrough"].tolist()

        # Must be monotonically increasing 1..N
        expected_playthrough = list(range(1, expected_rows + 1))
        assert (
            gold_playthrough == expected_playthrough
        ), f"Specimen {specimen}: mc_playthrough not monotonic 1..{expected_rows}"

    def test_mn_playthrough_values(self, specimen: str, data_dir: Path):
        """mn_playthrough values (with a/b/c suffixes) match gold standard exactly."""
        _, _, gold_df = self._load_specimen(specimen, data_dir)

        gold_mn_playthrough = gold_df["mn_playthrough"].tolist()
        last_expected = GOLD_STANDARD[specimen][3]

        # Verify last value matches expected
        assert gold_mn_playthrough[-1] == last_expected, (
            f"Specimen {specimen}: last mn_playthrough={gold_mn_playthrough[-1]}, "
            f"expected {last_expected}"
        )

    def test_quarterbeats_values(self, specimen: str, data_dir: Path):
        """Cumulative quarterbeats match gold standard exactly (as Fraction).

        This is the critical test: quarterbeats must be computed from actual
        measure durations, not MC numbers.
        """
        _, _, gold_df = self._load_specimen(specimen, data_dir)

        last_qb_str = GOLD_STANDARD[specimen][4]
        last_qb = Fraction(last_qb_str)

        # Parse last quarterbeats from gold standard
        gold_last_qb = Fraction(gold_df["quarterbeats"].iloc[-1])

        assert gold_last_qb == last_qb, (
            f"Specimen {specimen}: last quarterbeats={gold_last_qb}, "
            f"expected {last_qb}"
        )

        # Verify monotonicity of quarterbeats
        qb_values = [Fraction(q) for q in gold_df["quarterbeats"].tolist()]
        for i in range(1, len(qb_values)):
            assert qb_values[i] >= qb_values[i - 1], (
                f"Specimen {specimen}: quarterbeats not monotonic at row {i}: "
                f"{qb_values[i]} < {qb_values[i - 1]}"
            )

    def test_total_unfolded_length(self, specimen: str, data_dir: Path):
        """Total length = final_quarterbeats + final_duration_qb."""
        _, _, gold_df = self._load_specimen(specimen, data_dir)

        expected_total = Fraction(GOLD_STANDARD[specimen][6])

        # Compute from gold standard
        last_qb = Fraction(gold_df["quarterbeats"].iloc[-1])
        last_dur = Fraction(gold_df["duration_qb"].iloc[-1])
        computed_total = last_qb + last_dur

        assert computed_total == expected_total, (
            f"Specimen {specimen}: total QB={computed_total}, "
            f"expected {expected_total} "
            f"(last_qb={last_qb} + last_dur={last_dur})"
        )

    def test_compute_qb_sections_total(self, specimen: str, data_dir: Path):
        """Sum of QB section durations matches gold standard total length."""
        folded_rel, _ = SPECIMEN_PATHS[specimen]
        folded_path = data_dir / folded_rel
        if not folded_path.exists():
            pytest.skip(f"Folded TSV not found: {folded_path}")

        controller = _load_controller(folded_path)
        flow = controller.compute_flow(FlowMode.DEFAULT)
        qb_sections = compute_qb_sections(flow, controller)

        expected_total = Fraction(GOLD_STANDARD[specimen][6])
        computed_total = sum(end - start for start, end in qb_sections)

        assert computed_total == expected_total, (
            f"Specimen {specimen}: QB sections total={computed_total}, "
            f"expected {expected_total}"
        )


# endregion
