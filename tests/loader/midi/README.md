# MIDI Loaders: Testing, Validation & Performance

This directory contains the unit tests and validation logic for the MIDI loaders in `timetoalign`. Given the complexity of MIDI as a data format—which can represent both loose, unquantized performances and strict, quantized scores—we employ a rigorous testing strategy to ensure data integrity across different parsing paradigms.

## 1. The Challenge: One Format, Two Paradigms

MIDI files (`.mid`) are used for two fundamentally different types of musical data:

1.  **Performance Data**: A linear stream of timestamped events (Note On/Off, Control Changes). Timing is often in seconds or high-resolution ticks. There is no concept of "measure", "voice", or "staff".
2.  **Score Data**: A structured representation of music. Timing is strictly quantized (beats, measures). Notes belong to specific voices and staves.

To handle this, `timetoalign` provides two specialized loaders that map these distinct paradigms into a unified `MidiEventData` schema.

## 2. Loader Schemata & Fields

Two concrete `EventData` subclasses model the cross-loader vs
loader-specific split, so the storage schema is the minimal set of
columns each loader can populate:

* `MidiEventData` — used by `PerformanceMidiLoader`. Carries the
  seven cross-loader columns: `pitch`, `velocity`, `channel`,
  `track`, `control`, `value`, `program`.
* `ScoreMidiEventData(MidiEventData)` — used by `ScoreMidiLoader`.
  Extends the base with three partitura-only columns: `voice`,
  `staff`, `part_id`.

The previous unified-superset schema (with always-null `voice` /
`staff` / `part_id` columns on every performance-MIDI store) has
been retired — those columns existed only on the score side and
storing them as nulls on performance data was redundant.

| Field | Type | `MidiEventData` | `ScoreMidiEventData` | Source / notes |
| :--- | :--- | :--- | :--- | :--- |
| `start` | Coordinate | yes | yes | Exact tick (mido) / quantized tick (partitura) |
| `duration` | Coordinate | yes | yes | Exact / quantized |
| `pitch` | int8 | yes | yes | MIDI number (0–127) |
| `velocity` | int8 | **measured** | default 64 | Score MIDI rarely carries velocity |
| `channel` | int8 | **source channel** | derived / null | Partitura maps channels to parts |
| `track` | int16 | **source track** | derived / null | |
| `control` | int8 | **captured** | ignored | CC is performance-specific |
| `value` | int8 | **captured** | ignored | CC / Program value |
| `program` | int8 | **captured** | ignored | Program Change |
| `voice` | int8 | *(absent)* | **extracted** | Voice separation |
| `staff` | int8 | *(absent)* | **extracted** | LH / RH assignment |
| `part_id` | string | *(absent)* | **extracted** | Part ID from score structure |

The paired pydantic scalars `MidiEvent` (7 fields) and
`ScoreMidiEvent(MidiEvent)` (+3 fields) live in `core/events.py`;
their derived `pa.Schema` shapes are the two distinct semantic
fingerprints these EventData subclasses round-trip via
`SemanticField` / `EventData.get_field(...)`.

### Pitch is stored as the `EnharmonicPitch` struct

`pitch` is a materialised `{midi_number: int64}` struct — the exact
`EnharmonicPitch` storage shape — decorated with `b"timetoalign"`
metadata advertising `EnharmonicPitchField`. A MIDI pitch *number* carries
no enharmonic spelling, so reading it as an `EnharmonicPitch` (display alias
`MidiPitch`) invents nothing. Because the column is the canonical struct,
both `MidiEventData` and `ScoreMidiEventData` afford
`events.get_field(EnharmonicPitch)` / `events.get_pitch_field()` over the
note number with no per-loader wiring, which is what the
`pitch: EnharmonicPitch | None` annotation on the scalar promises. The MIDI
loaders emit a bare note integer; `MidiEventData.from_dicts` lifts it into
the struct dict before construction. Control Change / Program Change events
carry a null pitch. Validation pins (in `test_store.py` and the loader test
files): the `pitch` column type is `struct<midi_number: int64>`,
`table.column("pitch")[i]["midi_number"]` equals the source note number, and
`events.get_field(EnharmonicPitch)[i].midi_number` round-trips it.

## 3. The Three Parsing Approaches

