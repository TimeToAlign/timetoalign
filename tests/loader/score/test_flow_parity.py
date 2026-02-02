"""Flow Parity Tests: Validate flow computation across loaders against gold standard.

.. deprecated::

    This module is DEPRECATED. Its functionality has been subsumed by:

    - **test_flow_csv_validation.py**: Tests using Flow.is_equivalent() for
      section-based comparison against .flow.csv ground truth files
    - **tests/timelines/test_flow.py**: Unit tests for AtomicSection,
      PlaythroughSection, Flow, and FlowController

    The section-based architecture in `timetoalign.timelines.flow` provides:
    - AtomicSection and PlaythroughSection dataclasses
    - Flow.from_csv() / load_valid_flows() for loading ground truth
    - Flow.is_equivalent() for comparing flows by MC ranges


    **Architecture Change (Phase 10)**:

    MeasureUnit-based architecture with semantic groupings:
    - `MeasureUnit` replaces `FlowStep` as fundamental building block
    - `MeasureGroup` hierarchy: IncompleteMeasure, CompleteMeasure, Volta, etc.
    - AtomicSection/PlaythroughSection contain `groups: list[MeasureGroup]`
    - FlowController.iter_units() iterates over MeasureUnits
    - FlowController.iter_sections(mode=None) returns AtomicSections by default
    - FlowController.get_volta_groups() returns all Volta objects (query, not structural)

    **Migration Path**:
    - MC sequence comparison -> Use Flow.is_equivalent()
    - Gold standard loading -> Use load_valid_flows() from .flow.csv
    - MeasureUnit iteration -> Use controller.iter_units()
    - Section iteration -> Use controller.iter_sections()
    - Diagnostic output -> See TestDiagnosticOutput in test_flow_csv_validation.py

    See: .agent/prompts/flowcontrol_architecture_redesign.md (Phase 10) for details.

This module tests that different score loaders produce flows that match the
ms3 gold standard (unfolded TSV). For each specimen, we:

1. Load the gold standard MC sequence from the unfolded TSV
2. Load the score from various formats (MusicXML, MEI, mm.json, TSV via partitura)
3. Compute the flow using FlowController
4. Compare the computed MC sequence against the gold standard

Per ZERO TOLERANCE VALIDATION POLICY (from AGENTS.md):
- EXACT MC sequence match required
- No tolerances or approximations
- Every mismatch must be investigated

Test Matrix:
| Specimen | TSV (ms3) | MeasureMap | Music21 XML | Music21 MEI | Partitura XML | Partitura TSV |
|----------|-----------|------------|-------------|-------------|---------------|---------------|
| polyrhythm_only | gold | test | test | test | test | test |
| c05n05_musete | gold | test | test | test | test | test |
| Rachmaninoff | gold | test | test | test | test | test |
"""

from __future__ import annotations

from pathlib import Path

import pytest

# region Path Configuration

TESTS_DATA_DIR = Path(__file__).parents[2] / "data"
SCORE_DATA_DIR = TESTS_DATA_DIR / "score"

# Specimen paths
SPECIMENS = {
    "polyrhythm_only": {
        "dir": SCORE_DATA_DIR / "flow_control" / "polyrythm_only",
        "folded_tsv": "out_of_the_flow_experience-polyrhythm_only.measures.tsv",
        "unfolded_tsv": "out_of_the_flow_experience-polyrhythm_only_unfolded.measures.tsv",
        "mm_json": "out_of_the_flow_experience-polyrhythm_only.measures.mm.json",
        "musicxml": SCORE_DATA_DIR
        / "flow_control"
        / "out_of_the_flow_experience-polyrhythm_only.musicxml",
        "mei": SCORE_DATA_DIR
        / "flow_control"
        / "out_of_the_flow_experience-polyrhythm_only.mei",
        "expected_folded": 14,
        "expected_unfolded": 14,  # No flow control, same as folded
    },
    "c05n05_musete": {
        "dir": SCORE_DATA_DIR / "couperin_concerts",
        "folded_tsv": "c05n05_musete.measures.tsv",
        "unfolded_tsv": "c05n05_musete_unfolded.measures.tsv",
        "mm_json": "c05n05_musete.measures.mm.json",
        "musicxml": SCORE_DATA_DIR / "couperin_concerts" / "c05n05_musete.musicxml",
        "mei": SCORE_DATA_DIR / "couperin_concerts" / "c05n05_musete.mei",
        "expected_folded": 58,
        "expected_unfolded": 138,  # D.S. al Fine expands significantly
    },
    "rachmaninoff": {
        "dir": SCORE_DATA_DIR / "rachmaninoff_concerto2" / "score",
        "folded_tsv": "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.measures.tsv",
        "unfolded_tsv": "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff_unfolded.measures.tsv",
        "mm_json": "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.measures.mm.json",
        "musicxml": SCORE_DATA_DIR
        / "rachmaninoff_concerto2"
        / "score"
        / "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.musicxml",
        "mei": SCORE_DATA_DIR
        / "rachmaninoff_concerto2"
        / "score"
        / "Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.mei",
        "expected_folded": 374,
        "expected_unfolded": 374,  # No flow control
    },
}

