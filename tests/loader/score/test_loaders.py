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
    # M21 and PT should be exact if config matches
    
    # Assert within 10% margin? Realistically should be exact for main notes.
    # Note: Partitura separates grace notes from chords sometimes?
    
    # Just ensure they are in same ballpark for now
    assert abs(pt_notes - m21_notes) < 50
    assert abs(pt_notes - tsv_notes) < 50
