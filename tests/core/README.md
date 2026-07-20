# Core Module Tests

This directory contains tests for the `timetoalign.core` module, which provides fundamental types and enums for the TimeToAlign! library.

## Test Coverage Summary

| Module | Status |
|--------|--------|
| `core/time.py` (TimeScalar hierarchy + paired Fields) | Complete |
| `core/events.py` (pitch / harmony / Note / Measure + paired Fields) | Complete |
| `core/fields.py` (SemanticField base + arrow translator/builder/metadata) | Complete |
| `core/enums.py` | Complete |
| `core/ids.py` | Complete |
| `core/protocols.py` | Complete |
| `core/timestamp.py` | Complete |

## Test Files

### `test_types.py` - Coordinate Type

**Purpose:** Validates the `Coordinate` dataclass, the fundamental unit for representing positions on timelines.

**Test Categories:**

1. **Creation Tests** (10 tests)
   - Integer, float, and Fraction values accepted
   - String units coerced to TimeUnit enum
   - Invalid types (str, None) rejected
   - Frozen dataclass (immutable)
   - Hashable (usable in sets/dicts)

2. **Conversion Tests** (9 tests)
   - `to_float()`, `to_int()`, `to_fraction()` methods
   - Type preservation and truncation behavior

3. **Property Tests** (8 tests)
   - `number_type` property (INT, FLOAT, FRACTION)
   - `domain` property (physical, logical, graphical)
   - Boolean rejection in `number_type`

4. **Arithmetic Tests** (18 tests)
   - Addition/subtraction with same units
   - Different units raise TypeError
   - Scalar multiplication/division
   - Floor division
   - Zero division errors

5. **Comparison Tests** (8 tests)
   - `<`, `<=`, `>`, `>=` operators
   - Different units raise TypeError
   - Non-Coordinate comparison raises TypeError

6. **Utility Tests** (8 tests)
   - `__repr__`, `__str__` formatting
   - `is_zero()`, `is_positive()`, `is_negative()`
   - `with_value()`, `with_unit()` copy methods

**Validity Rationale:**

The Coordinate class is the atomic unit for all temporal positioning in TTA. Tests verify:
- Type safety (only valid number types accepted)
- Immutability (frozen dataclass prevents mutation bugs)
- Unit safety (operations between incompatible units are rejected)
- Mathematical correctness (arithmetic operations preserve semantics)

---

### `test_enums.py` - Domain and Unit Enums

**Purpose:** Validates the enumeration types that categorize domains, units, and event types.

**Test Categories:**

1. **FancyStrEnum Base** (3 tests)
   - Abbreviation lookup (dict and string formats)
   - `__repr__` and `__str__` formatting

2. **Domain Enum** (7 tests)
   - Values: `logical`, `physical`, `graphical`
   - String subclass (usable as strings)
   - Alias support (`lo`, `ph`, `gr`)
   - Invalid value handling

3. **TimeUnit Enum** (18 tests)
   - Physical units: `seconds`, `milliseconds`, `samples`, `frames`
   - Logical units: `quarters`, `beats`, `measures`, `ticks`
   - Graphical units: `pixels`, `points`, `inches`, `millimeters`
   - Alias support (`q`, `ms`, `px`, etc.)
   - `domain` property mapping
   - `is_discrete` property

4. **NumberType Enum** (8 tests)
   - Values: `int`, `float`, `fraction`
   - `python_type` property
   - Construction from string, type, or instance

5. **EventType Enum** (5 tests)
   - Values: `instant`, `interval`
   - Alias support (`inst`, `intv`)

**Validity Rationale:**

The enum types enforce the TTA manuscript's domain model:
- Three domains (Logical, Physical, Graphical)
- Each domain has discrete and continuous variants
- Units must be compatible within operations

---

### `test_ids.py` - Scoped ID System

**Purpose:** Validates the `ScopedId` and `IdGenerator` classes for unique identification.

**Test Categories:**

1. **ScopedId Creation** (9 tests)
   - Basic creation with scope and local
   - Validation (no digits starting scope, no whitespace/colons in local)
   - Frozen and hashable

2. **ScopedId String Conversion** (3 tests)
   - `__str__` format: `scope:local` or just `local`
   - `__repr__` format

3. **ScopedId Parse** (4 tests)
   - Parsing from string with/without scope
   - Roundtrip: `parse(str(id)) == id`

4. **ScopedId Methods** (6 tests)
   - `with_scope()`, `with_local()` copy methods
   - `nested()` for hierarchical scopes
   - `is_scoped` property

5. **IdGenerator Creation** (2 tests)
   - Creation with scope
   - Empty scope allowed

