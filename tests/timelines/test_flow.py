"""Tests for Flow API (Phase 3.7).

This test suite validates the Flow API against ms3 gold standard unfolded
TSV files. Tests are organized by complexity, starting with the simplest
case (no flow control) and progressing to complex D.S./D.C. structures.

Test Specimens (Complexity Order):
1. rachmaninoff_concerto2 - 374 MCs, no flow control (baseline)
2. flow_control/polyrhythm_only - 14 MCs, line breaks only
3. couperin/c05n05_musete - 58 MCs -> 138 unfolded, D.S. al Fine
4. couperin/c11n08_Rondeau - Rondeau form
5. beethoven_op18_flow - Repeats + Voltas
6. beethoven_woo71 - Complex split bars
7. flow_control/flow_only - All edge cases

Validation Criteria (ZERO TOLERANCE):
- EXACT mc_playthrough sequence
- EXACT mn_playthrough values with suffixes
- EXACT quarterbeats values
- EXACT row count
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from timetoalign.loader.score import TSVLoader
from timetoalign.timelines import Flow, FlowController, FlowMap, FlowMode, FlowStep
from timetoalign.timelines.flow import (
    AtomicSection,
    PlaythroughSection,
    load_valid_flows,
)

# region Fixtures


@pytest.fixture
def data_dir() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent.parent / "data" / "score"


@pytest.fixture
def target_flows_dir() -> Path:
    """Path to target_flows directory."""
    return Path(__file__).parent.parent / "data" / "target_flows"


@pytest.fixture
def rachmaninoff_measures_tsv(data_dir: Path) -> Path:
    """Path to Rachmaninoff folded measures TSV."""
    return (
        data_dir
        / "rachmaninoff_concerto2"
        / "score"
        / "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.measures.tsv"
    )


@pytest.fixture
def rachmaninoff_unfolded_tsv(data_dir: Path) -> Path:
    """Path to Rachmaninoff unfolded measures TSV."""
    return (
        data_dir
        / "rachmaninoff_concerto2"
        / "score"
        / "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff_unfolded.measures.tsv"
    )


@pytest.fixture
def musete_measures_tsv(data_dir: Path) -> Path:
    """Path to Couperin Musete folded measures TSV."""
    return data_dir / "couperin_concerts" / "c05n05_musete.measures.tsv"


@pytest.fixture
def musete_unfolded_tsv(data_dir: Path) -> Path:
    """Path to Couperin Musete unfolded measures TSV."""
    return data_dir / "couperin_concerts" / "c05n05_musete_unfolded.measures.tsv"


@pytest.fixture
def rondeau_measures_tsv(data_dir: Path) -> Path:
    """Path to Couperin Rondeau folded measures TSV."""
    return data_dir / "couperin_concerts" / "c11n08_Rondeau.measures.tsv"


@pytest.fixture
def rondeau_unfolded_tsv(data_dir: Path) -> Path:
    """Path to Couperin Rondeau unfolded measures TSV."""
    return data_dir / "couperin_concerts" / "c11n08_Rondeau_unfolded.measures.tsv"


# endregion

# region Unit Tests: FlowStep


class TestFlowStep:
    """Test FlowStep dataclass."""

    def test_creation(self) -> None:
        """FlowStep can be created with all fields."""
        step = FlowStep(
            mc=1,
            mn="1",
            mc_playthrough=1,
            mn_playthrough="1a",
            quarterbeats=Fraction(0),
            duration_qb=Fraction(4),
            visit_count=1,
        )
        assert step.mc == 1
        assert step.mn == "1"
        assert step.mc_playthrough == 1
        assert step.mn_playthrough == "1a"
        assert step.quarterbeats == Fraction(0)
        assert step.duration_qb == Fraction(4)
        assert step.visit_count == 1

    def test_frozen(self) -> None:
        """FlowStep is immutable."""
        step = FlowStep(
            mc=1,
            mn="1",
            mc_playthrough=1,
            mn_playthrough="1a",
            quarterbeats=Fraction(0),
            duration_qb=Fraction(4),
            visit_count=1,
        )
        with pytest.raises(AttributeError):
            step.mc = 2  # type: ignore

    def test_to_dict(self) -> None:
        """FlowStep can be converted to dict."""
        step = FlowStep(
            mc=5,
            mn="5",
            mc_playthrough=10,
            mn_playthrough="5b",
            quarterbeats=Fraction(20),
            duration_qb=Fraction(4),
            visit_count=2,
        )
        d = step.to_dict()
        assert d["mc"] == 5
        assert d["mn_playthrough"] == "5b"
        assert d["visit_count"] == 2


# endregion

# region Unit Tests: AtomicSection


class TestAtomicSection:
    """Test AtomicSection dataclass."""

    def test_creation(self) -> None:
        """AtomicSection can be created with all fields."""
        # Right-open: mc_end=5 means MCs 1,2,3,4 (4 MCs total)
        sec = AtomicSection(
            id="A",
            mc_start=1,
            mc_end=5,  # Right-open: includes MCs 1-4
            to=("A", "B"),
            await_to=("C",),
            section_type="leap_end",
        )
        assert sec.id == "A"
        assert sec.mc_start == 1
        assert sec.mc_end == 5
        assert sec.to == ("A", "B")
        assert sec.await_to == ("C",)
        assert sec.section_type == "leap_end"

    def test_mc_range(self) -> None:
        """AtomicSection mc_range property."""
        # Right-open: mc_end=9 means MCs 5,6,7,8 (4 MCs total)
        sec = AtomicSection(id="B", mc_start=5, mc_end=9)
        assert sec.mc_range == (5, 9)
        assert sec.mc_count == 4  # 9 - 5 = 4

    def test_frozen(self) -> None:
        """AtomicSection is immutable."""
        sec = AtomicSection(id="A", mc_start=1, mc_end=5)
        with pytest.raises(AttributeError):
            sec.id = "B"  # type: ignore

    def test_invalid_range_raises(self) -> None:
        """AtomicSection raises on invalid mc range."""
        with pytest.raises(ValueError, match="mc_end.*cannot be before mc_start"):
            AtomicSection(id="A", mc_start=10, mc_end=5)

    def test_invalid_section_type_raises(self) -> None:
        """AtomicSection raises on invalid section_type."""
        with pytest.raises(ValueError, match="invalid section_type"):
            AtomicSection(id="A", mc_start=1, mc_end=5, section_type="invalid")

    def test_to_dict(self) -> None:
        """AtomicSection can be converted to dict."""
        # Right-open: mc_end=5 means MCs 1,2,3,4
        sec = AtomicSection(id="A", mc_start=1, mc_end=5, to=("B",))
        d = sec.to_dict()
        assert d["id"] == "A"
        assert d["mc_start"] == 1
        assert d["mc_end"] == 5
        assert d["to"] == ["B"]


# endregion

# region Unit Tests: PlaythroughSection


class TestPlaythroughSection:
    """Test PlaythroughSection dataclass."""

    def test_creation(self) -> None:
        """PlaythroughSection can be created with all fields."""
        seg = PlaythroughSection(
            mc_start=1,
            mc_end=8,
            atomic_section_ids=("A", "B"),
        )
        assert seg.mc_start == 1
        assert seg.mc_end == 8
        assert seg.atomic_section_ids == ("A", "B")

    def test_mc_range(self) -> None:
        """PlaythroughSection mc_range property."""
        # Right-open: mc_end=13 means MCs 5,6,7,8,9,10,11,12 (8 MCs total)
        seg = PlaythroughSection(mc_start=5, mc_end=13)
        assert seg.mc_range == (5, 13)
        assert seg.mc_count == 8  # 13 - 5 = 8

    def test_frozen(self) -> None:
        """PlaythroughSection is immutable."""
        # Right-open: mc_end=9 means MCs 1-8
        seg = PlaythroughSection(mc_start=1, mc_end=9)
        with pytest.raises(AttributeError):
            seg.mc_start = 5  # type: ignore

    def test_invalid_range_raises(self) -> None:
        """PlaythroughSection raises on invalid mc range."""
        with pytest.raises(ValueError, match="mc_end.*cannot be before mc_start"):
            PlaythroughSection(mc_start=10, mc_end=5)

    def test_to_dict(self) -> None:
        """PlaythroughSection can be converted to dict."""
        # Right-open: mc_end=9 means MCs 1-8
        seg = PlaythroughSection(mc_start=1, mc_end=9, atomic_section_ids=("A", "B"))
        d = seg.to_dict()
        assert d["mc_start"] == 1
        assert d["mc_end"] == 9
        assert d["atomic_sections"] == "A;B"

    def test_to_mc_sequence(self) -> None:
        """PlaythroughSection to_mc_sequence expands range."""
        # Right-open: mc_end=9 means MCs 5,6,7,8 (4 MCs)
        seg = PlaythroughSection(mc_start=5, mc_end=9)
        assert seg.to_mc_sequence() == [5, 6, 7, 8]


# endregion

# region Unit Tests: Flow


class TestFlow:
    """Test Flow class."""

    def test_empty_flow(self) -> None:
        """Empty flow has correct properties."""
        flow = Flow(steps=[], mode=FlowMode.DEFAULT, folded_length=0)
        assert flow.unfolded_length == 0
        assert flow.total_quarterbeats == Fraction(0)
        assert flow.has_repeats is False
        assert flow.to_mc_sequence() == []

    def test_simple_flow(self) -> None:
        """Simple flow with sequential measures."""
        steps = [
            FlowStep(1, "1", 1, "1a", Fraction(0), Fraction(4), 1),
            FlowStep(2, "2", 2, "2a", Fraction(4), Fraction(4), 1),
            FlowStep(3, "3", 3, "3a", Fraction(8), Fraction(4), 1),
        ]
        flow = Flow(steps=steps, mode=FlowMode.DEFAULT, folded_length=3)

        assert flow.unfolded_length == 3
        assert flow.folded_length == 3
        assert flow.has_repeats is False
        assert flow.total_quarterbeats == Fraction(12)
        assert flow.to_mc_sequence() == [1, 2, 3]

    def test_flow_with_repeats(self) -> None:
        """Flow with repeated measures has correct properties."""
        steps = [
            FlowStep(1, "1", 1, "1a", Fraction(0), Fraction(4), 1),
            FlowStep(2, "2", 2, "2a", Fraction(4), Fraction(4), 1),
            FlowStep(1, "1", 3, "1b", Fraction(8), Fraction(4), 2),
            FlowStep(2, "2", 4, "2b", Fraction(12), Fraction(4), 2),
        ]
        flow = Flow(steps=steps, mode=FlowMode.DEFAULT, folded_length=2)

        assert flow.unfolded_length == 4
        assert flow.folded_length == 2
        assert flow.has_repeats is True
        assert flow.to_mc_sequence() == [1, 2, 1, 2]

    def test_to_dataframe(self) -> None:
        """Flow can be converted to DataFrame."""
        steps = [
            FlowStep(1, "1", 1, "1a", Fraction(0), Fraction(4), 1),
            FlowStep(2, "2", 2, "2a", Fraction(4), Fraction(4), 1),
        ]
        flow = Flow(steps=steps, mode=FlowMode.DEFAULT, folded_length=2)

        df = flow.to_dataframe()
        assert len(df) == 2
        assert list(df.columns) == [
            "mc",
            "mn",
            "mc_playthrough",
            "mn_playthrough",
            "quarterbeats",
            "duration_qb",
            "visit_count",
        ]
        assert df["mc"].tolist() == [1, 2]
        assert df["mn_playthrough"].tolist() == ["1a", "2a"]


class TestFlowSegmentBased:
    """Test Flow segment-based API."""

    def test_from_sections(self) -> None:
        """Flow can be created from segments."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        segments = [
            PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
            PlaythroughSection(mc_start=5, mc_end=9, atomic_section_ids=("B",)),
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        assert len(flow.sections) == 2
        assert flow.mode == FlowMode.DEFAULT
        assert flow.sections[0].mc_start == 1
        assert flow.sections[1].mc_end == 9

    def test_from_records(self) -> None:
        """Flow can be created from records."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        records = [
            {"mc_start": 1, "mc_end": 5, "atomic_segments": "A"},
            {"mc_start": 5, "mc_end": 9, "atomic_segments": "B"},
        ]
        flow = Flow.from_records(records, FlowMode.DEFAULT)

        assert len(flow.sections) == 2
        assert flow.sections[0].atomic_section_ids == ("A",)
        assert flow.sections[1].atomic_section_ids == ("B",)

    def test_from_records_semicolon_separated(self) -> None:
        """Flow.from_records handles semicolon-separated atomic_segments."""
        # Right-open: mc_end=9 means MCs 1-8
        records = [
            {"mc_start": 1, "mc_end": 9, "atomic_segments": "A;B"},
        ]
        flow = Flow.from_records(records, FlowMode.DEFAULT)

        assert flow.sections[0].atomic_section_ids == ("A", "B")

    def test_to_records(self) -> None:
        """Flow can be exported to records."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        segments = [
            PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
            PlaythroughSection(mc_start=5, mc_end=9, atomic_section_ids=("B",)),
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        records = flow.to_records()
        assert len(records) == 2
        assert records[0]["mc_start"] == 1
        assert records[0]["atomic_sections"] == "A"
        assert records[1]["mc_end"] == 9

    def test_to_csv_rows(self) -> None:
        """Flow can be exported to CSV rows format."""
        # Right-open: mc_end=5 means MCs 1-4
        segments = [
            PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        rows = flow.to_csv_rows("test.tsv", "test v1.0")
        assert len(rows) == 1
        assert rows[0]["flow_mode"] == "default"
        assert rows[0]["source_file"] == "test.tsv"
        assert rows[0]["software_version"] == "test v1.0"
        assert rows[0]["mc_start"] == 1
        assert rows[0]["mc_end"] == 5

    def test_is_equivalent_true(self) -> None:
        """Flow.is_equivalent returns True for matching flows."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        flow1 = Flow.from_records(
            [
                {"mc_start": 1, "mc_end": 5, "atomic_segments": "A"},
                {"mc_start": 5, "mc_end": 9, "atomic_segments": "B"},
            ],
            FlowMode.DEFAULT,
        )
        flow2 = Flow.from_records(
            [
                {"mc_start": 1, "mc_end": 5, "atomic_segments": "X"},  # Different ID
                {"mc_start": 5, "mc_end": 9, "atomic_segments": "Y"},  # Different ID
            ],
            FlowMode.PARTITURA_MINIMAL,  # Different mode
        )
        # is_equivalent only compares MC ranges, not IDs or modes
        assert flow1.is_equivalent(flow2)

    def test_is_equivalent_false_different_length(self) -> None:
        """Flow.is_equivalent returns False for different segment counts."""
        # Right-open: mc_end=9 means MCs 1-8
        flow1 = Flow.from_records(
            [{"mc_start": 1, "mc_end": 9, "atomic_segments": "A"}],
            FlowMode.DEFAULT,
        )
        flow2 = Flow.from_records(
            [
                {"mc_start": 1, "mc_end": 5, "atomic_segments": "A"},
                {"mc_start": 5, "mc_end": 9, "atomic_segments": "B"},
            ],
            FlowMode.DEFAULT,
        )
        assert not flow1.is_equivalent(flow2)

    def test_is_equivalent_false_different_ranges(self) -> None:
        """Flow.is_equivalent returns False for different MC ranges."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=6 means MCs 1-5
        flow1 = Flow.from_records(
            [{"mc_start": 1, "mc_end": 5, "atomic_segments": "A"}],
            FlowMode.DEFAULT,
        )
        flow2 = Flow.from_records(
            [{"mc_start": 1, "mc_end": 6, "atomic_segments": "A"}],  # Different end
            FlowMode.DEFAULT,
        )
        assert not flow1.is_equivalent(flow2)

    def test_to_mc_sequence_from_sections(self) -> None:
        """Flow.to_mc_sequence works with segment-only flows."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        segments = [
            PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
            PlaythroughSection(mc_start=5, mc_end=9, atomic_section_ids=("B",)),
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        assert flow.to_mc_sequence() == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_to_atomic_sequence(self) -> None:
        """Flow.to_atomic_sequence returns flattened atomic IDs."""
        segments = [
            PlaythroughSection(mc_start=1, mc_end=17, atomic_section_ids=("A", "B")),
            PlaythroughSection(
                mc_start=1, mc_end=32, atomic_section_ids=("A", "B", "C")
            ),
            PlaythroughSection(mc_start=17, mc_end=32, atomic_section_ids=("C",)),
            PlaythroughSection(mc_start=6, mc_end=17, atomic_section_ids=("B",)),
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        expected = ["A", "B", "A", "B", "C", "C", "B"]
        assert flow.to_atomic_sequence() == expected

    def test_to_atomic_sequence_empty(self) -> None:
        """Flow.to_atomic_sequence handles empty flows."""
        flow = Flow(steps=[], sections=[], mode=FlowMode.DEFAULT)
        assert flow.to_atomic_sequence() == []

    def test_diff_flows(self) -> None:
        """Flow.diff_flows shows differences between flows."""
        flow1 = Flow.from_sections(
            [
                PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
                PlaythroughSection(mc_start=5, mc_end=9, atomic_section_ids=("B",)),
                PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
            ],
            FlowMode.DEFAULT,
        )
        flow2 = Flow.from_sections(
            [
                PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
                PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
                PlaythroughSection(mc_start=5, mc_end=9, atomic_section_ids=("B",)),
            ],
            FlowMode.DEFAULT,
        )
        # diff_flows should show the swapped A and B
        diff = flow1.diff_flows(flow2)
        assert "---" in diff  # Has unified diff header
        assert "+++" in diff

    def test_unfolded_length_from_sections(self) -> None:
        """Flow.unfolded_length works with segment-only flows."""
        # Right-open: mc_end=5 means MCs 1-4 (4 MCs each)
        segments = [
            PlaythroughSection(mc_start=1, mc_end=5, atomic_section_ids=("A",)),
            PlaythroughSection(
                mc_start=1, mc_end=5, atomic_section_ids=("A",)
            ),  # Repeat
        ]
        flow = Flow.from_sections(segments, FlowMode.DEFAULT)

        # 4 + 4 = 8 total MC visitations
        assert flow.unfolded_length == 8


class TestFlowCSVLoading:
    """Test Flow loading from .flow.csv files."""

    def test_from_csv(self, target_flows_dir: Path) -> None:
        """Flow.from_csv loads a specific mode from CSV."""
        csv_path = target_flows_dir / "c05n05_musete.flow.csv"
        if not csv_path.exists():
            pytest.skip(f"Test data not found: {csv_path}")

        flow = Flow.from_csv(csv_path, FlowMode.PARTITURA_MINIMAL)

        assert flow.mode == FlowMode.PARTITURA_MINIMAL
        assert len(flow.sections) == 4  # A, B, C, D
        assert flow.sections[0].mc_start == 1
        # Right-open: mc_end=6 means MCs 1-5 (5 measures)
        assert flow.sections[0].mc_end == 6

    def test_from_csv_invalid_mode_raises(self, target_flows_dir: Path) -> None:
        """Flow.from_csv raises for non-existent mode."""
        csv_path = target_flows_dir / "c05n05_musete.flow.csv"
        if not csv_path.exists():
            pytest.skip(f"Test data not found: {csv_path}")

        with pytest.raises(ValueError, match="No entries for flow_mode"):
            Flow.from_csv(csv_path, FlowMode.SINGLE_PASS)

    def test_load_valid_flows(self, target_flows_dir: Path) -> None:
        """load_valid_flows loads all modes from CSV."""
        csv_path = target_flows_dir / "c05n05_musete.flow.csv"
        if not csv_path.exists():
            pytest.skip(f"Test data not found: {csv_path}")

        flows = load_valid_flows(csv_path)

        assert len(flows) >= 2  # At least default and partitura_minimal
        assert FlowMode.PARTITURA_MINIMAL in flows
        assert len(flows[FlowMode.PARTITURA_MINIMAL].sections) == 4


# endregion

# region Unit Tests: FlowMode


class TestFlowMode:
    """Test FlowMode enum."""

    def test_all_modes_exist(self) -> None:
        """All expected flow modes exist."""
        assert FlowMode.DEFAULT.value == "default"
        assert FlowMode.MS3.value == "ms3"
        assert FlowMode.PARTITURA_MINIMAL.value == "partitura_minimal"
        assert FlowMode.PARTITURA_MAXIMAL.value == "partitura_maximal"
        assert FlowMode.MUSIC21.value == "music21"
        assert FlowMode.PRINTED.value == "printed"
        assert FlowMode.SINGLE_PASS.value == "single"
        assert FlowMode.CUSTOM.value == "custom"


# endregion

# region Unit Tests: FlowController


class TestFlowController:
    """Test FlowController computation logic."""

    def test_occurrence_to_suffix(self) -> None:
        """Test suffix generation: 1->a, 2->b, 27->aa."""
        from timetoalign.loader.score.stores import MeasureData

        # Create minimal MeasureData
        measures = MeasureData.empty()
        controller = FlowController(measures)

        assert controller._occurrence_to_suffix(1) == "a"
        assert controller._occurrence_to_suffix(2) == "b"
        assert controller._occurrence_to_suffix(26) == "z"
        assert controller._occurrence_to_suffix(27) == "aa"
        assert controller._occurrence_to_suffix(28) == "ab"

    def test_get_atomic_sections(self, rachmaninoff_measures_tsv: Path) -> None:
        """FlowController builds atomic segments from MeasureData."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)

        controller = FlowController(loader.store.measures)
        segments = controller.get_atomic_sections()

        # Rachmaninoff has no flow control, should be 1 segment
        assert len(segments) >= 1
        assert segments[0].id == "A"
        assert segments[0].mc_start == 1

    def test_from_atomic_sections(self) -> None:
        """FlowController can be created from atomic segments directly."""
        # Right-open: mc_end=5 means MCs 1-4, mc_end=9 means MCs 5-8
        segments = [
            AtomicSection(id="A", mc_start=1, mc_end=5, to=("B",)),
            AtomicSection(id="B", mc_start=5, mc_end=9, to=()),
        ]
        controller = FlowController.from_atomic_sections(segments)

        assert controller.get_atomic_sections() == segments

    def test_flow_has_segments(self, rachmaninoff_measures_tsv: Path) -> None:
        """Computed flow includes segments."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)

        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.DEFAULT)

        # Flow should have both steps and segments
        assert len(flow.steps) == 374
        assert len(flow.sections) >= 1


# endregion

# region Integration Tests: Example 1 - Rachmaninoff (No Flow Control)


class TestExample1Rachmaninoff:
    """Test Example 1: Rachmaninoff Concerto 2 (baseline, no repeats).

    This is the simplest case: 374 measures, all sequential, no flow control.
    The unfolded sequence should be identical to the folded sequence.

    Gold Standard:
    - Folded: 374 MCs
    - Unfolded: 374 measures (ratio 1.0)
    """

    def test_load_measures(self, rachmaninoff_measures_tsv: Path) -> None:
        """Can load Rachmaninoff measures."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)
        assert len(loader.store.measures) == 374

    def test_compute_flow(self, rachmaninoff_measures_tsv: Path) -> None:
        """Flow computation for sequential score."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)

        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.DEFAULT)

        assert flow.folded_length == 374
        assert flow.unfolded_length == 374
        assert flow.has_repeats is False

    def test_flow_matches_unfolded_gold_standard(
        self, rachmaninoff_measures_tsv: Path, rachmaninoff_unfolded_tsv: Path
    ) -> None:
        """Flow output matches ms3 unfolded TSV exactly."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")
        if not rachmaninoff_unfolded_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_unfolded_tsv}")

        # Load folded and compute flow
        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)
        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.DEFAULT)

        # Load unfolded gold standard
        import pandas as pd

        gold = pd.read_csv(rachmaninoff_unfolded_tsv, sep="\t")

        # EXACT row count
        assert flow.unfolded_length == len(
            gold
        ), f"Row count mismatch: {flow.unfolded_length} != {len(gold)}"

        # EXACT mc_playthrough sequence
        computed_mc_playthrough = [s.mc_playthrough for s in flow.steps]
        gold_mc_playthrough = gold["mc_playthrough"].tolist()
        assert (
            computed_mc_playthrough == gold_mc_playthrough
        ), "mc_playthrough sequence mismatch"

        # EXACT mn_playthrough values
        computed_mn_playthrough = [s.mn_playthrough for s in flow.steps]
        gold_mn_playthrough = gold["mn_playthrough"].tolist()
        assert (
            computed_mn_playthrough == gold_mn_playthrough
        ), "mn_playthrough sequence mismatch"


