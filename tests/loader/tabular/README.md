# Tabular Loader Tests

This directory contains comprehensive tests for the `timetoalign.loader.tabular` subpackage, validating the **vectorized** loading pipeline.

## Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `test_tabular.py` | 11 | Core TabularLoader, CsvLoader, TsvLoader functionality |
| `test_vectorized.py` | 10 | Vectorized pipeline integration tests |
| `test_correctness.py` | 11 | ZERO TOLERANCE validation with real specimens |
| `test_error_handling.py` | 15 | Graceful degradation and error message clarity |
| `test_struct_columns.py` | 16 | `Field`, `ComputedField`, `ConvertedField` unit tests and JSON-to-struct parsing helper |
| `test_table_schema.py` | 25 | TableSchema system for semantic column specifications |
| `test_solo_loader.py` | `SoloLoader` round-trip against the Chopin Nocturne ``.solo`` specimen — see §SoloLoader below |
| `profile_vectorized.py` | - | Performance profiling script (not a test file) |

---

## Test Specimens

### Source/Provenance

Tests use specimens from `tests/data/score/` which are **gold standard** files from established music datasets:

| Specimen | Source | Format | Events | Description |
|----------|--------|--------|--------|-------------|
| `beethoven_woo71/WoO71.notes.tsv` | ms3 parser | ms3 TSV | 4,753 | Beethoven WoO 71 piano piece, all notes |
| `beethoven_woo71/WoO71.measures.tsv` | ms3 parser | ms3 TSV | 397 | Measure annotations for WoO 71 |
| `rachmaninoff_concerto2/.../notes.tsv` | ms3 parser | ms3 TSV | 14,315 | Rachmaninoff Piano Concerto No. 2, 1st mvt |
| `beethoven_woo71/original_file_before_cleaning.notes.tsv` | ms3 parser | ms3 TSV | 4,750 | Original uncleaned version |

### ms3 TSV Format

The ms3 (MuseScore 3) parser produces TSV files with the following columns:

```
mc  mn  quarterbeats  quarterbeats_all_endings  duration_qb  volta  mc_onset  mn_onset  timesig  staff  voice  duration  gracenote  nominal_duration  scalar  tied  tpc  midi  name  octave  chord_id
```

**Key columns for TabularLoader:**
- `quarterbeats`: Start coordinate as fraction strings ("0", "1/2", "3/4")
- `duration_qb`: Duration in quarter beats (float)
- `name`: Note name ("A4", "C#5", etc.)
- `midi`: MIDI note number (integer)

### Generated Test Data

Some tests use **dynamically generated temporary files** for isolation:

| Fixture | Format | Columns | Purpose |
|---------|--------|---------|---------|
| `csv_file` | CSV | id, start, end, event_type, name | Basic CSV with mixed instant/interval events |
| `tsv_file` | TSV | id, start, end, event_type, name | Same structure, tab-delimited |
| `minimal_csv` | CSV | start | Minimal file with only required column |

All generated test files use pytest's `tmp_path` fixture for automatic cleanup.
No manual `os.unlink()` or `tempfile.NamedTemporaryFile(delete=False)` patterns remain.

---

## Validation Logic

### How We Know the Parser is Correct

1. **EXACT COUNT VALIDATION**: Event counts are validated against the source file line counts minus header. For example:
   - `WoO71.notes.tsv` has 4,754 lines -> 4,753 events (EXACT)
   - `WoO71.measures.tsv` has 398 lines -> 397 events (EXACT)

2. **COORDINATE RANGE VALIDATION**: Start/end coordinates are validated against known musical structure:
   - First note starts at quarterbeat 0 (EXACT)
   - Coordinate range matches the piece length in quarter beats

3. **FRACTION ROUND-TRIP**: For fraction coordinates, we verify:
   ```python
   Fraction(numerator, denominator) == value  # Within float precision
   ```

4. **TEMPORAL TYPE INFERENCE**:
   - Events with valid `duration_qb` -> "interval"
   - Events with null `duration_qb` or null `quarterbeats` -> "instant"
   - Validated: all 4,753 events are intervals (EXACT, per `test_correctness.py` line 259)

5. **ZERO ITERATION GUARANTEE**: Validated via monkey-patching:
   ```python
   pd.DataFrame.__iter__ = lambda self: raise AssertionError("ITERATION DETECTED!")
   ```

### ZERO TOLERANCE Validation Policy

Per the ZERO TOLERANCE validation policy, all tests use **EXACT** assertions:

```python
# CORRECT
assert len(loader.events) == 4753  # Exact count from gold standard

# WRONG - FORBIDDEN
assert len(loader.events) >= 4000  # Approximate count
assert len(loader.events) > 0      # "At least some events"
```

---

## Performance Benchmarks

### Profiling Results (2026-01-31)