We evaluated three approaches to parsing MIDI.

### 1. Mido (Stream Parsing)
-   **Implementation**: `PerformanceMidiLoader`
-   **Logic**: Iterates over tracks linearly. Pairs `note_on` with `note_off`.
-   **Pros**: Extremely fast. Preserves all MIDI messages (CC, SysEx). Zero interpretation.
-   **Cons**: No structural analysis (cannot tell voice 1 from voice 2).

### 2. Partitura Performance (Object Parsing)
-   **Implementation**: `partitura.load_performance_midi()` (Raw)
-   **Logic**: Parses MIDI into a `Performance` object with a `note_array`.
-   **Pros**: Good middle ground. Structured note array.
-   **Cons**: Slower than Mido. Less control over raw message stream.

### 3. Partitura Score (Structural Analysis)
-   **Implementation**: `ScoreMidiLoader` (wraps `partitura.load_score_midi`)
-   **Logic**: Performs complex analysis: key estimation, voice separation, quantization, pitch spelling.
-   **Pros**: Extracts rich score structure (`voice`, `staff`, `part`).
-   **Cons**: Very slow (expensive analysis). Inappropriate for raw performance data.

## 4. Performance Profiling

We benchmarked these approaches on `supra_raw.mid` (238 KB, ~30k events), a raw piano roll scan.

| Approach | Implementation | Speed | Relative Speed | Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Mido** | `PerformanceMidiLoader` | **~15,700 events/sec** | **1.0x (Baseline)** | **High-volume Performance Data** |
| **Partitura Perf** | `load_performance_midi` | ~12,400 notes/sec | 0.8x | Structured Performance Analysis |
| **Partitura Score** | `ScoreMidiLoader` | ~2,000 events/sec | 0.13x | **Score / OMR Data Only** |

**Recommendation**: Use `PerformanceMidiLoader` for large performance datasets (1.25x faster than Partitura Perf, 8x faster than Partitura Score). Use `ScoreMidiLoader` strictly for score data where the overhead yields valuable structural info.

## 5. Equivalence Validation (Harmonization)

To verify correctness, we run **Harmonization Tests** (`test_harmonization.py`) that parse the exact same file using both `PerformanceMidiLoader` and `ScoreMidiLoader`.

### Validation Logic
We assert that:
1.  **Note Counts Match**: The number of identified note events must be identical (exact match required; both loaders produce exactly 30,092 notes).
2.  **Durations Match**: The total duration of the track must match.
3.  **Pitch Content Matches**: The frequency distribution of pitches must be identical.

### Verified Mismatch: Control Changes
On `supra_raw.mid`, we observed a difference of exactly 4 events:
-   Mido: 30,096 events.
-   Partitura: 30,092 events.
-   **Explanation**: The file contains 4 `ControlChange` messages. Mido captures them; Partitura (in score mode) ignores them. The 30,092 **Note** events match exactly.

**Status**: VALIDATED. The loaders produce musically equivalent note data.

## 6. Test Status

**All MIDI-loader tests passing under the split schema.**

### Bug Fix History

| Date | Issue | Root Cause | Fix |
|------|-------|------------|-----|
| Feb 2026 | `KeyError: 'pitch'` in all MIDI tests | `MidiLoader` used wrong class attribute name (`_event_store_class` instead of `_event_data_class`), causing base `EventData` schema to be used instead of `MidiEventData` | Renamed attribute in `loader/midi/base.py:26` |

### Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `test_performance.py` | 4 | `PerformanceMidiLoader` (mido parsing); pins the narrower 7-extra-column schema |
| `test_score.py` | 3 | `ScoreMidiLoader` (partitura parsing); pins the wider 10-extra-column schema |
| `test_harmonization.py` | 2 | Cross-loader Note-count validation |
| `test_store.py` | 7 | `MidiEventData` + `ScoreMidiEventData` schema contracts |
| `test_bundle.py` | 23 | `MidiStore` operations (filter / merge / canonical iteration) |

Scalar-side coverage for `MidiEvent` / `ScoreMidiEvent` lives at
`tests/core/test_midi_event.py` (16 tests) — pydantic construction,
`derive_arrow_schema` shape, and the column-builder → `from_field`
round-trip for both scalars.
