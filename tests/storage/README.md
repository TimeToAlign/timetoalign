# Storage Tests

This directory contains tests for `timetoalign.storage`, the PyArrow-backed
event storage layer (`EventData`, `EventStore` and its subclasses).

## Fraction Fidelity Validation

Interval completion is checked with exact rational expectations whenever every
operand carries a numerator and denominator.  Tests cover both row-oriented
`from_dicts` construction and the vectorized `from_arrays` path, including
addition and subtraction results such as `7/2 + 3/4 = 17/4`.  Float-only and
mixed exact/inexact inputs must leave computed numerator and denominator fields
null; the float convenience value must not be converted back into a fabricated
rational.  These assertions protect the authoritative rational pair from
default `0/1` values during interval filling.

The interval-normalisation regression also checks the explicit temporal type:
an instant row may have a populated ``start`` coordinate, but its ``end`` and
``duration`` cells remain null.  Interval rows still receive both coordinates;
when their inputs are exact, the generated pair is checked with Fraction
arithmetic.  This is the same vectorized path used while assembling merged
score tables.

## Test Files

### `test_events.py` - `EventData.column_values()`

**Purpose:** Documents and validates the public, decoded column-read
affordance that lets callers outside `timetoalign.storage` read a column's
values without reaching into `EventData`'s private `_table`.

**Contract:**

- `column_values(name, *, default=None)` returns one plain Python value per
  event (row), in row order.
- A **rational-shaped** column -- the canonical coordinate struct
  `{value, numerator, denominator}` used by `start`, `end`, `duration`, and
  any extra field sharing that shape -- decodes to an exact `Fraction` via
  `timetoalign.core.struct_to_rational`.
- When a row's struct carries no exact ratio (missing or non-integral
  `numerator`/`denominator`), the float `value` member is used instead,
  wrapped in a `Fraction`.
- A **null coordinate struct cell** yields `default`.
- Every other (non rational-shaped) column type is returned via
  `to_pylist()` unchanged -- ints, strings, bools, lists pass through
  as-is, including `None` for a null cell (`default` does not apply here;
  it only substitutes for a null coordinate struct or an absent column).
- When `name` is not a column of the table at all, the method returns
  `[default] * len(self)` rather than raising `KeyError`.

**Test Categories:**
- **Rational decoding**: a `duration` column with exact numerator/
  denominator decodes to the exact `Fraction`, not a rounded float.
- **Fallback decoding**: a coordinate struct with only `value` populated
  (no numerator/denominator) falls back to `Fraction(value)`.
- **Null coordinate handling**: a null coordinate-struct cell yields the
  caller-supplied `default`.
- **Null plain-column handling**: a null cell in a non-coordinate column
  passes through as `None`, unaffected by `default`.
- **Missing column**: requesting an absent column name returns a
  `default`-filled list sized to the event count, not an exception.
- **Plain passthrough**: non-coordinate columns (e.g. `event_type`) are
  returned unchanged from `to_pylist()`.

### `test_events.py` - `EventData.head()`

**Purpose:** Validates the pandas-style leading-row preview that replaces
the verbose `.table.slice(0, n).to_pandas()` idiom.

**Contract:**

- `head(n=5)` returns the first `n` events as a pandas DataFrame, using the
  same coordinate conversion as `to_dataframe()` (native numbers, not raw
  struct dicts).
- `n` larger than the event count returns every event; `n <= 0` returns an
  empty frame.
- `head(n)` equals the leading `n` rows of `to_dataframe()` (checked with
  `pandas.testing.assert_frame_equal`).

**Test Categories:**
- **Default arity**: `head()` returns exactly five rows.
- **Explicit arity**: `head(n)` returns `n` rows with exact `Fraction`
  coordinates.
- **Over-count / non-positive `n`**: saturates to the full table / yields
  an empty frame.
- **Conversion equivalence**: `head(n)` matches `to_dataframe().head(n)`.
- **Numeric rendering**: coordinate columns decode to `Fraction`, never
  raw struct dicts.
