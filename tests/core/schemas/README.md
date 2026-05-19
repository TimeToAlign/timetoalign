# Tests for `timetoalign.core.schemas` (WP2 pydantic pilot)

This directory pins the contract of the WP2 pilot: pydantic v2 scalar
schemas, the pa.Schema translator, the column-builder pattern, and the
`b"timetoalign"` Parquet-metadata blob.  The pilot scalars are
`Coordinate` (`core/types.py`) and `SpecificPitch` (`core/scalars/pitch.py`).
Other scalars are out of scope for this commission.

Per CLAUDE.md §12, this README is **document-before-implement**: each
test below is reasoned about in prose, with the gold-standard expected
value spelled out, *before* the corresponding test body exists.  The
reviewer cross-checks the test bodies against this document.

## Files

- `test_from_pydantic.py` — pa.Schema derivation from pydantic models
- `test_parquet_metadata.py` — `b"timetoalign"` blob helpers
- `test_column_builder.py` — bulk SemanticField construction
- `test_pilot_round_trip.py` — full Parquet round-trip for Coordinate
  and SpecificPitch, with the three regimes wired up

## Test plan (each `assert` is the gold standard)

### `test_from_pydantic.py`

1. **Coordinate pa.Schema matches the legacy `make_coordinate_type`.**
   `derive_arrow_struct(Coordinate).equals(make_coordinate_type(TimeUnit.seconds))`
   is `True`.  This is the contract that the pydantic translator
   reproduces the existing on-disk coordinate storage byte-for-byte.

2. **Coordinate pa.Schema is `{value: float64?, numerator: int64?,
   denominator: int64?}`.**  All three fields nullable=True.  The
   translator must apply the registered value-projector for
   `Coordinate.value` and the empty projector for `Coordinate.unit`
   (unit lives in pa.Field metadata, NOT in the column).

3. **SpecificPitch pa.Schema is `{step: string, alter: int64,
   octave: int64, cents: float64}`.**  Computed fields (`fifths`,
   `midi_number`, `pitch_class`) MUST be absent.  `step` MUST be
   `pa.string()` (NOT dictionary-encoded).

4. **`@computed_field` properties are excluded.**  `SpecificPitch` has
   `fifths` as a `@computed_field`; the derived struct has exactly 4
   fields, not 5.

5. **Translator caches per class.**  `derive_arrow_struct(Coordinate)`
   called twice returns the **same** `pa.StructType` instance (object
   identity).

6. **Literal[str, ...] is plain `pa.string()`, not dictionary.**
   `SpecificPitch.step` is `Literal["C", "D", "E", "F", "G", "A", "B"]`;
   the derived field's type is `pa.string()`.  This is the explicit
   reason WP2 chose to hand-roll over `pydantic-to-pyarrow`.

7. **Unsupported types raise TypeError.**  A dummy pydantic model with
   a `bytes` or `datetime` field raises `TypeError` from
   `derive_arrow_struct` with a message mentioning extension.  This
   pins the "supported scope" contract; the bulk migration extends.

### `test_parquet_metadata.py`

1. **`metadata_blob_for_model(SpecificPitch)` returns
   `SpecificPitch.model_json_schema()` as UTF-8 JSON bytes.**
   `json.loads(blob)["title"] == "SpecificPitch"`,
   `json.loads(blob)["required"] == ["step", "octave"]`.

2. **Blob is cached and identical across calls.**
   `metadata_blob_for_model(Coordinate) is metadata_blob_for_model(Coordinate)`
   (object identity via `lru_cache`).

3. **`parquet_metadata_for_model` returns a dict with `b"timetoalign"`
   key.**  The value matches `metadata_blob_for_model(cls)`.

4. **`extra=...` is merged into the metadata dict.**
   `parquet_metadata_for_model(Coordinate, extra={b"foo": b"bar"})` has
   both `b"timetoalign"` and `b"foo"`.

5. **`metadata_blob_from_dict({...})` returns sorted JSON bytes.**
   Same input dict in different insertion orders → identical output.
   This is the path used by not-yet-migrated SemanticFields.

