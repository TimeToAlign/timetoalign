# Semantic Fields & Score Scalars Tests

This directory contains tests for the `timetoalign.fields` module (the semantic
field hierarchy), the `timetoalign.core.scalars` score types, and the
`timetoalign.loader.mixins` field-access dispatch system. Together these validate
the three-layer architecture: **Protocol -> Scalar -> Field**.

## Test Files

| File | Tests | What It Validates |
|------|------:|-------------------|
| `test_fields_base.py` | 26 | Raw DataField classes (`NumericField`, `StringField`, `StructField`, `MapField`), `SemanticField[R]` composition, protocol conformance |
| `test_coordinate_field.py` | 29 | `CoordinateField` -- the reference `SemanticField[StructField]` implementation |
| `test_pitch_field.py` | 54 | Pitch field hierarchy: abstract `PitchField`, `GenericPitchField`, `SpelledPitchClassField`, `SpecificPitchField`, `EnharmonicPitchField`, aliases |
| `test_harmony_field.py` | 36 | Harmony field hierarchy: abstract `HarmonyField`, `WesternTertianHarmonyField`, `RomanNumeralHarmonyField`, `DcmlLabelField` |
| `test_mixins.py` | 28 | `SemanticFieldAccessMixin` dispatch, `PitchAccessMixin`, `HarmonyAccessMixin`, `MeasureAccessMixin`, EventData composition |
| `test_score_scalars.py` | 40 | Frozen dataclass scalars: `MidiPitch`, `SpelledPitch`, `Note`, `Measure`, `DcmlHarmony` |
| `test_real_data_score.py` | 19 | End-to-end validation with real Chopin and Beethoven specimens |
| **Total** | **232** | |

## Detailed Test Categories

### `test_fields_base.py` (26 tests)

**What we validate:**
- Raw field classes accept correct Arrow types and reject incorrect ones
- `SemanticField[R]` delegates attribute access to the wrapped raw field
- `SemanticField.value` returns the raw field for schema access
- `DataField.to_pyarrow()` produces correct `pa.Array` and `pa.Field` objects
- Schema-only fields (no data) raise on element access and `to_pyarrow()`
- `CoordinateField` satisfies `SemanticTypeLike` and `CoordinateLike` protocols

**Why this matters:**
The raw field classes are the foundation of the entire semantic type system.
`SemanticField[R]` uses Generic[R] composition (not inheritance) -- this is a
core architectural decision that must be verified.

### `test_coordinate_field.py` (29 tests)

**What we validate:**
- Construction from 4 sources: `pa.Array`, `StructField`, `pa.Field` (schema), `(name, type)` tuple
- `__getitem__` returns `Coordinate` scalars with correct `value`, `numerator`, `denominator`
- Fraction and integer coordinate variants
- Null handling: `__getitem__` returns `None` for null structs
- Properties: `unit`, `domain`, `number_type`, `metadata_dict`
- Serialization: `to_field()` injects `b"timetoalign"` metadata; Parquet round-trip preserves metadata
- `from_table()` auto-detection and explicit column selection
- Copy-on-write: `with_unit()` returns new field with updated metadata
- Delegation: `value`, `field_names`, `get_sub_field()` pass through to raw `StructField`

**Why this matters:**
`CoordinateField` is the canonical reference implementation for all `SemanticField`
subclasses. Its patterns (construction, delegation, serialization) are replicated
across all other semantic fields.

### `test_pitch_field.py` (54 tests)

**What we validate:**

| Test Class | Tests | Purpose |
|---|---|---|
| `TestAbstractPitchField` | 2 | `PitchField` cannot be instantiated; has abstract methods |
| `TestHierarchy` | 4 | `isinstance(field, PitchField)` for all 4 concrete subclasses |
| `TestAliases` | 4 | `MidiPitchField is SpecificPitchField`; `SpelledPitchField is EnharmonicPitchField` |
| `TestProtocolConformance` | 6 | Each field and scalar satisfies `SemanticTypeLike`, `PitchLike` |
| `TestSpecificPitchFieldConstruction` | 4 | `SpecificPitchField` from array/struct/schema/tuple |
| `TestGenericPitchFieldConstruction` | 4 | `GenericPitchField` from array/struct/schema/tuple |
| `TestSpelledPitchClassFieldConstruction` | 3 | `SpelledPitchClassField` from array/struct/schema |
| `TestSpecificPitchFieldElementAccess` | 3 | `__getitem__` returns `MidiPitch` with exact values |
| `TestGenericPitchFieldElementAccess` | 3 | `__getitem__` returns `GenericPitch` with exact values |
| `TestSpelledPitchClassFieldElementAccess` | 2 | `__getitem__` returns `SpelledPitchClass` |
| `TestEnharmonicPitchFieldElementAccess` | 2 | `__getitem__` returns `SpelledPitch` |
| `TestProperties` | 8 | `semantic_type` and `metadata_dict` for all 4 concrete types |
| `TestSerialization` | 4 | `to_field()` metadata injection; Parquet round-trip |
| `TestDelegation` | 5 | `value`, `len`, `is_empty`, `name`, `field_names` delegation |

