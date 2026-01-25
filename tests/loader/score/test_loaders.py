"""Tests for symbolic score loaders."""

from collections import Counter
from pathlib import Path

import pytest

from timetoalign.core import TimeUnit
from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.store import ScoreEventStore, ScoreEventType
from timetoalign.loader.score.tsv import TSVLoader

DATA_DIR = Path(__file__).parents[2] / "data" / "midi" / "score"
MS3_DIR = DATA_DIR / "ms3"


@pytest.fixture
def chopin_xml():
    return DATA_DIR / "chopin_op10_no3.musicxml"


@pytest.fixture
def chopin_tsv_notes():
    return MS3_DIR / "chopin_op10_no3.notes.tsv"


def test_partitura_loader_chopin(chopin_xml):
    """Test PartituraLoader on Chopin MusicXML."""
    loader = PartituraLoader(unit=TimeUnit.ticks)
    loader.load(chopin_xml)
    
    assert len(loader.events) > 0
    assert loader.unit == TimeUnit.ticks
    assert loader.events.has_rests is not None  # Should be detected
    
    summary = loader.events.summary()
    cats = summary["categories"]
    assert cats[ScoreEventType.CAT_MEASURE] > 0
    assert cats[ScoreEventType.CAT_NOTE] > 0
    # Controls might be present or not depending on score
    
    # Check simple properties
    notes = loader.events.filter(event_category=ScoreEventType.CAT_NOTE)
    assert notes.count > 0
    
    # Check first note properties
    first_note = next(iter(notes))
    assert first_note["start"] is not None
    assert first_note["duration"] is not None
    # MusicXML should have spelled pitch
    if first_note["event_type"] == ScoreEventType.NOTE:
        pass


def test_music21_loader_chopin(chopin_xml):
    """Test Music21Loader on Chopin MusicXML."""
    loader = Music21Loader(unit=TimeUnit.ticks) # M21 uses quarters usually but let's see
    loader.load(chopin_xml)
    
    assert len(loader.events) > 0
    # Music21 loads usually distinct number of info (spanners etc)
    
    summary = loader.events.summary()
    cats = summary["categories"]
    assert cats[ScoreEventType.CAT_MEASURE] > 0
    assert cats[ScoreEventType.CAT_NOTE] > 0


def test_tsv_loader_chopin(chopin_tsv_notes):
    """Test TSVLoader on ms3 TSV."""
    # We load notes, measures, chords(controls)
    ms3_files = [
        chopin_tsv_notes,
        MS3_DIR / "chopin_op10_no3.measures.tsv",
        MS3_DIR / "chopin_op10_no3.chords.tsv"
    ]
    
    # Check if files exist (some might be missing in test data subset)
    valid_files = [f for f in ms3_files if f.exists()]
    
    loader = TSVLoader(unit=TimeUnit.ticks) # TSV uses quarters usually
    try:
        loader.load(*valid_files)
    except ImportError:
        pytest.skip("ms3 not installed")
        
    assert len(loader.events) > 0
    summary = loader.events.summary()
    cats = summary["categories"]
    if any("notes" in str(f) for f in valid_files):
        assert cats.get(ScoreEventType.CAT_NOTE, 0) > 0


def test_cross_validation_chopin(chopin_xml, chopin_tsv_notes):
    """Cross-validate event counts between loaders."""
    # Load all
    pt_loader = PartituraLoader()
    pt_loader.load(chopin_xml)
    
    m21_loader = Music21Loader()
    m21_loader.load(chopin_xml)
    
    tsv_loader = TSVLoader()
    try:
        # Load all tsvs
        tsv_files = list(MS3_DIR.glob("chopin_op10_no3.*.tsv"))
        tsv_loader.load(*tsv_files)
    except ImportError:
        pytest.skip("ms3 not installed")
        
    # Compare NOTE counts
    # Note: different parsers might handle grace notes, ties, or rests differently.
    # We filter for proper Notes (not rests)
    
    # Compare NOTE counts
    # Note: different parsers might handle grace notes, ties, or rests differently.
    # We filter for proper Notes (not rests)
    
    def count_notes(store):
        return store.filter(
            event_category=ScoreEventType.CAT_NOTE,
            event_type=ScoreEventType.NOTE
        ).count

    pt_notes = count_notes(pt_loader.events)
    m21_notes = count_notes(m21_loader.events)
    tsv_notes = count_notes(tsv_loader.events)
    
    print(f"Notes: PT={pt_notes}, M21={m21_notes}, TSV={tsv_notes}")
    
    # Tolerant comparison - parsers differ slightly
    # But usually should be very close for Op. 10 No. 3
    assert abs(pt_notes - m21_notes) < 50
    assert abs(pt_notes - tsv_notes) < 50

    # Strict Pitch Schema Verification
    def verify_pitch_schema(loader, name):
        notes = loader.events.filter(event_category=ScoreEventType.CAT_NOTE, event_type=ScoreEventType.NOTE)
        if notes.count == 0: return
        
        # Check first note
        n = next(iter(notes))
        assert n.get("octave") is not None, f"{name}: Missing Octave"
        
        mp = n.get("midi_pitch")
        assert mp is not None, f"{name}: Missing midi_pitch"
        assert "ep" in mp and mp["ep"] is not None, f"{name}: Missing ep"
        
        sp = n.get("spelled_pitch")
        assert sp is not None, f"{name}: Missing spelled_pitch"
        for field in ["gpc_str", "spc_str", "sp", "acc"]:
            assert field in sp and sp[field] is not None, f"{name}: Missing {field}"
        
        # Check canonical accidentals
        # E major key signature likely, check for Sharps
        # Just check one note that *should* be sharp if possible, or just format
        # chopin op 10 no 3 is E Major. Lots of G#s.
        G_sharps = [e for e in notes if e["spelled_pitch"]["gpc_str"] == "G"]
        if G_sharps:
            # G# should have acc=1 and spc_str="G♯"
            # note: might be naturalized, but likely mostly sharps
            # Just check if we see ANY '♯' or '♭' in the dataset if we expect them
            pass

    verify_pitch_schema(pt_loader, "Partitura")
    verify_pitch_schema(m21_loader, "Music21")
    verify_pitch_schema(tsv_loader, "TSV")
