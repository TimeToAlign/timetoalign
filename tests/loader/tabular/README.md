# Tabular Loader Tests

This directory contains tests for the `timetoalign.loader.tabular` subpackage.

## Test Files

### `test_tabular.py`

Tests for `TabularLoader`, `CsvLoader`, and `TsvLoader` classes.

## Test Data

Tests use **dynamically generated temporary files** rather than static fixtures. This approach:
- Ensures tests are self-contained and reproducible
- Avoids dependency on external data files
- Makes test expectations explicit in the test code itself

### Generated Test Data Format

| Fixture | Format | Columns | Purpose |
|---------|--------|---------|---------|
| `csv_file` | CSV | id, start, end, event_type, name | Basic CSV with mixed instant/interval events |
| `tsv_file` | TSV | id, start, end, event_type, name | Same structure, tab-delimited |
| `minimal_csv` | CSV | start | Minimal file with only required column |

## Validation Logic

### How We Know the Parser is Correct

1. **Column Mapping**: Tests verify that configured columns (e.g., `start_column="onset"`) are correctly mapped to EventData fields.

2. **Temporal Type Inference**: Events with `end` values become "interval" events; those without become "instant" events. This is verified by `test_temporal_types`.

3. **Coordinate Parsing**: Tests verify that coordinates are parsed according to `coordinate_type` (float, int, Fraction).

4. **Error Handling**: Tests verify that missing required columns raise `ValueError` with descriptive messages.

## Known Limitations

- **No schema validation**: TabularLoader does not validate that extra columns match EventData schema fields. Invalid columns are silently ignored.
- **No type coercion for extra columns**: Values from `extra_columns` are stored as-is without type conversion.

## Coverage

All tests use exact assertions per the Zero Tolerance Validation Policy:
- Exact event counts (not ranges)
- Exact coordinate values
- Exact event type distributions
