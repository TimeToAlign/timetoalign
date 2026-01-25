"""Tests for symbolic score loaders (ScoreBundle architecture)."""

from pathlib import Path

import pytest

from timetoalign.loader.score.bundle import ScoreBundle
from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.tsv import TSVLoader

DATA_DIR = Path(__file__).parents[2] / "data" / "midi" / "score"
MS3_DIR = DATA_DIR / "ms3"


@pytest.fixture
def chopin_xml():
    return DATA_DIR / "chopin_op10_no3.musicxml"


@pytest.fixture
def chopin_tsv_notes():
    return MS3_DIR / "chopin_op10_no3.notes.tsv"


class TestTSVLoader:
    """Tests for TSVLoader."""

    def test_returns_score_bundle(self, chopin_tsv_notes):
        """TSVLoader.load() populates ScoreBundle."""
        loader = TSVLoader()
        loader.load(chopin_tsv_notes)
        bundle = loader.bundle

        assert isinstance(bundle, ScoreBundle)
        assert len(bundle.notes) > 0
        assert "parser" in bundle.metadata
        assert bundle.metadata["parser"] == "ms3"

    def test_note_count(self, chopin_tsv_notes):
        """TSV gold standard has 498 notes."""
        loader = TSVLoader()
        loader.load(chopin_tsv_notes)
        bundle = loader.bundle
        assert len(bundle.notes) == 498

    def test_fraction_schema(self, chopin_tsv_notes):
        """Temporal fields use Fraction struct."""
        loader = TSVLoader()
        loader.load(chopin_tsv_notes)
        bundle = loader.bundle
        first = list(bundle.notes)[0]

        qb = first.get("start")
        assert qb is not None
        assert "numerator" in qb and "denominator" in qb
        assert "value" in qb

    def test_pitch_schema(self, chopin_tsv_notes):
        """Pitch fields properly populated."""
        loader = TSVLoader()
        loader.load(chopin_tsv_notes)
        bundle = loader.bundle
        first = list(bundle.notes)[0]

        mp = first.get("midi_pitch")
        assert mp is not None
        assert "ep" in mp and mp["ep"] == 59  # B3

        sp = first.get("spelled_pitch")
        assert sp is not None
        assert sp.get("gpc_str") == "B"


class TestPartituraLoader:
    """Tests for PartituraLoader."""

    def test_returns_score_bundle(self, chopin_xml):
        """PartituraLoader.load() populates ScoreBundle."""
        loader = PartituraLoader()
        loader.load(chopin_xml)
        bundle = loader.bundle

        assert isinstance(bundle, ScoreBundle)
        assert len(bundle.notes) > 0
        assert len(bundle.measures) > 0
        assert bundle.metadata["parser"] == "partitura"

    def test_note_count(self, chopin_xml):
        """Partitura matches TSV gold standard (498 notes)."""
        loader = PartituraLoader()
        loader.load(chopin_xml)
        bundle = loader.bundle

        # Filter to Notes only (exclude Rests)
        df = bundle.notes.to_dataframe()
        note_count = len(df[df["event_type"] == "Note"])
        assert note_count == 498

    def test_measure_count(self, chopin_xml):
        """Partitura extracts measures."""
        loader = PartituraLoader()
        loader.load(chopin_xml)
        bundle = loader.bundle
        assert len(bundle.measures) == 22

    def test_fraction_schema(self, chopin_xml):
        """Temporal fields use Fraction struct."""
        loader = PartituraLoader()
        loader.load(chopin_xml)
        bundle = loader.bundle
        first = list(bundle.notes)[0]

        qb = first.get("start")
        assert qb is not None
        assert "numerator" in qb and "denominator" in qb
        assert "value" in qb


