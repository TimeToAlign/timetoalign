# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module.

## Architecture

All score loaders return a `ScoreStore` containing category-specific data:
- `NoteEventData`: Notes, rests, chords
- `MeasureEventData`: Measure boundaries
- `ControlEventData`: Dynamics, tempo, signatures
- `AnnotationEventData`: Text annotations

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
- `test_partitura_loader_store`: Verify ScoreStore structure
- `test_music21_loader_store`: Verify ScoreStore structure
- `test_tsv_loader_store`: Verify ScoreStore structure
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

---

## MeasureMapLoader Tests (Phase 1 Complete)

### `test_measuremap_loader.py`

Tests for the `MeasureMapLoader` implementation (Phase 1 of Measure Handling Design).

**Purpose**: Validates MeasureMapLoader which parses MeasureMap JSON files and returns
`ScoreStore` with populated `MeasureEventData`.

### Test Categories

| Class | Description | Tests |
|-------|-------------|-------|
| `TestMeasureMapLoaderBasic` | Basic loader functionality | Import, init, load specimen |
| `TestMeasureMapExpansion` | Compression/expansion logic | Minimal, anacrusis, repeats |
| `TestMeasureMapValidation` | Validation rules | MC unique, qstamp monotonic, next valid |
| `TestMeasureMapTraversal` | Traversal computation | Simple, repeat, unfolded count |
| `TestMeasureMapCrossValidation` | Cross-loader validation | Count match, MC match, flow control |
| `TestMeasureEventDataSchema` | Schema validation | Flow control fields, identity fields |
| `TestFlowControlSpecimen` | Complex flow control | Load flow_control specimen |

### Gold Standard Specimens

| File | Location | Description | Count |
|------|----------|-------------|-------|
| `WoO71.measures.mm.json` | `beethoven_woo71/` | Folded MeasureMap | 397 MCs |
| `WoO71.measures.tsv` | `beethoven_woo71/` | Folded TSV (ms3) | 397 rows |
| `WoO71_unfolded.measures.tsv` | `beethoven_woo71/` | Unfolded traversal | 505 rows |
| `*.mm.json` | `flow_control/flow_only/` | Complex flow control | Variable |

### Validation Policy

Per the **ZERO TOLERANCE VALIDATION POLICY** (AGENTS.md):
- EXACT counts required (no tolerances)
- Every mismatch must be investigated
- Gold standard is authoritative
- Loader parity is required

### Running MeasureMapLoader Tests

```bash
# Run all MeasureMapLoader tests
pytest tests/loader/score/test_measuremap_loader.py -v

# Run specific test class
pytest tests/loader/score/test_measuremap_loader.py::TestMeasureMapCrossValidation -v

# Run with coverage
pytest tests/loader/score/test_measuremap_loader.py --cov=timetoalign.loader.score
```

### Implementation Status

| Component | Status | Validated Against |
|-----------|--------|-------------------|
| JSON parsing & expansion | Complete | Beethoven WoO71 (397 MCs) |
| Validation (MC/qstamp/next) | Complete | Unit tests |
| Traversal computation | Complete | Unfolded TSV (505 measures) |
| TSVLoader._load_measures() | Complete | Cross-validation |
| MeasureEventData schema | Complete | Schema tests |

### MeasureEventData Fields

| Category | Fields |
|----------|--------|
| Identity | `mc`, `mn`, `mn_int`, `mm_id` |
| Temporal | `nominal_length`, `actual_length`, `mc_offset`, `quarterbeats_all_endings` |
| Flow Control | `start_repeat`, `end_repeat`, `next`, `volta`, `breaks`, `repeats`, `dont_count` |
| Signatures | `timesig`, `keysig`, `timesig_num`, `timesig_den`, `keysig_fifths` |
