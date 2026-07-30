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

### `test_fraction_field_arithmetic.py` - Exact Coordinate Arithmetic

**Purpose:** Validates that arithmetic over coordinate and duration fields keeps
exact rational storage when every participating value has an authoritative
numerator/denominator pair.

The tests inspect both the materialised numeric result and the underlying Arrow
struct. Exact rows assert the reduced numerator and denominator as well as the
float convenience value; mixed rows assert that exact inputs retain pairs while
rows involving floats have null pair members. Scalar Coordinate/Duration
operations are checked with exact `Fraction` equality, and float operations are
checked to ensure arithmetic never fabricates a rational pair from a float.

**Validity Rationale:** The rational pair is the lossless representation used
for persistence. Checking the pair directly catches precision loss that value
comparisons alone could hide.

### `test_coordinate_resolution.py` - Coordinate Input Resolution

**Purpose:** Validates the shared decomposition of public coordinate inputs and
the timeline-level policy that resolves timeline IDs and units.

The tests use exact values to cover raw integer, float, and `Fraction` inputs;
plain and timeline-qualified coordinates; conflicting IDs; unsupported input
types; exact preservation of native `Fraction` values; conversion through an
attached C-Map; missing conversion paths; unknown timeline IDs; and descendant
offset arithmetic. Descendant resolution covers two-level offset composition,
bare values qualified by `timeline_id`, and scalar and affine foreign-unit maps
registered on either the owning descendant or one of its ancestors. It verifies
that conversion precedes the exact upward offset composition. Public routing
coverage also verifies unknown timeline IDs through `to_dataframe()`, batch
group queries with independently qualified rows, missing IDs on raw batch
values, and conflicting embedded and explicit timeline IDs wherever both forms
are accepted. This separates the pure core decomposition contract from the
unit- and hierarchy-aware behavior owned by `Timeline.get_coordinate()`.

**Validity Rationale:** A single decomposition shape prevents callers from
silently discarding unit or timeline metadata, while timeline resolution makes
every public coordinate entry point apply the same conversion and child-offset
rules.

---

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

The enum types enforce TimeToAlign's domain model:
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
   - `_get_related_timeline_ids()` returns direct child IDs
   - `_get_descendant_timeline_ids()` returns the full subtree
   - `_get_available_units()` aggregates C-Map targets across the subtree

7. **TimeStampReprHtml** (2 tests)
   - `_repr_html_` still renders the coordinate cross-section table
   - `_repr_html_` appends an affordance `Try` footer after the table
     surfacing the real accessors (`ts.get(<tl_id>)` / `ts.get_unit(<unit>)`)

8. **TimeStampCrossSectionConversions** — every C-Map surfaces, at any depth
   - A conversion map with **no `target_unit`** (a label or structured-value
     map such as `IntervalToConstantMap`) surfaces in `__str__`, `to_dict`,
     subscript, and `get_conversion` — not only `TimeUnit`-targeted maps. This
     is the core-contract requirement: a timestamp is a cross-section, so it
     exposes ALL attached conversions, not just the numeric-unit subset.
   - A C-Map registered on a **direct child** surfaces on the parent's
     timestamp, evaluated at the child's own coordinate.
   - A C-Map registered on a **grandchild** (deeper descendant) likewise
     surfaces, evaluated at the descendant coordinate reached by exact,
     composed offset arithmetic. A stop-at-direct-children design would still
     hide these — the whole subtree is walked.
   - **Non-numeric outputs render intact**: a mapping/label value appears as
     itself (e.g. `{'page': 2}`, `'B'`), never coerced through `float`.
   - **Subscript by map name/selector**: `ts["<cmap-name>"]` returns the raw
     C-Map output; an unknown key raises `KeyError`.
   - **Collision qualification**: when two present timelines expose the same
     label, both are qualified as `"{owner_id}:{label}"`.
   - **`conversion_maps` gating** still applies — `conversion_maps=False`
     suppresses every surfaced conversion; a selector list surfaces only the
     matching maps.

   Contract §4 ("C-Map visibility"): timestamps surface the full
   `_conversion_maps` set across the subtree via `_conversion_rows()`.
   `add_conversion_map` still indexes `TimeUnit`-targeted maps in `_unit_maps`
   for `convert_to`/`get_conversion_map`.

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
  left-inclusive, right-exclusive interval convention.