6. **IdGenerator get_or_create** (9 tests)
   - Wrapping external IDs
   - Auto-generation with type hints
   - Counter incrementation
   - Independent counters per type hint

7. **IdGenerator State** (5 tests)
   - `count` property
   - `has_seen()` lookup
   - `reset()` and `reset_counters()` methods

8. **IdGenerator Empty Scope** (2 tests)
   - Unscoped ID generation

**Validity Rationale:**

The ID system ensures:
- Events and timelines have unique, traceable identifiers
- IDs can be hierarchically scoped (e.g., `midi:track1:note_42`)
- External IDs from source files are preserved

---

### `test_timestamp.py` - Unified TimeStamp Architecture

**Purpose:** Validates the unified `TimeStamp` and `TimeIntervalStamp` classes that provide cross-section views through timeline hierarchies.

**Test Categories:**

1. **TimeStampBasics** (3 tests)
   - `get_timestamp()` at specific coordinates
   - Coordinate object input
   - Source reference preservation

2. **TimeStampWithChildren** (6 tests)
   - Child coordinate resolution via `ts["child:id"]`
   - Boundary handling: left-inclusive, right-exclusive `[offset, offset+length)`
   - Out-of-range returns `None` (no extrapolation)
   - Multiple children with staggered offsets
   - `to_dict()` materialization
   - `present_timelines` property

3. **TimeStampWithCMaps** (7 tests)
   - Unit conversion via `get_unit(TimeUnit)`
   - Creating timestamp in alternate unit
   - Subscript access by unit name
   - No C-Map returns None
   - Missing C-Map raises ValueError
   - `to_dict()` with conversion units

4. **TimeIntervalStamp** (10 tests)
   - Interval creation from start/end coordinates
   - `get_interval()` for child timelines
   - `get_duration()` calculation
   - `zip_intervals()` for all timelines
   - Subscript access for intervals
   - Iteration as (start, end) pair
   - `__str__` basic format (header + aligned start/end columns)
   - `__str__` straddling children (`-` for out-of-range endpoint)
   - `__str__` omits fully out-of-range children

5. **TimeStampValidation** (1 test)
   - Start/end must be from same source

6. **TimeStampSource Protocol** (4 tests)
   - Timeline implements required methods
   - `_get_related_timeline_ids()` returns child IDs
   - `_get_available_units()` returns C-Map targets

7. **TimeStampReprHtml** (2 tests)
   - `_repr_html_` still renders the coordinate cross-section table
   - `_repr_html_` appends an affordance `Try` footer after the table
     surfacing the real accessors (`ts.get(<tl_id>)` / `ts.get_unit(<unit>)`)

**Validity Rationale:**

The unified TimeStamp architecture enables:
- Identical coordinate resolution for Timeline and TimelineGroup
- O(log n) lookup via InterpolationMaps (no table scans)
- Seamless unit conversion through attached C-Maps
- Cross-timeline coordinate projection in hierarchies

**Key API Demonstrated:**

```python
# Timeline unified API
ts = timeline.get_timestamp(30.0)
ts.axis                    # 30.0
ts["child:1"]              # Converted coordinate (None if out of range)
ts.to_dict()               # All coordinates as dict
print(ts)                  # Full cross-section display

# Interval stamps
interval = timeline.get_interval_stamp(20.0, 60.0)
interval.duration          # 40.0
interval["child:1"]        # (start, end) tuple (None if both out of range)
print(interval)            # Two-column (start, end) display with '-' for out-of-range
```

**Design Notes:**

- **Child bounds checking**: `TimeStamp.get(child_id)` returns `None` when the queried
  coordinate falls outside the child's `[offset, offset+length)` span, per the TTA
  manuscript's left-inclusive, right-exclusive interval convention.
- **TimeIntervalStamp.__str__**: Shows a `-` when one endpoint is out of range for a
  child, making it easy to see events that straddle children.

### `test_stamp_interface.py` - Stamp Family Contract

**Purpose:** Pins the shared `Stamp` contract using `TimeStamp` as its first
conforming implementation. The exact coordinate values make the `Coordinate`
return type and its attached `TimeUnit` observable, while the subscript cases
pin timeline-ID lookup, unit-name fallback, and unknown-key errors. The tests
also pin `conversion_maps` gating so disabled and allowed-set timestamps cannot
silently resolve units outside their declared set, and verify the exact
`to_dict()` materialized shape.

---

### `test_field_scalar_parity.py` - Scalar `to(*)` vs Field `convert_to(*)` Parity

**Purpose:** Verifies that every `@data_shaped` conversion implemented at the `SemanticField` level produces the same scalar values as the per-row scalar dispatch. The field-level `convert_to(*)` MUST be a `pa.compute` expression over the underlying `pa.Array`; iterating over materialised scalars to call `scalar.to()` is forbidden by the vectorized conversion contract.

