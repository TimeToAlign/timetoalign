"""Harmonization tests for MIDI loaders."""

from pathlib import Path

import pytest

from timetoalign.loader.midi import (
    MidiEventType,
    PerformanceMidiLoader,
    ScoreMidiLoader,
)


class TestMidiHarmonization:
    """Compare PerformanceMidiLoader and ScoreMidiLoader on the same file."""

    def test_compare_supra_raw(self, supra_raw_path: Path) -> None:
        """Compare parsing of raw piano roll data."""
        if not supra_raw_path.exists():
            pytest.skip("Test data not found")

        # Load with both
        mido_loader = PerformanceMidiLoader()
        mido_loader.load(supra_raw_path)

        # Use simple mode for partitura to avoid heavy quantization overhead if possible
        # but ScoreMidiLoader defaults to quantized loading.
        part_loader = ScoreMidiLoader()
        part_loader.load(supra_raw_path)

        # Get Note events only
        mido_notes = [
            e for e in mido_loader.events if e["event_type"] == MidiEventType.NOTE
        ]
        part_notes = [
            e for e in part_loader.events if e["event_type"] == MidiEventType.NOTE
        ]

        # Counts should be very close (within <0.5% difference)
        # Difference comes from handling of zero-length notes or overlaps
        diff = abs(len(mido_notes) - len(part_notes))
        assert (
            diff < len(mido_notes) * 0.005
        ), f"Event count mismatch: mido={len(mido_notes)}, partitura={len(part_notes)}"

        # Check total duration (approximate)
        # Note: 'end' is a Coordinate struct {'value': ..., 'unit': ...}
        mido_end = max(e["end"]["value"] for e in mido_notes)
        part_end = max(e["end"]["value"] for e in part_notes)

        # Should be identical in ticks
        assert (
            abs(mido_end - part_end) < 100
        ), f"Total duration mismatch: mido={mido_end}, partitura={part_end}"

    def test_compare_chopin_performance(self, chopin_perf_path: Path) -> None:
        """Compare parsing of expressive performance."""
        if not chopin_perf_path.exists():
            pytest.skip("Test data not found")

        mido_loader = PerformanceMidiLoader()
        mido_loader.load(chopin_perf_path)

        part_loader = ScoreMidiLoader()
        part_loader.load(chopin_perf_path)

        # Mido captures controls, Partitura (ScoreLoader) treats file as score
        # so it might ignore CCs but capture notes.

        mido_notes = [
            e for e in mido_loader.events if e["event_type"] == MidiEventType.NOTE
        ]
        part_notes = [
            e for e in part_loader.events if e["event_type"] == MidiEventType.NOTE
        ]

        # Compare pitch histograms
        mido_pitches = {}
        for n in mido_notes:
            p = n["pitch"]
            mido_pitches[p] = mido_pitches.get(p, 0) + 1

        part_pitches = {}
        for n in part_notes:
            p = n["pitch"]
            part_pitches[p] = part_pitches.get(p, 0) + 1

        # Verify most frequent pitch count matches
        # Find max frequency pitch in mido
        max_p = max(mido_pitches, key=mido_pitches.get)
        assert abs(mido_pitches[max_p] - part_pitches.get(max_p, 0)) < 5
