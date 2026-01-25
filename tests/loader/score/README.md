# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module.

## Architecture

All score loaders return a `ScoreBundle` containing category-specific stores:
- `NoteEventStore`: Notes, rests, chords
- `MeasureEventStore`: Measure boundaries
- `ControlEventStore`: Dynamics, tempo, signatures
- `AnnotationEventStore`: Text annotations

## Testing Strategy

### Cross-Validation
We load *Chopin Op. 10 No. 3* using three loaders and verify consistency:

| Loader | Source | Notes | Measures | Controls |
|--------|--------|-------|----------|----------|
| TSVLoader | TSV (ms3) | 498 | - | - |
| PartituraLoader | MusicXML | 498 | 22 | 27 |
| Music21Loader | MusicXML | 498+12 rests | 22 | 11 |

### Validation Checks
1. **Note Count Consistency**: All loaders return 498 Notes (rests tracked separately)
2. **Temporal Schema**: `quarterbeats` stored as Fraction structs `{num, den}`
3. **Pitch Schema**: `midi_pitch` and `spelled_pitch` fully populated
4. **Measure Context**: `mc`, `mn`, `mc_onset` correctly computed

## Test Files

### `test_loaders.py`
Unit tests for each loader:
- `test_partitura_loader_bundle`: Verify ScoreBundle structure
- `test_music21_loader_bundle`: Verify ScoreBundle structure
- `test_tsv_loader_bundle`: Verify ScoreBundle structure
- `test_cross_validation_notes`: Compare note counts across loaders
- `test_fraction_preservation`: Verify Fraction structs round-trip

### `verify_strict.py`
Strict field-by-field comparison between loaders:
- Compares `start`, `duration`, `midi_pitch`, `mc` for exact match
- Uses TSV as gold standard
- Reports any discrepancies

### `profile.py`
Timing benchmarks for each loader (n=5 runs average).

## Profiling Results

Benchmarks on *Chopin Op. 10 No. 3*:

| Loader | Format | Time (avg) | Notes |
|--------|--------|------------|-------|
| TSVLoader | TSV (ms3) | ~150 ms | Fastest. Direct load. |
| Music21Loader | MusicXML | ~400 ms | Medium. Object overhead. |
| PartituraLoader | MusicXML | ~700 ms | Slowest. Detailed analysis. |

## Running Tests
```bash
pytest tests/loader/score/test_loaders.py -v
```

## Running Profiler
```bash
python tests/loader/score/profile.py
```

## Running Strict Verification
```bash
python tests/loader/score/verify_strict.py
```

## Test Data

Located in `tests/data/midi/score/`:
- `chopin_op10_no3.musicxml`: MusicXML source
- `ms3/chopin_op10_no3.notes.tsv`: Gold standard notes (ms3 format)
- `ms3/chopin_op10_no3.measures.tsv`: Measure info