**Test Categories:**

1. **EnharmonicPitch conversions** (3 tests)
   - `EP → MidiPitch` (metadata-only retype)
   - `EP → EnharmonicPitchClass` (vectorized `pc.mod(midi_number, 12)`)
   - `EP → EP` (identity)
2. **SpecificPitch conversions** (4 parametrized tests)
   - Full conversion matrix: `SP → {SpecificPitch, MidiPitch, EnharmonicPitchClass, SpecificPitchClass}`
3. **SpecificPitchClass conversions** (2 tests)
   - `SPC → EnharmonicPitchClass`
   - `SPC → SPC` (identity)
4. **GenericPitch conversions** (1 test)
   - `GP → GenericPitchClass`
5. **Sliced-field parity** (2 tests)
   - `SP[20:70] → EnharmonicPitchClass` on a zero-copy slice
   - `EP[10:60] → EnharmonicPitchClass` on a zero-copy slice

**Validity Rationale:**

Per `workshop_typing_push.md` decision 6 ("Scalar/Field parity is structurally enforced — for data-shaped methods only"), every scalar method tagged `@data_shaped` MUST have a vectorized mirror on the paired `SemanticField` subclass. These tests are the runtime guarantee that the mirror produces semantically identical output to the per-row scalar path. Samples include nulls and boundary values (e.g. MIDI 0/1/127, step C/B with alter ±2, octave -1 and 8) to confirm that null propagation and edge cases are handled identically on both paths.

The sliced-field tests confirm the corpus-scale slicing constraint (`workshop_typing_push.md` negative constraints): SemanticField operations MUST work efficiently on zero-copy `pa.Array` slices, never round-tripping through Python loops over materialised scalars.

This file also carries the `__init_subclass__` parity-check failure-path test (`TestParityCheckEnforcement`) that exercises `SemanticField.__init_subclass__`'s `@data_shaped` enforcement on a synthetic bad subclass.

---

### `test_scalar_repr.py` - Uniform scalar `repr()` / `str()`

**Purpose:** Pins the one uniform representation rule across every scalar:
`repr()` is the SHORT typed form `ABBR(token)`, and `str()` is the PRETTY
human token. The pitch scalars consolidate this onto the shared
`TwelveTETPitchMixin` (a class attribute `_REPR_ABBR` + a single
`__str__` / `__repr__`); two pitch scalars override `__repr__` for a
dual-spelling or numeric form. The MIDI-event scalars share one rendered
`__repr__` driven by a `_repr_parts()` hook (no string surgery between the
base and the subclass).

**Exact expected strings (zero-tolerance; canonical ♯/♭ per §13):**

Pitch scalars — `repr()` then `str()`:

| Scalar | construction | `repr()` | `str()` |
|--------|--------------|----------|---------|
| `EnharmonicPitchClass` | `(0)` | `EPC(C)` | `C` |
| `EnharmonicPitchClass` | `(1)` | `EPC(C♯/D♭)` | `C♯/D♭` |
| `GenericPitchClass` | `(0)` | `GPC(C)` | `C` |
| `GenericPitch` | `(0, 4)` | `GP(C4)` | `C4` |
| `SpecificPitchClass` | `(step="C", alter=1)` | `SPC(C♯)` | `C♯` |
| `EnharmonicPitch` | `(56)` (black) | `EP(G♯/A♭3)` | `A♭3` |
| `EnharmonicPitch` | `(60)` (white) | `EP(C4)` | `C4` |
| `MidiPitch` | `(60)` | `MP(60)` | `60` |
| `SpecificPitch` | `(step="C", alter=1, octave=4)` | `SP(C♯4)` | `C♯4` |