- **TimeIntervalStamp.__str__**: Shows a `-` when one endpoint is out of range for a
  child, making it easy to see events that straddle children.

### `test_stamp_interface.py` - Stamp Family Contract

**Purpose:** Pins the shared `Stamp` contract across `TimeStamp` and `MatchStamp`.
The exact coordinate values distinguish raw `get()` lookup from the
`Coordinate`-returning `get_coordinate()` API and make attached `TimeUnit`
values observable. The cases pin `present_timelines`, timeline-ID-first
subscript lookup with unit-name fallback, conversion-map gating, every
`MatchStamp.to_dict()` format, and frozen `MatchStamp` fields. Exact dictionary
shapes ensure neither grouped rendering nor legacy graph serialization drifts.

**`MatchStamp` conversion-row display:** `MatchStamp.__str__`/`_repr_html_`
surface every C-Map enabled by the stamp's `conversion_maps` spec, the same
row shape `TimeStamp` uses (`_conversion_rows()` — inherited from the shared
`Stamp` base). The fixture timeline (`clock`, length 100 seconds) carries two
exact-value `TableMap`s: seconds→milliseconds (`[0,100]->[0,100000]`) and
seconds→frames (`[0,100]->[0,5000]`), queried at 25.0 seconds:

- `conversion_maps=True` — `str(stamp)` and `_repr_html_()` contain
  `"milliseconds"`/`"25000"` and `"frames"`/`"1250"` (25.0×1000 and 25.0×50);
  the HTML rows are tagged `<em>cmap</em>`.
- `conversion_maps=False` (the getter default, see below) — neither unit name
  appears in either rendering; the source coordinate (`"clock"`/`"25"`) still
  does.

**`conversion_maps` is opt-in on `MatchStamp`:** the field default and every
public matchstamp getter (`AlignmentBundle.get_matchstamp_at`,
`get_matchstamps`, `get_matchstamp_table`, `MatchClaim.get_matchstamp`) now
default `conversion_maps` to `False` — a caller must ask for conversions
explicitly, matching the opt-in getter pattern elsewhere in the module. Every
existing exact-value assertion in this file passes `conversion_maps=True`
(or `False`) explicitly through `_matchstamp_with_maps`, so none depend on
the getter default.

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

Scalar/Field parity is structurally enforced for data-shaped methods: every scalar method tagged `@data_shaped` MUST have a vectorized mirror on the paired `SemanticField` subclass. These tests are the runtime guarantee that the mirror produces semantically identical output to the per-row scalar path. Samples include nulls and boundary values (e.g. MIDI 0/1/127, step C/B with alter ±2, octave -1 and 8) to confirm that null propagation and edge cases are handled identically on both paths.

The sliced-field tests confirm the corpus-scale slicing constraint: SemanticField operations MUST work efficiently on zero-copy `pa.Array` slices, never round-tripping through Python loops over materialised scalars.

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

### `test_parquet_metadata.py` - Versioned metadata blob, single ownership

**Purpose:** Pins the contract of the Arrow-metadata vocabulary that travels
with every TimeToAlign!-written `pa.Field` and table schema.
`core/fields.py` is its sole owner: it defines the metadata key, the blob
version, the two writers (`metadata_blob_from_dict`,
`metadata_blob_for_model`) and the one parser (`parse_metadata_blob`).

**What we validate:**

1. **Version injection.** Both writers stamp
   `"version": TIMETOALIGN_BLOB_VERSION` into every payload they encode —
   the dict writer even when the caller supplied no `version`, and the model
   writer alongside the model's JSONSchema. `parse_metadata_blob` returns the
   `version` entry as part of the payload, so a parsed dict can be re-encoded
   unchanged.
2. **Version-less rejection.** A hand-rolled blob with no `version` key, a
   non-integer `version`, or a `version` greater than
   `TIMETOALIGN_BLOB_VERSION` raises `ValueError`. There are no
   compatibility shims: every blob in circulation comes from one of the two
   writers. Absent (`None`) and empty blobs still parse to `{}`.