**Why this matters:**
The pitch field hierarchy is the largest in the system (4 concrete subclasses
from one abstract parent). The abstract parent enforces that all subclasses share
a common interface while allowing each to wrap a different struct schema and
return a different scalar type from `__getitem__`.

**Pitch field struct schemas:**

| Field Class | Struct Schema | Scalar |
|---|---|---|
| `GenericPitchField` | `{pitch_class: int64}` | `GenericPitch` |
| `SpelledPitchClassField` | `{gpc_str: string, acc: int64, spc_int: int64}` | `SpelledPitchClass` |
| `SpecificPitchField` | `{ep: int64, epc: int64}` | `MidiPitch` |
| `EnharmonicPitchField` | `{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}` | `SpelledPitch` |

### `test_harmony_field.py` (36 tests)

**What we validate:**

| Test Class | Tests | Purpose |
|---|---|---|
| `TestProtocolConformance` | 3 | Scalars satisfy `HarmonyLabelLike`; fields satisfy `SemanticTypeLike` |
| `TestHierarchy` | 6 | `isinstance` relationships: `DcmlLabelField` is `HarmonyField`; `RomanNumeralHarmonyField` is `WesternTertianHarmonyField`; `DcmlLabelField` is NOT `WesternTertianHarmonyField`; `HarmonyField` is abstract |
| `TestConstruction` | 4 | `DcmlLabelField` from array/struct/schema/tuple |
| `TestWesternTertianConstruction` | 2 | `WesternTertianHarmonyField` from array/struct |
| `TestRomanNumeralConstruction` | 2 | `RomanNumeralHarmonyField` from array/struct |
| `TestElementAccess` | 3 | `DcmlLabelField.__getitem__` returns `DcmlHarmony` with exact values |
| `TestWesternTertianElementAccess` | 2 | Returns `WesternTertianHarmony` scalars |
| `TestRomanNumeralElementAccess` | 2 | Returns `RomanNumeralHarmony` scalars |
| `TestProperties` | 5 | `semantic_type` and `metadata_dict` for all 3 concrete types |
| `TestSerialization` | 2 | `to_field()` metadata injection; Parquet round-trip |
| `TestDelegation` | 5 | `value`, `len`, `is_empty`, `name`, `field_names` delegation |

**Why this matters:**
The harmony hierarchy demonstrates a different branching pattern from pitch: it
uses intermediate abstract levels (`WesternTertianHarmonyField` ->
`RomanNumeralHarmonyField` -> `DcmlLabelField`) where each level adds schema
fields. The `isinstance` tests verify that `DcmlLabelField` is a `HarmonyField`
but NOT a `WesternTertianHarmonyField` (parallel branch, not linear chain).

**Harmony field struct schemas (cumulative):**

| Field Class | Schema Adds | Scalar |
|---|---|---|
| `HarmonyField` (abstract) | `label, standard` | -- |
| `WesternTertianHarmonyField` | `root, bass, chord_quality, inversion` | `WesternTertianHarmony` |
| `RomanNumeralHarmonyField` | `numeral, key_context` | `RomanNumeralHarmony` |
| `DcmlLabelField` | `globalkey, localkey, form, figbass, relativeroot, pedal` | `DcmlHarmony` |

### `test_mixins.py` (28 tests)

**What we validate:**

| Test Class | Tests | Purpose |
|---|---|---|
| `TestSemanticFieldAccessMixin` | 12 | `get_field()` dispatch via column metadata; parent-type matching (`PitchField` matches `SpecificPitchField`); `get_fields()` returns all matches; `has_field()` presence checks; data access through reconstructed fields |
| `TestPitchAccessMixin` | 5 | `get_pitch_field()` with explicit type; default priority (EnharmonicPitchField > SpecificPitchField > GenericPitchField); raises when no pitch columns exist |
| `TestHarmonyAccessMixin` | 5 | `get_harmony_field()` with explicit type; default priority (DcmlLabelField > RomanNumeralHarmonyField > WesternTertianHarmonyField); data access |
| `TestMeasureAccessMixin` | 1 | Placeholder raises `NotImplementedError` |
| `TestEventDataComposition` | 5 | `NoteEventData` has `PitchAccessMixin`; `MeasureData` has `MeasureAccessMixin`; `AnnotationEventData` has `HarmonyAccessMixin`; backward compat of `pitch_field`/`spelled_pitch_field` properties |

**Why this matters:**
The mixin dispatch system replaces hardcoded `pitch_field`/`spelled_pitch_field`
properties with type-dispatched `get_field(type)` access. This is the bridge
between the field hierarchy and the EventData stores. The dispatch scans column
metadata (`b"timetoalign"` JSON blobs) to reconstruct the appropriate
`SemanticField` subclass, using `issubclass()` for parent-type matching.

