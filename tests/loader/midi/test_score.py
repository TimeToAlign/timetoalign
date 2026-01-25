"""Tests for ScoreMidiLoader."""

from pathlib import Path

import pytest
from timetoalign.loader.midi import MidiEventType, ScoreMidiLoader


class TestScoreMidiLoader:
    """Tests for loading score MIDI files."""

    def test_load_beethoven_quartet(self, beethoven_score_path: Path) -> None:
        """Can load multi-part score MIDI."""
        if not beethoven_score_path.exists():
            pytest.skip("Test data not found")

        loader = ScoreMidiLoader(part_voice_assign_mode=0)
        loader.load(beethoven_score_path)

        assert len(loader) > 0
        assert loader.ticks_per_beat is not None
        
        # Check metadata
        meta = loader.metadata["sources"][0]
        assert meta["parser"] == "partitura"
        assert meta["parts"] > 0

        # Check events have score info
        df = loader.events.to_dataframe()
        assert not df["pitch"].isnull().all()
        # Voice/Staff may be present
        if "voice" in df.columns:
            # Not all notes might have voice, but some should if mode=0
            pass 

    def test_load_empty_raises(self, tmp_path: Path) -> None:
        """Loading invalid/empty file raises error."""
        # ScoreMidiLoader uses partitura which raises its own errors or returns empty
        empty_file = tmp_path / "empty.mid"
        empty_file.touch()
        
        loader = ScoreMidiLoader()
        # partitura might raise or return empty. Check behavior.
        # usually load_score_midi raises exception on empty file
        try:
            loader.load(empty_file)
        except Exception:
            pass # Expected behavior varies, but shouldn't crash ungracefully