3. **Single ownership.** The byte string `b"timetoalign"` is spelled out in
   `timetoalign/core/fields.py` and nowhere else in the package — every other
   module imports `TIMETOALIGN_METADATA_KEY`. A test walks the package source
   to enforce this, in either quote style and including prose: an error
   message that spells the key out is a second source of truth too, so those
   name the constant instead.
4. **Hierarchy-wide stamping.** `SemanticField.to_field()` stamps the blob for
   every field in the hierarchy exactly once, deriving `field_type` from the
   class rather than from hand-written literals, and carries over metadata
   entries owned by anyone else untouched.
5. **Canonical-struct round-trip.** `rational_to_struct` /
   `struct_to_rational` are the row-wise pair for
   `RATIONAL_STRUCT_TYPE` (`{value, numerator, denominator}`), the library's
   only rational shape. Round-trips return the **exact** `Fraction`
   (`Fraction(3, 4)`, not `0.75`) because the parser reads the integer
   components and ignores the lossy float projection; a struct whose
   components are not integers raises `ValueError`.

**Validity Rationale:** A single owner plus a required version means a stored
table can always be interpreted, and a future payload change is a bump rather
than a guessing game. One rational struct means a reader never has to sniff
between two key spellings to recover an exact ratio.

---

### `test_wire_format.py` - The rational wire dict

**Purpose:** Pins the JSON wire format shared by every `to_dict` in the
library. `RATIONAL_STRUCT_TYPE` is how a rational is stored in Arrow; the
**rational wire dict** is how the same number is stored in JSON, and
`core/fields.py` owns both.

**The shape.** Every rational-valued number in a `to_dict` payload is the
three-key dict

```json
{"value": 3.3333333333333335, "numerator": 10, "denominator": 3}
```

`rational_to_wire` writes it and `wire_to_rational` reads it. A `Fraction`
keeps its exact ratio; anything else encodes as `{"value": x, "numerator":
null, "denominator": null}` and decodes back to a plain `float`. The null
ratio is the *only* marker of inexactness — the float `value` is a lossy
projection and is never consulted when the ratio is present.
`is_rational_wire` recognises the shape for the few slots (a `ConstantMap`
value) whose payload is genuinely open-ended.

There is exactly one encoding. `Fraction` objects are never emitted raw, and
the `"n/d"` strings the maps used to write are gone — `wire_to_rational`
rejects a string rather than parsing it, so a stale payload fails at the
boundary instead of silently becoming something else.

**What we validate:**

1. **Codec.** Exact ratios survive `rational_to_wire` → `json` →
   `wire_to_rational`; floats and ints encode with a null ratio and decode as
   `float`; non-numeric input and stale string encodings raise.
2. **Fixpoint guarantee.** For a timeline, a `BeatGrid`, a map, an
   `AlignmentAnchor`, and a `MatchClaim`,
   `X.from_dict(json.loads(json.dumps(x.to_dict()))) .to_dict() == x.to_dict()`.
   The dictionary is the fixed point, so a payload can be written, read, and
   written again without drifting.
3. **Exactness.** `Fraction(10, 3)` as a timeline length, `Fraction(5, 3)` as
   a child offset, `Fraction(1, 3)` as an event coordinate, and
   `Fraction(3, 4)` as a `ConstantMap` value all come back with their
   numerator and denominator intact.
4. **Name round-trip.** `ConversionMap.to_dict` always emits `name`, and
   every subclass `from_dict` passes it back to the constructor, so a custom
   name survives serialization for every registered map class.
5. **JSON safety.** A parametrized sweep asserts `json.dumps` succeeds on the
   `to_dict` output of `Timeline`, `BeatGrid`, every `ConversionMap`
   subclass, `WarpMap`, `MatchLine`, `MatchGraph`, all four `MatchStamp`
   formats, `TimeStamp`, the claim classes, `MeasureUnit`, and the section
   dicts.

**Validity Rationale:** A serialization format that raises `TypeError` on
`json.dumps` for one number type and silently loses precision for another is
two bugs wearing one coat. Pinning a single encoding, and asserting the
fixpoint rather than merely "it round-trips", makes both failure modes
regressions rather than discoveries.

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