| Specimen | Events | Load Time | Throughput | Zero-Iter |
|----------|--------|-----------|------------|-----------|
| WoO71.notes.tsv | 4,753 | 0.029s | 166,074/s | PASS |
| WoO71.measures.tsv | 397 | 0.008s | 49,966/s | PASS |
| Rachmaninoff.notes.tsv | 14,315 | 0.077s | 185,830/s | PASS |
| original_file_before_cleaning.notes.tsv | 4,750 | 0.029s | 161,816/s | PASS |

**Summary:**
- **Average throughput:** 140,921 events/sec
- **Target (20,000 events/sec):** ACHIEVED (7x over target)
- **Zero iteration:** ALL PASS

### Running the Profiler

```bash
cd timetoalign
python -m tests.loader.tabular.profile_vectorized
```

**Note:** The profiler loads specimens from `tests/data/score/` (same as the test suite).

See `PROFILING_REPORT.md` for full details.

---

## Known Limitations

### Ms3Loader

1. **Null start coordinates raise error**: If `quarterbeats` column contains empty values, the fraction parser raises `ValueError`. This is intentional - null start coordinates are invalid for note events.

2. **Sibling-file variants silently skip missing columns**: `column_specs` lookups against the source DataFrame return `None` when a named column is absent (a measures.tsv lacks the `staff` / `voice` / `chord_id` columns that notes.tsv carries).  Positional specs (integer source keys) are NOT skipped — a missing positional index is a hard `IndexError`.

3. **Fraction parsing requires specific format**: Accepts "num/den" strings or pure integers ("0", "1", "42"). Does NOT accept:
   - Decimal strings ("0.5")
   - Multiple slashes ("1/2/3")
   - Non-numeric strings ("invalid")

### CsvLoader / TsvLoader

1. **Delimiter must match file format**: Using CsvLoader on a TSV file (or vice versa) will fail with "column not found" error because the entire line becomes a single column.

2. **Empty files return empty EventData**: Loading a header-only file succeeds with 0 events (does not raise error).

---

## Discrepancies Between Loaders

### Ms3Loader vs Generic TsvLoader

| Aspect | Ms3Loader | TsvLoader |
|--------|-----------|-----------|
| Start column | `quarterbeats` | `start` |
| End column | Computed from `duration_qb` | `end` |
| Coordinate type | `NumberType.fraction` | `NumberType.float` |
| Time unit | `TimeUnit.quarters` | `TimeUnit.seconds` |
| Default event type | `"Note"` | `"Event"` |

**Important:** Do NOT use generic `TsvLoader` for ms3 files - use `Ms3Loader` which has the correct column mappings and coordinate parsing.

### Null Handling

| Scenario | Behavior |
|----------|----------|
| Null `quarterbeats` (start) | Raises `ValueError` (fraction parser cannot handle NaN) |
| Null `duration_qb` (duration) | Event becomes "instant" (no end coordinate) |
| Null `end` column | Event becomes "instant" |

---

## Test Coverage Requirements

Each loader class requires **15+ tests** covering:

1. **Unit Tests (5+):** Happy path, empty input, single element, nulls, invalid format
2. **Integration Tests (3+):** Real specimen loading with EXACT counts
3. **Performance Tests (2+):** Small and large file benchmarks
4. **Error Handling Tests (3+):** Missing columns, malformed data, type mismatches
5. **Edge Case Tests (2+):** Mixed coordinate types, temporal type inference

Current coverage for `TabularLoader` family: **47 tests** (exceeds requirement)

---

## Running Tests

```bash
# Run all tabular tests
cd timetoalign
python -m pytest tests/loader/tabular/ -v

# Run only correctness tests
python -m pytest tests/loader/tabular/test_correctness.py -v

# Run only error handling tests
python -m pytest tests/loader/tabular/test_error_handling.py -v

# Run profiling (not a pytest test)
python -m tests.loader.tabular.profile_vectorized
```

---

## Adding New Tests

When adding tests for new specimens:

1. **Document provenance**: Add the specimen to the table above with source and expected event count
2. **Determine EXACT counts**: Count lines in file (`wc -l file.tsv`) and subtract 1 for header
3. **Use ZERO TOLERANCE assertions**: `assert len(events) == EXACT_COUNT`
4. **Update this README**: Add any new limitations or discrepancies discovered

When adding tests for new loaders:

1. Follow the test coverage requirements (15+ tests)
2. Profile with real specimens and document results
3. Add to the "Discrepancies Between Loaders" section if behavior differs

---

## TableSchema System

The `TableSchema` system (`timetoalign.loader.table_schema`) provides a declarative way to specify how tabular columns map to TimeToAlign! objects.

### Key Classes