# endregion

# region Helper Functions


def get_gold_standard_mc_sequence(specimen_name: str) -> list[int]:
    """Extract the MC sequence from the gold standard unfolded TSV.

    Args:
        specimen_name: Name of the specimen in SPECIMENS dict.

    Returns:
        List of MC values in unfolded order.
    """
    from timetoalign.loader.score import TSVLoader

    spec = SPECIMENS[specimen_name]
    unfolded_path = spec["dir"] / spec["unfolded_tsv"]

    if not unfolded_path.exists():
        pytest.skip(f"Gold standard not found: {unfolded_path}")

    loader = TSVLoader()
    loader.load(unfolded_path)

    # Extract MC column
    table = loader.store.measures._table
    mc_col = table.column("mc").to_pylist()
    return mc_col


def compute_flow_from_measuremap(specimen_name: str) -> list[int]:
    """Compute flow MC sequence from MeasureMap JSON.

    Args:
        specimen_name: Name of the specimen in SPECIMENS dict.

    Returns:
        List of MC values in computed flow order.
    """
    from timetoalign.loader.score import MeasureMapLoader

    spec = SPECIMENS[specimen_name]
    mm_path = spec["dir"] / spec["mm_json"]

    if not mm_path.exists():
        pytest.skip(f"MeasureMap not found: {mm_path}")

    loader = MeasureMapLoader()
    loader.load(mm_path)

    # Use MeasureMapLoader's built-in traversal computation
    return loader.compute_default_traversal()


def compute_flow_from_music21(source_path: Path) -> list[int]:
    """Compute flow MC sequence from Music21 loaded score.

    Args:
        source_path: Path to MusicXML or MEI file.

    Returns:
        List of MC values in computed flow order.
    """
    from timetoalign.loader.score import Music21Loader
    from timetoalign.timelines import FlowController

    if not source_path.exists():
        pytest.skip(f"Source file not found: {source_path}")

    loader = Music21Loader()
    loader.load(source_path)

    controller = FlowController(loader.store.measures)
    flow = controller.compute_flow()
    return flow.to_mc_sequence()


def compute_flow_from_partitura_xml(source_path: Path) -> list[int]:
    """Compute flow MC sequence from Partitura loaded score.

    Args:
        source_path: Path to MusicXML or MEI file.

    Returns:
        List of MC values in computed flow order.
    """
    from timetoalign.loader.score import PartituraLoader
    from timetoalign.timelines import FlowController

    if not source_path.exists():
        pytest.skip(f"Source file not found: {source_path}")

    loader = PartituraLoader()
    loader.load(source_path)

    controller = FlowController(loader.store.measures)
    flow = controller.compute_flow()
    return flow.to_mc_sequence()


