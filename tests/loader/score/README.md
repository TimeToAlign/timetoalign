# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module.

## Architecture

All score loaders return a `ScoreStore` containing category-specific data:
- `NoteEventData`: Notes, rests, chords
- `MeasureData`: Measure boundaries
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
`ScoreStore` with populated `MeasureData`.

### Test Categories

| Class | Description | Tests |
|-------|-------------|-------|
| `TestMeasureMapLoaderBasic` | Basic loader functionality | Import, init, load specimen |
| `TestMeasureMapExpansion` | Compression/expansion logic | Minimal, anacrusis, repeats |
| `TestMeasureMapValidation` | Validation rules | MC unique, qstamp monotonic, next valid |
| `TestMeasureMapTraversal` | Traversal computation | Simple, repeat, unfolded count |
| `TestMeasureMapCrossValidation` | Cross-loader validation | Count match, MC match, flow control |
| `TestMeasureDataSchema` | Schema validation | Flow control fields, identity fields |
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
| MeasureData schema | Complete | Schema tests |

### MeasureData Fields

| Category | Fields |
|----------|--------|
| Identity | `mc`, `mn`, `mn_int`, `mm_id` |
| Temporal | `nominal_length`, `actual_length`, `mc_offset`, `quarterbeats_all_endings` |
| Flow Control | `start_repeat`, `end_repeat`, `next`, `volta`, `breaks`, `repeats`, `dont_count` |
| Signatures | `timesig`, `keysig`, `timesig_num`, `timesig_den`, `keysig_fifths` |

---

## Flow Control Parity Tests (Phase 3.6 Complete)

### `test_flow_control_parity.py`

Cross-validation tests ensuring all score loaders extract flow control information consistently.

**Purpose**: Validates that TSVLoader, MeasureMapLoader, PartituraLoader, and Music21Loader
all extract repeat markers, volta information, and other flow control data correctly.

### Test Architecture

The test suite uses two specimen sets:

| Specimen | Location | MusicXML? | Purpose |
|----------|----------|-----------|---------|
| Beethoven WoO71 | `beethoven_woo71/` | No | TSV/MeasureMap validation (complex repeats) |
| Flow Control | `flow_control/flow_only/` | Yes | All 4 loaders including Partitura/Music21 |

### Test Classes

| Class | Description | Tests |
|-------|-------------|-------|
| `TestGoldStandardVerification` | Verify TSV gold standard values | 6 |
| `TestMeasureMapLoaderParity` | MeasureMap matches TSV | 4 |
| `TestPartituraLoaderParity` | Partitura on WoO71 (skipped - no MusicXML) | 2 |
| `TestMusic21LoaderParity` | Music21 on WoO71 (skipped - no MusicXML) | 3 |
| `TestCrossLoaderConsistency` | Compare TSV vs MeasureMap | 2 |
| `TestDiagnosticOutput` | Print comparison table | 1 |
| `TestFlowControlTSVGold` | Verify flow_control TSV gold | 3 |
| `TestFlowControlPartitura` | Partitura on flow_control specimen | 4 |
| `TestFlowControlMusic21` | Music21 on flow_control specimen | 4 |
| `TestFlowControlCrossLoader` | Cross-loader parity on flow_control | 4 |
| `TestFlowControlDiagnostic` | Print all 4 loaders comparison | 1 |

### Gold Standard Values

#### Beethoven WoO71 (TSV)
```python
{
    "total_measures": 397,
    "repeat_starts": 11,
    "repeat_ends": 11,
    "section_breaks": 12,
    "double_barlines": 4,
    "volta_1_count": 1,
    "volta_2_count": 1,
}
```

#### Flow Control Specimen (TSV)
```python
{
    "total_measures": 15,
    "repeat_starts": 3,   # 2 "start" + 1 "startend"
    "repeat_ends": 6,     # 5 "end" + 1 "startend"
    "volta_1_count": 2,
    "volta_2_count": 2,
    "volta_3_count": 1,
}
```

### Loader Model Classification

The test suite distinguishes between two repeat extraction models:

| Model | Loaders | Behavior |
|-------|---------|----------|
| **Marker** | TSV, MeasureMap, Music21 | Reports barline markers as individual events |
| **Region** | Partitura | Infers missing start/end to create complete regions |

**Marker-based loaders** produce identical counts and are validated together.
**Partitura** is tested separately with adjusted expectations.

### Known Discrepancy: Partitura Region Model

Partitura models repeats as **regions** (start/end boundary pairs) rather than **markers**.
When encountering an orphan repeat end without a start, Partitura infers a start point.

For the flow_control specimen:
- **TSV gold**: 3 starts, 6 ends (marker model)
- **Partitura**: 7 starts, 7 ends (region model with inferred boundaries)

This is **expected behavior** and documented in:
1. Test docstrings
2. `TestFlowControlPartitura` class docstring
3. This README

### Validation Logic

Per the **ZERO TOLERANCE VALIDATION POLICY** (AGENTS.md):

1. **EXACT COUNTS REQUIRED**: All assertions use exact expected values
   ```python
   # CORRECT
   assert actual == 3, f"Repeat starts: got {actual}, expected 3"

   # WRONG - Never use ranges or minimums
   assert actual >= 3  # FORBIDDEN
   ```

2. **GOLD STANDARD IS AUTHORITATIVE**: TSV (ms3) defines correct values

3. **LOADER PARITY REQUIRED**: Marker-based loaders must produce identical counts
   ```python
   starts = {"TSV": 3, "MeasureMap": 3, "Music21": 3}
   assert len(set(starts.values())) == 1  # All must match
   ```

4. **DOCUMENTED DISCREPANCIES**: Known differences (like Partitura's region model)
   are explicitly documented and tested with adjusted expectations

### Running Flow Control Tests

```bash
# Run all flow control parity tests
pytest tests/loader/score/test_flow_control_parity.py -v --no-cov

# Run only the flow_control specimen tests (has MusicXML)
pytest tests/loader/score/test_flow_control_parity.py -k "FlowControl" -v --no-cov

# Run diagnostic output to see all loader values
pytest tests/loader/score/test_flow_control_parity.py::TestFlowControlDiagnostic -v -s --no-cov
```

### Test Results (Feb 2026)

```
tests/loader/score/test_flow_control_parity.py: 29 passed, 5 skipped
```

- **5 skipped**: WoO71 Partitura/Music21 tests (no MusicXML available)
- **29 passed**: All other tests including cross-loader parity

### Implementation Files Modified

| File | Changes |
|------|---------|
| `partitura.py` | Added flow control extraction from `part.repeats`, `pts.Ending` |
| `music21.py` | Added barline extraction, `RepeatBracket` parsing |
| `test_flow_control_parity.py` | New test suite (34 tests) |

### Future Work

1. **Export MusicXML for WoO71**: Enable Partitura/Music21 testing on primary specimen
2. **Barline type extraction**: Add `barline` field (single, double, final)
3. **Flow marker extraction**: Extract D.S., D.C., Fine, Coda from all loaders
