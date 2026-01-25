"""Debug script to identify specific mismatches between mido and partitura."""

from collections import Counter
from pathlib import Path

from timetoalign.loader.midi import (
    MidiEventType,
    PerformanceMidiLoader,
    ScoreMidiLoader,
)

DATA_DIR = Path(__file__).parents[2] / "data" / "midi"


def debug_mismatch():
    supra_raw_path = DATA_DIR / "performance" / "supra_raw.mid"
    print(f"Analyzing {supra_raw_path}...")

    # Load with both
    mido_loader = PerformanceMidiLoader()
    mido_loader.load(supra_raw_path)

    # Use Score loader (partitura)
    part_loader = ScoreMidiLoader()
    part_loader.load(supra_raw_path)

    # Get all events
    print(f"Mido total events: {len(mido_loader)}")
    print(f"Partitura total events: {len(part_loader)}")

    # Get Note events
    mido_notes = [
        e for e in mido_loader.events if e["event_type"] == MidiEventType.NOTE
    ]
    part_notes = [
        e for e in part_loader.events if e["event_type"] == MidiEventType.NOTE
    ]

    mido_others = [
        e for e in mido_loader.events if e["event_type"] != MidiEventType.NOTE
    ]
    part_others = [
        e for e in part_loader.events if e["event_type"] != MidiEventType.NOTE
    ]

    print(f"Mido notes: {len(mido_notes)}")
    print(f"Partitura notes: {len(part_notes)}")
    print(f"Mido non-notes: {len(mido_others)}")
    print(f"Partitura non-notes: {len(part_others)}")

    if len(mido_others) > 0:
        print("Mido non-note types:", Counter(e["event_type"] for e in mido_others))

    # Create signatures for comparison: (pitch, start, duration)
    # We round to avoid floating point noise if any, though ticks should be ints
    mido_sigs = Counter()
    for n in mido_notes:
        sig = (n["pitch"], int(n["start"]["value"]), int(n["duration"]["value"]))
        mido_sigs[sig] += 1

    part_sigs = Counter()
    for n in part_notes:
        sig = (n["pitch"], int(n["start"]["value"]), int(n["duration"]["value"]))
        part_sigs[sig] += 1

    # Find differences
    only_in_mido = mido_sigs - part_sigs
    only_in_part = part_sigs - mido_sigs

    print("\n--- Mismatch Analysis ---")
    if not only_in_mido and not only_in_part:
        print("PERFECT MATCH! No differences found.")
        return

    print(f"Notes only in Mido ({sum(only_in_mido.values())}):")
    for sig, count in only_in_mido.items():
        print(f"  {sig} x{count}")

    print(f"Notes only in Partitura ({sum(only_in_part.values())}):")
    for sig, count in only_in_part.items():
        print(f"  {sig} x{count}")


if __name__ == "__main__":
    debug_mismatch()