class TestMusic21Loader:
    """Tests for Music21Loader."""

    def test_returns_score_bundle(self, chopin_xml):
        """Music21Loader.load() populates ScoreBundle."""
        loader = Music21Loader()
        loader.load(chopin_xml)
        bundle = loader.bundle

        assert isinstance(bundle, ScoreBundle)
        assert len(bundle.notes) > 0
        assert bundle.metadata["parser"] == "music21"

    def test_note_count(self, chopin_xml):
        """Music21 matches TSV gold standard (498 notes + optional rests)."""
        loader = Music21Loader()
        loader.load(chopin_xml)
        bundle = loader.bundle

        df = bundle.notes.to_dataframe()
        note_count = len(df[df["event_type"] == "Note"])
        rest_count = len(df[df["event_type"] == "Rest"])

        # Notes must match exactly
        assert note_count == 498, f"Expected 498 notes, got {note_count}"

        # Rests: if has_rests is True, we should have some
        # The exact count may vary by music21 version
        if bundle.notes.has_rests:
            assert rest_count > 0, "has_rests=True but no rests found"
        # Total should be notes + rests
        assert len(df) == note_count + rest_count

    def test_fraction_schema(self, chopin_xml):
        """Temporal fields use Fraction struct."""
        loader = Music21Loader()
        loader.load(chopin_xml)
        bundle = loader.bundle
        first = list(bundle.notes)[0]

        qb = first.get("start")
        assert qb is not None
        assert "numerator" in qb and "denominator" in qb
        assert "value" in qb


class TestCrossValidation:
    """Cross-validation tests comparing all loaders."""

    def test_note_counts_match(self, chopin_xml, chopin_tsv_notes):
        """All loaders return same Note count (excluding rests)."""
        l1 = TSVLoader()
        l1.load(chopin_tsv_notes)
        tsv_bundle = l1.bundle

        l2 = PartituraLoader()
        l2.load(chopin_xml)
        pt_bundle = l2.bundle

        l3 = Music21Loader()
        l3.load(chopin_xml)
        m21_bundle = l3.bundle

        tsv_df = tsv_bundle.notes.to_dataframe()
        pt_df = pt_bundle.notes.to_dataframe()
        m21_df = m21_bundle.notes.to_dataframe()

        tsv_notes = len(tsv_df[tsv_df["event_type"] == "Note"])
        pt_notes = len(pt_df[pt_df["event_type"] == "Note"])
        m21_notes = len(m21_df[m21_df["event_type"] == "Note"])

        assert tsv_notes == 498
        assert pt_notes == 498
        assert m21_notes == 498

    def test_first_note_pitch_match(self, chopin_xml, chopin_tsv_notes):
        """First note has same pitch across all loaders."""
        l1 = TSVLoader()
        l1.load(chopin_tsv_notes)
        tsv = l1.bundle

        l2 = PartituraLoader()
        l2.load(chopin_xml)
        pt = l2.bundle

        l3 = Music21Loader()
        l3.load(chopin_xml)
        m21 = l3.bundle

        tsv_first = list(tsv.notes)[0]
        pt_first = list(pt.notes)[0]
        m21_first = list(m21.notes)[0]

        # All should be B3 (MIDI 59)
        assert tsv_first["midi_pitch"]["ep"] == 59
        assert pt_first["midi_pitch"]["ep"] == 59
        assert m21_first["midi_pitch"]["ep"] == 59

    def test_mc_onset_populated(self, chopin_xml, chopin_tsv_notes):
        """mc_onset is populated for all loaders."""
        l1 = TSVLoader()
        l1.load(chopin_tsv_notes)
        tsv = l1.bundle

        l2 = PartituraLoader()
        l2.load(chopin_xml)
        pt = l2.bundle

        l3 = Music21Loader()
        l3.load(chopin_xml)
        m21 = l3.bundle

        for bundle, name in [(tsv, "TSV"), (pt, "Partitura"), (m21, "Music21")]:
            first = list(bundle.notes)[0]
            mc_onset = first.get("mc_onset")
            assert mc_onset is not None, f"{name}: mc_onset is None"
            assert "num" in mc_onset, f"{name}: mc_onset missing num"
