"""Harmonization tests for MIDI loaders.

Validates that PerformanceMidiLoader (mido) and ScoreMidiLoader (partitura)
produce identical Note events from the same MIDI file. Both loaders parse raw
MIDI messages, so note counts, durations, and pitches must match exactly.

Gold standard values (verified empirically 2025-02-25):
- supra_raw.mid: 30092 notes, max end coordinate 277776.0 ticks
- Chopin_op10_no3_p01.mid: 451 notes, identical pitch histograms
"""

from pathlib import Path

import pytest

from timetoalign.loader.midi import (
    MidiEventType,
    PerformanceMidiLoader,
    ScoreMidiLoader,
)

# Exact gold standard values
SUPRA_RAW_NOTE_COUNT = 30092
SUPRA_RAW_END_TICKS = 277776.0
CHOPIN_NOTE_COUNT = 451
CHOPIN_MAX_PITCH = 59
CHOPIN_MAX_PITCH_COUNT = 50


class TestMidiHarmonization:
    """Compare PerformanceMidiLoader and ScoreMidiLoader on the same file.

    Both loaders must produce identical Note events. Any discrepancy indicates
    a parsing bug, not a "loader difference" to be tolerated.
    """

    @pytest.mark.slow
    def test_compare_supra_raw(self, supra_raw_path: Path) -> None:
        """Compare parsing of raw piano roll data.

        supra_raw.mid contains 30092 Note events with max end at 277776.0 ticks.
        Both loaders must produce identical counts and durations.
        """
        if not supra_raw_path.exists():
            pytest.skip("Test data not found")

        mido_loader = PerformanceMidiLoader()
        mido_loader.load(supra_raw_path)

        part_loader = ScoreMidiLoader()
        part_loader.load(supra_raw_path)

        mido_notes = [
            e for e in mido_loader.events if e["event_type"] == MidiEventType.NOTE
        ]
        part_notes = [
            e for e in part_loader.events if e["event_type"] == MidiEventType.NOTE
        ]

        # Both loaders must produce exactly 30092 notes
        assert (
            len(mido_notes) == SUPRA_RAW_NOTE_COUNT
        ), f"mido note count: {len(mido_notes)}, expected {SUPRA_RAW_NOTE_COUNT}"
        assert (
            len(part_notes) == SUPRA_RAW_NOTE_COUNT
        ), f"partitura note count: {len(part_notes)}, expected {SUPRA_RAW_NOTE_COUNT}"

        # Max end coordinates must match exactly (both in ticks, same source file)
        mido_end = max(e["end"]["value"] for e in mido_notes)
        part_end = max(e["end"]["value"] for e in part_notes)

        assert (
            mido_end == SUPRA_RAW_END_TICKS
        ), f"mido max end: {mido_end}, expected {SUPRA_RAW_END_TICKS}"
        assert (
            part_end == SUPRA_RAW_END_TICKS
        ), f"partitura max end: {part_end}, expected {SUPRA_RAW_END_TICKS}"

    def test_compare_chopin_performance(self, chopin_perf_path: Path) -> None:
        """Compare parsing of expressive performance.

        Chopin_op10_no3_p01.mid contains 451 Note events. Both loaders must
        produce identical note counts and pitch histograms.
        """
        if not chopin_perf_path.exists():
            pytest.skip("Test data not found")

        mido_loader = PerformanceMidiLoader()
        mido_loader.load(chopin_perf_path)

        part_loader = ScoreMidiLoader()
        part_loader.load(chopin_perf_path)

        mido_notes = [
            e for e in mido_loader.events if e["event_type"] == MidiEventType.NOTE
        ]
        part_notes = [
            e for e in part_loader.events if e["event_type"] == MidiEventType.NOTE
        ]

        # Both loaders must produce exactly 451 notes
        assert (
            len(mido_notes) == CHOPIN_NOTE_COUNT
        ), f"mido note count: {len(mido_notes)}, expected {CHOPIN_NOTE_COUNT}"
        assert (
            len(part_notes) == CHOPIN_NOTE_COUNT
        ), f"partitura note count: {len(part_notes)}, expected {CHOPIN_NOTE_COUNT}"

        # Pitch histograms must be identical
        mido_pitches: dict[int, int] = {}
        for n in mido_notes:
            p = n["pitch"]
            mido_pitches[p] = mido_pitches.get(p, 0) + 1

        part_pitches: dict[int, int] = {}
        for n in part_notes:
            p = n["pitch"]
            part_pitches[p] = part_pitches.get(p, 0) + 1

        assert mido_pitches == part_pitches, "Pitch histograms differ between loaders"

        # Verify gold standard for most frequent pitch
        max_p = max(mido_pitches, key=mido_pitches.get)  # type: ignore[arg-type]
        assert (
            max_p == CHOPIN_MAX_PITCH
        ), f"Most frequent pitch: {max_p}, expected {CHOPIN_MAX_PITCH}"
        assert (
            mido_pitches[max_p] == CHOPIN_MAX_PITCH_COUNT
        ), f"Max pitch count: {mido_pitches[max_p]}, expected {CHOPIN_MAX_PITCH_COUNT}"
