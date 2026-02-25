"""Integration tests: Loader to Timeline conversion with real data.

This module tests the complete pipeline from loading MusicXML/MIDI files
through EventStores to Timeline creation.

VALIDATION POLICY (per AGENTS.md Section 3.6):
- All counts are EXACT, not ranges or minimums
- Gold standard data is authoritative
- No tolerance without documented root cause
- Mismatches indicate bugs, not acceptable variance

Gold Standard Reference:
- Chopin Op.10 No.3 notes: EXACTLY 498 notes (MS3 TSV)
- Chopin Op.10 No.3 measures: EXACTLY 22 measures (MS3 TSV)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from timetoalign.timelines import create_timeline

# Test data paths
DATA_DIR = Path(__file__).parents[1] / "data" / "vienna_1x22"
SCORE_DIR = DATA_DIR
MS3_DIR = DATA_DIR / "ms3"
PERF_DIR = DATA_DIR

# Gold standard counts from MS3 TSV files
# Source: tests/data/vienna_1x22/ms3/chopin_op10_no3.notes.tsv (499 lines - 1 header = 498)
# Source: tests/data/vienna_1x22/ms3/chopin_op10_no3.measures.tsv (23 lines - 1 header = 22)
CHOPIN_GOLD_NOTES = 498
CHOPIN_GOLD_MEASURES = 22


class TestScoreLoaderToTimeline:
    """Integration tests for ScoreLoader to Timeline conversion.

    These tests validate the complete pipeline from MusicXML files through
    ScoreBundle to Timeline creation using real-world specimens.
    """

    @pytest.fixture
    def chopin_musicxml(self) -> Path:
        """Path to Chopin Op.10 No.3 MusicXML file."""
        path = SCORE_DIR / "Chopin_op10_no3.musicxml"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_partitura_to_default_timeline_structure(self, chopin_musicxml: Path):
        """PartituraLoader creates timeline with correct structure.

        Validates:
        - Timeline has expected ID
        - Timeline has children for each non-empty store
        - Children are at offset 0
        """
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_default_timeline(uid="chopin")

        # Verify parent structure
        assert timeline.id == "chopin"
        assert timeline.n_children == 3  # notes, measures, controls

        # Verify children exist
        assert "notes" in timeline
        assert "measures" in timeline

        # Verify offset 0
        assert timeline.get_child_offset("notes").value == 0
        assert timeline.get_child_offset("measures").value == 0

    def test_partitura_notes_count_exact(self, chopin_musicxml: Path):
        """Partitura loader note count matches gold standard EXACTLY.

        Gold standard: 498 notes from MS3 TSV file.
        """
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_default_timeline()
        notes_tl = timeline.get_child("notes")

        # EXACT count - no tolerance
        assert notes_tl.n_events == CHOPIN_GOLD_NOTES, (
            f"Note count mismatch: got {notes_tl.n_events}, "
            f"expected {CHOPIN_GOLD_NOTES} (gold standard from MS3 TSV)"
        )

    def test_partitura_measures_count_exact(self, chopin_musicxml: Path):
        """Partitura loader measure count matches gold standard EXACTLY.

        Gold standard: 22 measures from MS3 TSV file.
        """
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_default_timeline()
        measures_tl = timeline.get_child("measures")

        # EXACT count - no tolerance
        assert measures_tl.n_events == CHOPIN_GOLD_MEASURES, (
            f"Measure count mismatch: got {measures_tl.n_events}, "
            f"expected {CHOPIN_GOLD_MEASURES} (gold standard from MS3 TSV)"
        )

    def test_music21_notes_count_exact(self, chopin_musicxml: Path):
        """Music21 loader note count matches gold standard EXACTLY.

        Gold standard: 498 notes from MS3 TSV file.

        Note: Music21 creates implicit rests that don't exist in the source
        MusicXML file. The loader now excludes these to match gold standard.
        """
        from timetoalign.loader.score import Music21Loader

        loader = Music21Loader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_default_timeline()
        notes_tl = timeline.get_child("notes")

        # EXACT count - no tolerance
        assert notes_tl.n_events == CHOPIN_GOLD_NOTES, (
            f"Note count mismatch: got {notes_tl.n_events}, "
            f"expected {CHOPIN_GOLD_NOTES} (gold standard from MS3 TSV)"
        )

    def test_children_locked_after_timeline_creation(self, chopin_musicxml: Path):
        """Child timelines are locked after being added to parent."""
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_default_timeline()

        for _, child in timeline.iter_children():
            assert child.is_locked, f"Child {child.id} should be locked"


class TestScoreLoaderWithFilters:
    """Tests for filtered timeline creation from ScoreLoaders."""

    @pytest.fixture
    def chopin_musicxml(self) -> Path:
        """Path to Chopin Op.10 No.3 MusicXML file."""
        path = SCORE_DIR / "Chopin_op10_no3.musicxml"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_filter_notes_only(self, chopin_musicxml: Path):
        """Filter to notes store only.

        When include_stores filters to a single store, events are placed
        directly on the timeline (no children) per factory.py documentation.
        """
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_timeline(
            uid="notes_only",
            include_stores=["notes"],
        )

        # Single store: no children, events directly on timeline
        assert timeline.n_children == 0
        assert timeline.n_events == CHOPIN_GOLD_NOTES

    def test_exclude_controls_and_annotations(self, chopin_musicxml: Path):
        """Exclude controls and annotations stores."""
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = loader.store.to_timeline(
            exclude_stores=["controls", "annotations"],
        )

        # Should have notes and measures only
        assert "notes" in timeline
        assert "measures" in timeline


class TestMidiLoaderToTimeline:
    """Integration tests for MidiLoader to Timeline conversion."""

    @pytest.fixture
    def beethoven_midi(self) -> Path:
        """Path to Beethoven Op.18 MIDI file."""
        path = SCORE_DIR / "beethoven_op18.mid"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    @pytest.fixture
    def supra_midi(self) -> Path:
        """Path to Supra piano roll MIDI file."""
        path = PERF_DIR / "supra_raw.mid"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_score_midi_creates_bundle_with_notes_and_controls(
        self, beethoven_midi: Path
    ):
        """ScoreMidiLoader creates MidiBundle with notes and controls."""
        from timetoalign.loader.midi import ScoreMidiLoader

        loader = ScoreMidiLoader()
        loader.load(beethoven_midi)

        store = loader.store

        # MidiStore has notes and controls
        assert "notes" in store
        assert "controls" in store

    def test_score_midi_to_timeline_structure(self, beethoven_midi: Path):
        """ScoreMidiLoader timeline has correct structure.

        If controls store is empty, only notes remain, resulting in events
        placed directly on the timeline (no children) per factory.py.
        """
        from timetoalign.loader.midi import ScoreMidiLoader

        loader = ScoreMidiLoader()
        loader.load(beethoven_midi)

        timeline = loader.store.to_default_timeline(uid="beethoven")

        assert timeline.id == "beethoven"
        # Events are on the timeline (either directly or as children)
        # If only notes exist (controls empty), events are directly on timeline
        # If both exist, they become children
        if timeline.n_children > 0:
            assert "notes" in timeline
        else:
            assert timeline.n_events > 0

    def test_performance_midi_to_timeline(self, supra_midi: Path):
        """PerformanceMidiLoader creates timeline from piano roll."""
        from timetoalign.loader.midi import PerformanceMidiLoader

        loader = PerformanceMidiLoader()
        loader.load(supra_midi)

        timeline = loader.store.to_default_timeline(uid="supra")

        assert timeline.id == "supra"
        # Should have at least notes
        assert timeline.n_children >= 1

    def test_performance_midi_notes_child_has_events(self, supra_midi: Path):
        """Performance MIDI notes child has events."""
        from timetoalign.loader.midi import PerformanceMidiLoader

        loader = PerformanceMidiLoader()
        loader.load(supra_midi)

        timeline = loader.store.to_default_timeline()
        notes_tl = timeline.get_child("notes")

        # Supra raw has notes - verify non-zero
        # Exact count depends on the specimen
        assert notes_tl.n_events > 0


class TestCrossLoaderConsistency:
    """Verify timeline structure consistency across loaders.

    Per AGENTS.md Section 3.6: If two loaders parse the same file,
    they MUST produce identical core event counts.
    """

    @pytest.fixture
    def chopin_musicxml(self) -> Path:
        """Path to Chopin Op.10 No.3 MusicXML file."""
        path = SCORE_DIR / "Chopin_op10_no3.musicxml"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_partitura_vs_music21_note_count_identical(self, chopin_musicxml: Path):
        """Partitura and Music21 produce identical note counts.

        Both loaders must produce EXACTLY 498 notes (gold standard).
        Any difference indicates a bug in one of the loaders.
        """
        from timetoalign.loader.score import Music21Loader, PartituraLoader

        pt_loader = PartituraLoader()
        pt_loader.load(chopin_musicxml)
        pt_timeline = pt_loader.store.to_default_timeline()
        pt_notes = pt_timeline.get_child("notes").n_events

        m21_loader = Music21Loader()
        m21_loader.load(chopin_musicxml)
        m21_timeline = m21_loader.store.to_default_timeline()
        m21_notes = m21_timeline.get_child("notes").n_events

        # Both must equal gold standard
        assert (
            pt_notes == CHOPIN_GOLD_NOTES
        ), f"Partitura note count {pt_notes} != gold standard {CHOPIN_GOLD_NOTES}"
        assert (
            m21_notes == CHOPIN_GOLD_NOTES
        ), f"Music21 note count {m21_notes} != gold standard {CHOPIN_GOLD_NOTES}"

        # And therefore equal each other
        assert (
            pt_notes == m21_notes
        ), f"Loader parity violation: Partitura={pt_notes}, Music21={m21_notes}"

    def test_partitura_vs_music21_core_children_identical(self, chopin_musicxml: Path):
        """Partitura and Music21 produce identical CORE child structures.

        Core children (notes, measures, controls) must match.
        Annotations differ because:
        - Music21 parses TextExpressions (tempo markings, performance directions)
        - Partitura does not currently parse these text annotations

        This is a documented parser scope difference, not a bug.
        """
        from timetoalign.loader.score import Music21Loader, PartituraLoader

        pt_loader = PartituraLoader()
        pt_loader.load(chopin_musicxml)
        pt_timeline = pt_loader.store.to_default_timeline()

        m21_loader = Music21Loader()
        m21_loader.load(chopin_musicxml)
        m21_timeline = m21_loader.store.to_default_timeline()

        # Core children must be present in both
        core_children = {"notes", "measures", "controls"}

        pt_children = set(pt_timeline._children.keys())
        m21_children = set(m21_timeline._children.keys())

        # Both must have all core children
        assert core_children.issubset(
            pt_children
        ), f"Partitura missing core children: {core_children - pt_children}"
        assert core_children.issubset(
            m21_children
        ), f"Music21 missing core children: {core_children - m21_children}"

        # Core children must have same names
        pt_core = pt_children & core_children
        m21_core = m21_children & core_children
        assert (
            pt_core == m21_core
        ), f"Core child names mismatch: Partitura={pt_core}, Music21={m21_core}"

        # Document the annotation difference (not a failure)
        pt_has_annotations = "annotations" in pt_children
        m21_has_annotations = "annotations" in m21_children
        if pt_has_annotations != m21_has_annotations:
            # Expected: Music21 parses annotations, Partitura doesn't
            assert (
                m21_has_annotations and not pt_has_annotations
            ), "Unexpected annotation parsing difference"


class TestCreateTimelineFunction:
    """Tests for the universal create_timeline factory function."""

    @pytest.fixture
    def chopin_musicxml(self) -> Path:
        """Path to Chopin Op.10 No.3 MusicXML file."""
        path = SCORE_DIR / "Chopin_op10_no3.musicxml"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_create_timeline_from_loader(self, chopin_musicxml: Path):
        """create_timeline works directly with Loader."""
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = create_timeline(loader, uid="from_loader")

        assert timeline.id == "from_loader"
        assert timeline.n_children == 3  # notes, measures, controls

    def test_create_timeline_from_store(self, chopin_musicxml: Path):
        """create_timeline works with EventStore."""
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        timeline = create_timeline(loader.store, uid="from_store")

        assert timeline.id == "from_store"
        assert timeline.n_children == 3  # notes, measures, controls

    def test_create_timeline_with_filters(self, chopin_musicxml: Path):
        """create_timeline applies include_stores correctly.

        When include_stores filters to a single store, events are placed
        directly on the timeline (no children) per factory.py documentation.
        """
        from timetoalign.loader.score import PartituraLoader

        loader = PartituraLoader()
        loader.load(chopin_musicxml)

        # Use include_stores to select only notes
        # Single store -> events directly on timeline (no children)
        timeline = create_timeline(
            loader,
            include_stores=["notes"],
        )

        # Single store: no children, events directly on timeline
        assert timeline.n_children == 0
        assert timeline.n_events == CHOPIN_GOLD_NOTES