def compute_flow_from_partitura_tsv(specimen_name: str) -> list[int]:
    """Compute flow MC sequence from Partitura loaded DCML TSV.

    Uses partitura.load_dcml() to load from TSV files.

    Args:
        specimen_name: Name of the specimen in SPECIMENS dict.

    Returns:
        List of MC values in computed flow order.
    """
    try:
        import partitura as pt
    except ImportError:
        pytest.skip("partitura not installed")

    spec = SPECIMENS[specimen_name]
    notes_path = spec["dir"] / spec["folded_tsv"].replace(".measures.tsv", ".notes.tsv")
    measures_path = spec["dir"] / spec["folded_tsv"]

    if not notes_path.exists():
        pytest.skip(f"Notes TSV not found: {notes_path}")
    if not measures_path.exists():
        pytest.skip(f"Measures TSV not found: {measures_path}")

    # Load using partitura.load_dcml
    score = pt.load_dcml(
        note_tsv_path=str(notes_path),
        measure_tsv_path=str(measures_path),
    )

    # Extract measures from partitura score
    parts = score.parts if hasattr(score, "parts") else [score]
    if not parts:
        pytest.skip("No parts in partitura score")

    part = parts[0]
    measures = sorted(part.iter_all(pt.score.Measure), key=lambda m: m.start.t)

    # Build MeasureData from partitura measures
    # For now, just return the printed sequence (no flow control from partitura)
    return [i + 1 for i in range(len(measures))]


# endregion

# region Test Classes


@pytest.mark.skip(
    reason="DEPRECATED: Use TestFlowEquivalence in test_flow_csv_validation.py"
)
@pytest.mark.parametrize(
    "specimen_name", ["polyrhythm_only", "c05n05_musete", "rachmaninoff"]
)
class TestMeasureMapFlowParity:
    """Test MeasureMapLoader flow computation against gold standard.

    .. deprecated:: Use TestFlowEquivalence in test_flow_csv_validation.py
    """

    def test_measuremap_flow_matches_gold_standard(self, specimen_name: str) -> None:
        """MeasureMapLoader computed flow matches ms3 gold standard."""
        gold_sequence = get_gold_standard_mc_sequence(specimen_name)
        computed_sequence = compute_flow_from_measuremap(specimen_name)

        assert len(computed_sequence) == len(gold_sequence), (
            f"{specimen_name}: MeasureMap flow length mismatch\n"
            f"  Expected: {len(gold_sequence)} (gold standard)\n"
            f"  Got: {len(computed_sequence)} (MeasureMap)\n"
            f"  First 10 computed: {computed_sequence[:10]}\n"
            f"  First 10 gold: {gold_sequence[:10]}"
        )

        assert computed_sequence == gold_sequence, (
            f"{specimen_name}: MeasureMap MC sequence mismatch\n"
            f"  First difference at index "
            f"{next(i for i, (a, b) in enumerate(zip(computed_sequence, gold_sequence)) if a != b)}"
        )


@pytest.mark.skip(
    reason="DEPRECATED: Use TestFlowEquivalence in test_flow_csv_validation.py"
)
@pytest.mark.parametrize(
    "specimen_name", ["polyrhythm_only", "c05n05_musete", "rachmaninoff"]
)
class TestMusic21FlowParity:
    """Test Music21Loader flow computation against gold standard.

    .. deprecated:: Use TestFlowEquivalence in test_flow_csv_validation.py
    """

    def test_music21_musicxml_flow_matches_gold_standard(
        self, specimen_name: str
    ) -> None:
        """Music21Loader (MusicXML) computed flow matches ms3 gold standard."""
        gold_sequence = get_gold_standard_mc_sequence(specimen_name)
        source_path = SPECIMENS[specimen_name]["musicxml"]
        computed_sequence = compute_flow_from_music21(source_path)

        assert len(computed_sequence) == len(gold_sequence), (
            f"{specimen_name}: Music21 MusicXML flow length mismatch\n"
            f"  Expected: {len(gold_sequence)} (gold standard)\n"
            f"  Got: {len(computed_sequence)} (Music21)"
        )

        assert (
            computed_sequence == gold_sequence
        ), f"{specimen_name}: Music21 MusicXML MC sequence mismatch"

    def test_music21_mei_flow_matches_gold_standard(self, specimen_name: str) -> None:
        """Music21Loader (MEI) computed flow matches ms3 gold standard."""
        gold_sequence = get_gold_standard_mc_sequence(specimen_name)
        source_path = SPECIMENS[specimen_name]["mei"]
        computed_sequence = compute_flow_from_music21(source_path)

        assert len(computed_sequence) == len(gold_sequence), (
            f"{specimen_name}: Music21 MEI flow length mismatch\n"
            f"  Expected: {len(gold_sequence)} (gold standard)\n"
            f"  Got: {len(computed_sequence)} (Music21 MEI)"
        )

        assert (
            computed_sequence == gold_sequence
        ), f"{specimen_name}: Music21 MEI MC sequence mismatch"