### `test_score_scalars.py` (40 tests)

**What we validate:**

| Test Class | Tests | Purpose |
|---|---|---|
| `TestMidiPitch` | 9 | Construction, `PitchLike`/`SpecificPitchClassLike` conformance, `semantic_type`, `metadata_dict`, immutability, `octave` property |
| `TestSpelledPitch` | 9 | Construction, `PitchLike` conformance, `midi_number` computation (C4=60, B3=59, G#3=56), `pitch_class` computation, immutability |
| `TestNote` | 7 | Construction with pitch and as rest, `NoteLike` conformance, `instrument` field, immutability |
| `TestMeasure` | 7 | Construction, anacrusis, `MeasureLike` conformance, time signature tuple, flow control defaults, immutability |
| `TestDcmlHarmony` | 8 | Construction, dominant seventh, `HarmonyLabelLike`/`DcmlLabelLike` conformance, `semantic_type`, `metadata_dict`, immutability |

**Why this matters:**
Scalars are the element-level representation returned by `Field.__getitem__()`.
Each is a frozen dataclass with `slots=True` that satisfies one or more Protocols.
The MIDI number computation tests use exact values (ZERO TOLERANCE) derived from
the standard MIDI specification.

**Exact values validated:**

| Scalar | Property | Value |
|---|---|---|
| `MidiPitch(60, 0)` | `octave` | `4` |
| `SpelledPitch("C", 0, 4, -1, 0.0)` | `midi_number` | `60` |
| `SpelledPitch("B", 0, 3, 5, 0.0)` | `midi_number` | `59` |
| `SpelledPitch("G", 1, 3, 8, 0.0)` | `midi_number` | `56` |
| `SpelledPitch("C", 0, ...)` | `pitch_class` | `0` |
| `SpelledPitch("B", 0, ...)` | `pitch_class` | `11` |

### `test_real_data_score.py` (19 tests)

**What we validate:**

| Test Class | Tests | Specimen | Purpose |
|---|---|---|---|
| `TestChopinPitchFieldFromTSV` | 5 | Chopin op. 10/3 | Note count, first note MIDI pitch, pitch class, field construction from `NoteEventData`, first element scalar |
| `TestChopinMeasuresFromTSV` | 6 | Chopin op. 10/3 | Measure count, first/last MC, MN, time signature, all measures 2/4 |
| `TestBeethovenHarmonies` | 6 | Beethoven op. 2/1-i | First label, globalkey, numeral, V65 chord details, harmony count |
| `TestPitchFieldParquetRoundtrip` | 1 | Chopin op. 10/3 | Parquet write/read preserves pitch field metadata and scalar values |
| `TestCrossLoaderPitchConsistency` | 1 | Chopin op. 10/3 | TSV and Partitura loaders produce identical pitch values |

**Why this matters:**
These tests validate the semantic field system end-to-end against real musicological
data. They use EXACT expected values from the Vienna 4x22 corpus, ensuring that
the abstract type system correctly wraps actual analytical data.

**Test data specimens:**
- `tests/data/vienna_1x22/Chopin_op10_no3.notes.tsv` -- 1,159 notes
- `tests/data/vienna_1x22/Chopin_op10_no3.measures.tsv` -- 77 measures
- `tests/data/vienna_1x22/Chopin_op10_no3.musicxml` -- MusicXML score
- `tests/data/score/beethoven_op2no1_i_harmonies.tsv` -- DCML harmony annotations

## Running Tests

```bash
# Run all field tests
cd timetoalign
python -m pytest tests/fields/ -v

# Run only pitch field tests
python -m pytest tests/fields/test_pitch_field.py -v

# Run only harmony field tests
python -m pytest tests/fields/test_harmony_field.py -v

# Run only mixin tests
python -m pytest tests/fields/test_mixins.py -v

# Run with coverage
python -m pytest tests/fields/ --cov=timetoalign.fields --cov=timetoalign.loader.mixins --cov-report=term-missing
```

## Known Limitations

1. **`MeasureAccessMixin` is a placeholder.** `MeasureField` is not yet defined
   as a `SemanticField` subclass. `get_measure_field()` currently raises
   `NotImplementedError`. This will be addressed when the BeatGrid integration
   work defines the `MeasureField` type.

2. **No `SpelledPitchClassField` construction from tuple.** The `from_tuple`
   constructor is not yet implemented for `SpelledPitchClassField` because the
   struct schema has not stabilized. Construction from `pa.Array` and
   `StructField` is fully supported.

3. **Harmony hierarchy branching.** `DcmlLabelField` is a direct subclass of
   `HarmonyField`, NOT of `WesternTertianHarmonyField`. This is intentional:
   the DCML standard's struct schema includes fields from all levels
   (western tertian + roman numeral + DCML-specific) in a flat struct,
   rather than composing through intermediate field classes.