Note: `EnharmonicPitchClass` is the only pitch scalar whose `get()` returns
the bare pitch-class integer (untouched — its Field-vectorized mirror depends
on it). To honour the str=pretty rule, `EnharmonicPitchClass.__str__` is an
explicit override returning the dual `_PC_TO_LABEL` label (mirroring the
repr's inner token); `repr()` likewise uses an explicit `_PC_TO_LABEL`
override.

Shallow scalars:

| Scalar | `repr()` | `str()` |
|--------|----------|---------|
| `MeasureNumber(value=16)` | `MeasureNumber(16)` | `16` |
| `Id(value="n0")` | `Id('n0')` | `n0` |

MIDI-event scalars (only non-None fields appear, in declaration order;
`_repr_parts()` is the single source — no `super().__repr__()` slicing):

| Scalar | `repr()` |
|--------|----------|
| `MidiEvent(pitch=EnharmonicPitch(60), velocity=80, channel=0)` | `MidiEvent(pitch=EP(C4), velocity=80, channel=0)` |
| `MidiEvent(control=64, value=127, channel=0)` | `MidiEvent(channel=0, control=64, value=127)` |
| `ScoreMidiEvent(pitch=EnharmonicPitch(60), velocity=80, voice=1, staff=2, part_id="P1")` | `ScoreMidiEvent(pitch=EP(C4), velocity=80, voice=1, staff=2, part_id='P1')` |

Harmony scalars — `str()` returns the bare `label`:

| Scalar | `str()` |
|--------|---------|
| `HarmonyLabel(label="V7", …)` | `V7` |
| `PitchBasedHarmony(label="Cmaj", …)` | `Cmaj` |
| `WesternTertianHarmony(label="Cmaj7", …)` | `Cmaj7` |
| `RomanNumeralHarmony(label="V7", …)` | `V7` |
| `DcmlHarmony(label="V(64)", …)` | `V(64)` |

Note / Measure — `str()` is a pretty one-liner; `repr()` unchanged:

| Scalar | `str()` |
|--------|---------|
| `Note(start=0q, duration=1q, pitch=EnharmonicPitch(61))` | `C♯4 @0 quarters+1 quarters` |
| `Note(start=0q, duration=1q, pitch=None)` (rest) | `rest @0 quarters+1 quarters` |
| `Measure(mn="16", …)` | `16` |

**Validity Rationale:**

The TimeStamp-uniformity philosophy extends to scalar
representation: a user must be able to trust that any scalar's `repr()` is a
short typed form and `str()` is the readable token. Consolidating the rule
onto `TwelveTETPitchMixin` means seven pitch
scalars share one implementation; the `_repr_parts()` hook makes the
`ScoreMidiEvent` extension a first-class override rather than fragile string
surgery over the base repr. The exact-string assertions guard against silent
drift, regression of the EnharmonicPitch dual-spelling repr, and accidental
re-introduction of the verbose `Object(field=…)` forms.

### `test_field_repr_html.py` - Field affordance `_repr_html_`

Validates the rich-HTML affordance card every `DataField` / `SemanticField`
renders through the shared `affordance_html` helper.

**What we validate (exact presence of specific rows/snippets):**

- A live `CoordinateField` card titled `<h4>CoordinateField</h4>` shows:
  - a `Scalar type` row whose value is `Coordinate`;
  - a `Length` row matching the element count;
  - an `Arrow type` row (escaped `struct<…>`);
  - a `Sample` row containing the new scalar reprs (e.g. `Coordinate(0.0,`)
    — proving the sample uses `repr(field[i])`, the scalar reprs.
- The `Try` row lists exactly the three affordance snippets
  `field[i] -> <Scalar>`, `field.convert_to(<TargetScalar>)`,
  `field.get_raw()` (each as a `<code>` span, `<`/`>` escaped).
- A raw `StructField` card (the scalar-less base path) shows `Length`,
  `Arrow type`, `Sample` and the base `field[i]` / `field.get_raw()`
  affordances — but NO `Scalar type` row.
- A schema-only (blueprint) field's `Sample` value is `(schema-only)` and
  its `Length` is `0` — the card never raises.
- Head/tail truncation: a 6-element field's `Sample` shows the first 3 and
  last 2 element reprs separated by the `…` ellipsis.

### `test_eventdata_repr_html.py` - EventData affordance `_repr_html_`

**What we validate:**

- A `MidiEventData` card titled `<h4>MidiEventData</h4>` shows `Events`,
  `Unit`, `Number type`, and a `Fields` row listing each metadata-bearing
  semantic field as `name : ScalarType` inside an `<ul>` (the materialised
  `pitch` column reports `pitch : EnharmonicPitch`).
- The `Try` row lists `get_field(<Scalar>)`, `get_pitch_field()`,
  `get_raw('<col>')`.
- A plain `EventData` whose columns carry no `field_type` metadata renders a
  `Fields` row of `(none)` and does NOT raise (graceful skip per the
  "must not raise if a column has no paired field" contract).

---

## Running Tests

```bash
# Run all core tests
cd timetoalign
python -m pytest tests/core/ -v

# Run specific test file
python -m pytest tests/core/test_timestamp.py -v

# Run with coverage
python -m pytest tests/core/ --cov=timetoalign.core --cov-report=term-missing
```

---

## Validation Methodology

All tests follow the TimeToAlign! engineering standards:

1. **Exact Values**: Assertions use exact expected values, not ranges or tolerances
2. **Immutability**: Frozen dataclasses are tested for mutation rejection
3. **Type Safety**: Invalid types are verified to raise appropriate errors
4. **Roundtrip**: Serialization/parsing operations preserve data exactly
