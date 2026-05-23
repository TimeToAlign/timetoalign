"""Tests for PerformanceMidiLoader."""

from pathlib import Path

import pytest

from timetoalign.loader.midi import (
    MidiEventData,
    MidiEventType,
    PerformanceMidiLoader,
    ScoreMidiEventData,
)


class TestPerformanceMidiLoader:
    """Tests for loading performance MIDI files."""

    def test_load_piano_roll_raw(self, supra_raw_path: Path) -> None:
        """Can load raw piano roll MIDI."""
        if not supra_raw_path.exists():
            pytest.skip("Test data not found")

        loader = PerformanceMidiLoader()
        loader.load(supra_raw_path)

        assert len(loader) == 30096  # supra_raw.mid has 30096 total events
        assert loader.ticks_per_beat is not None

        # Check metadata
        meta = loader.metadata["sources"][0]
        assert meta["format"] == "midi"
        assert meta["parser"] == "mido"

        # Check events
        types = loader.count_events_by_type()
        assert MidiEventType.NOTE in types
        # Piano roll: 30092 notes + 4 control changes = 30096 total
        assert types[MidiEventType.NOTE] == 30092

    def test_load_chopin_performance(self, chopin_perf_path: Path) -> None:
        """Can load expressive performance MIDI."""
        if not chopin_perf_path.exists():
            pytest.skip("Test data not found")

        loader = PerformanceMidiLoader(include_controls=True)
        loader.load(chopin_perf_path)

        assert len(loader) > 0

        # Should have notes and control changes (pedal)
        types = loader.count_events_by_type()
        assert MidiEventType.NOTE in types

    def test_note_pairing(self, tmp_path: Path) -> None:
        """Loader correctly pairs note_on and note_off."""
        # Create a simple MIDI file
        import mido

        mid = mido.MidiFile(type=0)
        track = mido.MidiTrack()
        mid.tracks.append(track)

        # Note C4, vel 100, duration 480 ticks
        track.append(mido.Message("note_on", note=60, velocity=100, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0, time=480))

        midi_path = tmp_path / "test.mid"
        mid.save(midi_path)

        loader = PerformanceMidiLoader()
        loader.load(midi_path)

        assert len(loader) == 1
        event = loader.events.to_dataframe().iloc[0]

        assert event["event_type"] == MidiEventType.NOTE
        assert event["pitch"] == 60
        assert event["duration"] == 480

    def test_performance_emits_narrow_schema(self, tmp_path: Path) -> None:
        """Performance MIDI emits the narrower 7-extra-column schema.

        ``ScoreMidiEventData``-only columns (``voice``, ``staff``,
        ``part_id``) must NOT appear on the performance-MIDI store —
        partitura is the only loader that can populate them.
        """
        import mido

        mid = mido.MidiFile(type=0)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message("note_on", note=60, velocity=100, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0, time=480))
        track.append(mido.Message("control_change", control=64, value=127, time=0))
        midi_path = tmp_path / "narrow.mid"
        mid.save(midi_path)

        loader = PerformanceMidiLoader(include_controls=True)
        loader.load(midi_path)

        # The concrete EventData class is the narrower base, not the
        # wider score-side subclass.
        assert type(loader.events) is MidiEventData
        assert not isinstance(loader.events, ScoreMidiEventData)

        columns = set(loader.events.table.column_names)
        for required in (
            "pitch",
            "velocity",
            "channel",
            "track",
            "control",
            "value",
            "program",
        ):
            assert required in columns, f"missing {required} column"
        for forbidden in ("voice", "staff", "part_id"):
            assert forbidden not in columns, f"unexpected {forbidden} column"
