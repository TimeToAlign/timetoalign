"""Tests for ScoreMidiLoader."""

from pathlib import Path

import pytest

from timetoalign.loader.midi import ScoreMidiLoader


class TestScoreMidiLoader:
    """Tests for loading score MIDI files."""

    def test_load_beethoven_quartet(self, beethoven_score_path: Path) -> None:
        """Can load multi-part score MIDI."""
        if not beethoven_score_path.exists():
            pytest.skip("Test data not found")

        loader = ScoreMidiLoader(part_voice_assign_mode=0)
        loader.load(beethoven_score_path)

        assert len(loader) == 3751  # beethoven_op18.mid has 3751 events
        assert loader.ticks_per_beat is not None

        # Check metadata
        meta = loader.metadata["sources"][0]
        assert meta["parser"] == "partitura"
        assert meta["parts"] == 4  # String quartet: 4 parts

        # Check events have score info
        df = loader.events.to_dataframe()
        assert not df["pitch"].isnull().all()

    def test_load_empty_raises(self, tmp_path: Path) -> None:
        """Loading invalid/empty file raises error."""
        # ScoreMidiLoader uses partitura which raises its own errors or returns empty
        empty_file = tmp_path / "empty.mid"
        empty_file.touch()

        loader = ScoreMidiLoader()
        # ScoreMidiLoader uses partitura which raises EOFError on empty file
        # (no exception wrapping in score.py, raw partitura error escapes)
        with pytest.raises(EOFError):
            loader.load(empty_file)


if __name__ == "__main__":
    pytest.main([__file__])
