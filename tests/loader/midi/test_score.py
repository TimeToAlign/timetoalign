"""Tests for ScoreMidiLoader."""

from pathlib import Path

import pytest

from timetoalign.loader.midi import MidiEventData, ScoreMidiEventData, ScoreMidiLoader


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

    def test_score_emits_wide_schema(self, beethoven_score_path: Path) -> None:
        """Score MIDI emits the wider 10-extra-column schema.

        Partitura supplies ``voice``, ``staff`` and ``part_id`` per
        note, so the storage class is :class:`ScoreMidiEventData`
        (not the narrower performance-side :class:`MidiEventData`).
        """
        if not beethoven_score_path.exists():
            pytest.skip("Test data not found")

        loader = ScoreMidiLoader(part_voice_assign_mode=0)
        loader.load(beethoven_score_path)

        # Concrete class is the wider subclass.
        assert type(loader.events) is ScoreMidiEventData
        # Subclass relationship is preserved.
        assert isinstance(loader.events, MidiEventData)

        columns = set(loader.events.table.column_names)
        for required in (
            "pitch",
            "velocity",
            "channel",
            "track",
            "control",
            "value",
            "program",
            "voice",
            "staff",
            "part_id",
        ):
            assert required in columns, f"missing {required} column"


if __name__ == "__main__":
    pytest.main([__file__])