6. **`parse_metadata_blob` round-trips.**  Encoding and parsing a dict
   yields the original dict.

### `test_column_builder.py`

1. **`build_struct_array(SpecificPitch, [...])` matches
   `pa.array([sp.model_dump() for sp in scalars], type=struct)`
   field-by-field.**  Verifies byte-equivalence with the row-wise
   `model_dump` path (the legacy/forbidden path) for valid inputs.

2. **Column-builder handles `None` entries.**  A mixed list
   `[sp1, None, sp2]` produces a struct array of length 3 with
   `is_valid == [True, False, True]`.

3. **Column-builder omits computed fields.**  The result has no
   `fifths` column even though `SpecificPitch.fifths` is a computed
   field on the scalar.

4. **`build_coordinate_struct_array` produces the canonical denormalised
   shape.**  For `Coordinate(Fraction(3, 4), TimeUnit.quarters)`, the
   row is `{"value": 0.75, "numerator": 3, "denominator": 4}`.  For
   `Coordinate(1.5, TimeUnit.seconds)`, the row is `{"value": 1.5,
   "numerator": null, "denominator": null}`.

5. **`build_coordinate_struct_array` handles ints losslessly.**  For
   `Coordinate(120, TimeUnit.ticks)`, the row is `{"value": 120.0,
   "numerator": 120, "denominator": 1}`.  Round-trip via
   `struct_to_coordinate` with `NumberType.int` returns `120` (int,
   not float).

6. **Column-builder is at least 2× faster than `model_dump` row-wise
   on 1 000 SpecificPitch instances.**  This is a smoke gate; the
   full 100k benchmark lives in `timetoalign/benchmarks/`.  Marked
   `@pytest.mark.benchmark` (skip-if-not-set).

### `test_pilot_round_trip.py`

1. **SpecificPitch full Parquet round-trip.**  Construct N scalars,
   build the struct array, wrap with metadata blob, write Parquet,
   read it back, `model_construct(**dict)` each row.  Reconstructed
   list is field-for-field equal to the original.

2. **Coordinate full Parquet round-trip with three numeric types.**
   List has one Fraction, one float, one int Coordinate; round-trip
   preserves all three exactly (Fraction precision via num/den).

3. **Metadata blob survives the round-trip.**  After write+read, the
   pa.Field's metadata contains `b"timetoalign"` with the same JSON
   payload bytes.

4. **`model_construct` vs `model_validate` parity on valid input.**
   For a valid dict, both produce equal scalars
   (`sp_v == sp_c == sp_v.model_copy()`).

5. **`model_validate` rejects invalid input that `model_construct`
   accepts silently.**  Dict `{"step": "X", "octave": 4}` —
   `model_validate(...)` raises `ValidationError`;
   `model_construct(...)` returns a scalar with `step="X"` (the
   pa.Schema's trust contract: validators do NOT re-run on internal
   round-trip).

6. **Trust-boundary regime via `from_row` rejects invalid input.**
   `SpecificPitch.from_row({"gpc_str": "X", ...})` raises
   `ValidationError`.

## Tests removed / superseded

This commission replaces these legacy behaviours that no longer apply:

- `Coordinate.__post_init__` raising `TypeError` for bool — superseded
  by the pydantic `@field_validator("value", mode="before")`, which
  raises the same `TypeError` *during* construction (not lazily on
  `number_type` access).  The corresponding test was updated.
- `Coordinate.value = X` raising `AttributeError` — pydantic v2
  `frozen=True` raises `ValidationError` instead.  The corresponding
  test was generalised to accept either exception type.

## Out of scope (deferred to bulk migration)

- `EnharmonicPitch`, `EnharmonicPitchClass`, `SpecificPitchClass`,
  `GenericPitch`, `GenericPitchClass`: still dataclasses.
- `Duration`, harmony scalars, `Note`, `Measure`: still dataclasses.
- Discriminated-union fields inside a scalar schema (forbidden by WP2).
- Nested `BaseModel` fields (the workshop `MidiEvent` scalar will need
  this; the translator's projector hook is the extension point).