| Class | Purpose |
|-------|---------|
| `TableSchema` | Main schema container with all specifications |
| `TimelineDefaults` | Default timeline creation parameters (unit, number_type) |
| `CoordinateSpec` | Specifies start/end/duration/instant fields with CMapField support |
| `PartitionSpec` | Groups rows into separate timelines (SEPARATE or CHILDREN mode) |
| `RegionSpec` | Extracts named TimeIntervals from fields |
| `MatchSpec` | Specifies fields referencing events on other timelines |
| `CMapField` | Declares a field as C-Map target (different unit than primary) |
| `Field` | Accesses nested struct/JSON fields (auto-parses JSON) |
| `ComputedField` | Computes derived columns via formula or callable |
| `ConvertedField` | Explicit type conversion/transformation for columns |

### Example Usage

```python
from timetoalign.loader import TableSchema, CoordinateSpec, CMapField
from timetoalign.core import TimeUnit

schema = TableSchema(
    coordinates=CoordinateSpec(
        start="onset_sec",
        duration="duration_sec",
        cmap_fields={"onset_beat": CMapField(target_unit=TimeUnit.quarters)},
    ),
)
results = schema.create_timelines(df)
```

### Test Coverage (test_table_schema.py)

- `TestTimelineDefaults`: Default values and custom configuration
- `TestCoordinateSpec`: Interval, duration, instant, and CMap field specs
- `TestPartitionSpec`: SEPARATE and CHILDREN modes, composite keys
- `TestTableSchemaBasics`: Minimal schema, reserved fields, role detection
- `TestTimelineCreation`: Timeline, region, CMap, and instant event creation
- `TestSerialization`: Dict round-trip and repr output
- `TestEdgeCases`: Missing source columns, empty DataFrames, null handling

---

## SoloLoader

### Specimen

`tests/data/performance_precision/Chopin Nocturne Op. 9 No. 2.solo` — a
header-less tab-separated file of 2494 lines (one note-on or note-off
event per line) produced by a performance-analysis tool.  Six columns:

| Index | Name             | Type         | Example  |
|-------|------------------|--------------|----------|
| 0     | `position`       | "M+frac"     | `1+3/8`  |
| 1     | `duration`       | rational     | `1/2`    |
| 2     | `channel`        | int          | `90`     |
| 3     | `pitch`          | int          | `63`     |
| 4     | `velocity`       | int          | `80`     |
| 5     | `note_id`        | alphanumeric | `nwp1wrk`|

### Validation logic (decided in advance — document-before-implement)

1. **EXACT row count**: 2494 events, matching `wc -l` on the source.
2. **Sentinel rows asserted exactly**:
   - Row 0: `position == "0+11/8"`, `duration == "0/1"`, `channel == 90`,
     `pitch == 70`, `velocity == 80`, `note_id == "n1b8xktz"`.
   - Row 1: `position == "1+0/1"`, `duration == "1/8"`, `pitch == 70`,
     `note_id == "n1b8xktz"` (the note-off paired with row 0).
   - Row 12: `position == "1+3/8"`, `duration == "1/2"`, `pitch == 58`,
     `velocity == 0`, `note_id == "n1fst1u3"` (a note-off pairing).
3. **`column_specs` shape decision**: the composite `position` column
   splits into two parts named `measure_number` (default name derived
   from `MeasureNumberField`'s class name minus the `Field` suffix in
   snake_case) and `mn_onset` (explicit `name="mn_onset"`).  The
   loader surfaces both at the top level of the EventData table so
   `start_column = "mn_onset"` resolves correctly.  The composite
   `position` column also remains as an opaque struct for users who
   need the original packing.
4. **Step 2 promotion**: the `pitch` column is decorated with
   `EnharmonicPitchField` metadata; it is repacked from `int64` into
   the `{midi_number: int64}` struct shape expected by
   `EnharmonicPitchField`.  `note_id` is decorated with `IdField`
   metadata and repacked into `{value: string}`.
5. **`get_field` round-trip**: `events.get_field(EnharmonicPitch)`
   returns an `EnharmonicPitchField` of length 2494; indexing into
   it yields `EnharmonicPitch` scalars (e.g. `[0] -> EnharmonicPitch(B♭4)`
   for MIDI 70).  `events.get_field(Id)[0]` yields
   `Id(value='n1b8xktz')`.
6. **Out-of-scope** (explicitly NOT asserted): the canonical `start`
   coordinate.  Measures are second-order time units; the loader
   currently routes `start_column = "mn_onset"` and consumers must
   reconcile measure-number into flat-quarter coordinates against a
   `MetricMap` separately.

### Composite-part naming convention

When the iterable form of `CompositeFieldParser(parts=[...])` is given
an unnamed entry that resolves to a paired SemanticField subclass
(e.g. `MeasureNumberField`), the resulting sub-field's default name is
the class name minus the `Field` suffix, snake-cased:
`MeasureNumberField` → `measure_number`.  When the resolved entry is a
DataField blueprint or a `FieldParser` instance with an explicit
`name=`, that name is used directly.  Otherwise the fallback is
`f"part_{i}"`.  This is exercised end-to-end in
`test_solo_loader.py` (the `position` column splits into
`measure_number` + `mn_onset`).
