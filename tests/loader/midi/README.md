# MIDI Loaders: Testing, Validation & Performance

This directory contains the unit tests and validation logic for the MIDI loaders in `timetoalign`. Given the complexity of MIDI as a data format—which can represent both loose, unquantized performances and strict, quantized scores—we employ a rigorous testing strategy to ensure data integrity across different parsing paradigms.

## 1. The Challenge: One Format, Two Paradigms

MIDI files (`.mid`) are used for two fundamentally different types of musical data:

1.  **Performance Data**: A linear stream of timestamped events (Note On/Off, Control Changes). Timing is often in seconds or high-resolution ticks. There is no concept of "measure", "voice", or "staff".
2.  **Score Data**: A structured representation of music. Timing is strictly quantized (beats, measures). Notes belong to specific voices and staves.

To handle this, `timetoalign` provides two specialized loaders that map these distinct paradigms into a unified `MidiEventStore` schema.

## 2. Loader Schemata & Fields

The `MidiEventStore` uses a superset schema. Each loader populates a subset of fields appropriate for its paradigm.

| Field | Type | `PerformanceMidiLoader` (mido) | `ScoreMidiLoader` (partitura) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `start` | Coordinate | Exact Tick | Quantized Tick (Div) | |
| `duration` | Coordinate | Exact Duration | Quantized Duration | |
| `pitch` | int8 | MIDI Number (0-127) | MIDI Number (0-127) | Partitura also has spelling, but we store MIDI pitch. |
| `velocity` | int8 | **Measured Velocity** | *Default (64)* | Score MIDI rarely contains meaningful velocity. |
| `channel` | int8 | **Source Channel** | *Derived/Null* | Partitura maps channels to parts. |
| `track` | int16 | **Source Track** | *Derived/Null* | |
| `control` | int8 | **Captured** | *Ignored* | CC messages are performance-specific. |
| `voice` | int8 | *Null* | **Extracted** | Voice separation (polyphony analysis). |
| `staff` | int8 | *Null* | **Extracted** | Staff assignment (LH/RH). |
| `part_id` | string | *Null* | **Extracted** | Part ID from score structure. |

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
1.  **Note Counts Match**: The number of identified note events must be identical (within <0.5% tolerance for edge cases).
2.  **Durations Match**: The total duration of the track must match.
3.  **Pitch Content Matches**: The frequency distribution of pitches must be identical.

### Verified Mismatch: Control Changes
On `supra_raw.mid`, we observed a difference of exactly 4 events:
-   Mido: 30,096 events.
-   Partitura: 30,092 events.
-   **Explanation**: The file contains 4 `ControlChange` messages. Mido captures them; Partitura (in score mode) ignores them. The 30,092 **Note** events match exactly.

**Status**: VALIDATED. The loaders produce musically equivalent note data.