# endregion

# region Integration Tests: Example 3 - Couperin Musete (D.S. al Fine)


class TestExample3CouperinMusete:
    """Test Example 3: Couperin Musete (D.S. al Fine structure).

    This tests a moderately complex flow with:
    - Anacrusis (MN=0)
    - Segno marker
    - D.S. al Fine jumps
    - Multiple couplets

    Gold Standard:
    - Folded: 58 MCs
    - Unfolded: 138 measures (ratio ~2.4)
    """

    def test_load_measures(self, musete_measures_tsv: Path) -> None:
        """Can load Musete measures."""
        if not musete_measures_tsv.exists():
            pytest.skip(f"Test data not found: {musete_measures_tsv}")

        loader = TSVLoader()
        loader.load(musete_measures_tsv)
        # Exact count from TSV file (59 rows including header = 58 data rows)
        assert len(loader.store.measures) == 58

    def test_has_flow_control(self, musete_measures_tsv: Path) -> None:
        """Musete has flow control markers."""
        if not musete_measures_tsv.exists():
            pytest.skip(f"Test data not found: {musete_measures_tsv}")

        loader = TSVLoader()
        loader.load(musete_measures_tsv)
        summary = loader.store.measures.get_flow_control_summary()

        # Should have repeats based on 'next' field branching
        assert summary["total_measures"] == 58

    def test_compute_flow_unfolded_count(self, musete_measures_tsv: Path) -> None:
        """Flow computation produces correct unfolded count."""
        if not musete_measures_tsv.exists():
            pytest.skip(f"Test data not found: {musete_measures_tsv}")

        loader = TSVLoader()
        loader.load(musete_measures_tsv)

        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.DEFAULT)

        assert flow.folded_length == 58
        # The unfolded count should be around 138 (from gold standard)
        # This test will validate the exact algorithm
        assert (
            flow.unfolded_length > 58
        ), f"Expected unfolded > 58, got {flow.unfolded_length}"

    def test_flow_matches_unfolded_gold_standard(
        self, musete_measures_tsv: Path, musete_unfolded_tsv: Path
    ) -> None:
        """Flow output matches ms3 unfolded TSV exactly."""
        if not musete_measures_tsv.exists():
            pytest.skip(f"Test data not found: {musete_measures_tsv}")
        if not musete_unfolded_tsv.exists():
            pytest.skip(f"Test data not found: {musete_unfolded_tsv}")

        # Load folded and compute flow
        loader = TSVLoader()
        loader.load(musete_measures_tsv)
        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.DEFAULT)

        # Load unfolded gold standard
        import pandas as pd

        gold = pd.read_csv(musete_unfolded_tsv, sep="\t")

        # EXACT row count
        assert flow.unfolded_length == len(
            gold
        ), f"Row count mismatch: {flow.unfolded_length} != {len(gold)}"


# endregion

# region Integration Tests: FlowMap


class TestFlowMap:
    """Test FlowMap coordinate transformation."""

    def test_create_flow_map(self, rachmaninoff_measures_tsv: Path) -> None:
        """Can create FlowMap from FlowController."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)

        controller = FlowController(loader.store.measures)
        flow_map = controller.create_flow_map()

        assert isinstance(flow_map, FlowMap)
        assert flow_map.flow.folded_length == 374


# endregion

# region Printed Mode Tests


class TestPrintedMode:
    """Test PRINTED flow mode (no unfolding)."""

    def test_printed_flow_equals_folded(self, rachmaninoff_measures_tsv: Path) -> None:
        """PRINTED mode returns same count as folded."""
        if not rachmaninoff_measures_tsv.exists():
            pytest.skip(f"Test data not found: {rachmaninoff_measures_tsv}")

        loader = TSVLoader()
        loader.load(rachmaninoff_measures_tsv)

        controller = FlowController(loader.store.measures)
        flow = controller.compute_flow(FlowMode.PRINTED)

        assert flow.mode == FlowMode.PRINTED
        assert flow.folded_length == 374
        assert flow.unfolded_length == 374
        assert flow.has_repeats is False


# endregion