@pytest.mark.skip(
    reason="DEPRECATED: Use TestFlowEquivalence in test_flow_csv_validation.py"
)
@pytest.mark.parametrize(
    "specimen_name", ["polyrhythm_only", "c05n05_musete", "rachmaninoff"]
)
class TestPartituraFlowParity:
    """Test PartituraLoader flow computation against gold standard.

    .. deprecated:: Use TestFlowEquivalence in test_flow_csv_validation.py
    """

    def test_partitura_musicxml_flow_matches_gold_standard(
        self, specimen_name: str
    ) -> None:
        """PartituraLoader (MusicXML) computed flow matches ms3 gold standard."""
        gold_sequence = get_gold_standard_mc_sequence(specimen_name)
        source_path = SPECIMENS[specimen_name]["musicxml"]
        computed_sequence = compute_flow_from_partitura_xml(source_path)

        assert len(computed_sequence) == len(gold_sequence), (
            f"{specimen_name}: Partitura MusicXML flow length mismatch\n"
            f"  Expected: {len(gold_sequence)} (gold standard)\n"
            f"  Got: {len(computed_sequence)} (Partitura)"
        )

        assert (
            computed_sequence == gold_sequence
        ), f"{specimen_name}: Partitura MusicXML MC sequence mismatch"

    def test_partitura_mei_flow_matches_gold_standard(self, specimen_name: str) -> None:
        """PartituraLoader (MEI) computed flow matches ms3 gold standard."""
        gold_sequence = get_gold_standard_mc_sequence(specimen_name)
        source_path = SPECIMENS[specimen_name]["mei"]
        computed_sequence = compute_flow_from_partitura_xml(source_path)

        assert len(computed_sequence) == len(gold_sequence), (
            f"{specimen_name}: Partitura MEI flow length mismatch\n"
            f"  Expected: {len(gold_sequence)} (gold standard)\n"
            f"  Got: {len(computed_sequence)} (Partitura MEI)"
        )

        assert (
            computed_sequence == gold_sequence
        ), f"{specimen_name}: Partitura MEI MC sequence mismatch"


# endregion

# region Diagnostic Tests


class TestDiagnosticOutput:
    """Diagnostic tests that print flow comparison for debugging."""

    @pytest.mark.parametrize("specimen_name", ["polyrhythm_only"])
    def test_print_flow_comparison(self, specimen_name: str) -> None:
        """Print flow comparison across loaders for debugging."""
        print(f"\n{'=' * 70}")
        print(f"FLOW COMPARISON: {specimen_name}")
        print("=" * 70)

        try:
            gold = get_gold_standard_mc_sequence(specimen_name)
            print(f"Gold standard (ms3): {len(gold)} MCs")
            print(f"  Sequence: {gold[:20]}{'...' if len(gold) > 20 else ''}")
        except Exception as e:
            print(f"Gold standard: ERROR - {e}")
            gold = None

        try:
            mm = compute_flow_from_measuremap(specimen_name)
            print(f"MeasureMap: {len(mm)} MCs")
            print(f"  Sequence: {mm[:20]}{'...' if len(mm) > 20 else ''}")
            if gold:
                print(f"  Match: {mm == gold}")
        except Exception as e:
            print(f"MeasureMap: ERROR - {e}")

        try:
            m21 = compute_flow_from_music21(SPECIMENS[specimen_name]["musicxml"])
            print(f"Music21 MusicXML: {len(m21)} MCs")
            print(f"  Sequence: {m21[:20]}{'...' if len(m21) > 20 else ''}")
            if gold:
                print(f"  Match: {m21 == gold}")
        except Exception as e:
            print(f"Music21 MusicXML: ERROR - {e}")

        try:
            pt = compute_flow_from_partitura_xml(SPECIMENS[specimen_name]["musicxml"])
            print(f"Partitura MusicXML: {len(pt)} MCs")
            print(f"  Sequence: {pt[:20]}{'...' if len(pt) > 20 else ''}")
            if gold:
                print(f"  Match: {pt == gold}")
        except Exception as e:
            print(f"Partitura MusicXML: ERROR - {e}")

        print("=" * 70)

        # Diagnostic test always passes
        assert True


# endregion
