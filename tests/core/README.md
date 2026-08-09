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

**Purpose:** Validates that arithmetic over coordinate and duration fields runs
in the representation the field declares, and that both sides of every result
cell agree.

A storage cell carries its number twice — as a float64 and as an integer ratio
— and **both sides are populated on every non-null row**. Which side is
authoritative is not something a reader may infer from the row; it is declared
once per field, in `number_type` metadata. The tests therefore assert three
things per result: the materialised scalar, the ratio members, and that the
float member equals `float(numerator/denominator)` exactly. A cell whose two
sides disagree is a bug even when the side a caller happens to read is right.

Field-with-field arithmetic asserts that **the left operand decides** the
result's representation: a fraction-typed `CoordinateField` plus a float-typed
`DurationField` yields a fraction-typed `CoordinateField`, with the float side
mirrored from the exact result. Scalar arithmetic asserts the same rule, so
`Coordinate(Fraction(1, 3), quarters) + 0.5` is `Fraction(5, 6)` and not
`0.8333333333333333` — the float operand is converted into the left operand's
representation *before* the addition, which is the whole point of declaring one.

Scaling is asserted separately and deliberately, under the rule **quantize
the result, never the operand**. A multiplier is dimensionless, so converting
it into the field's representation first is a category error; instead the
arithmetic runs in the most exact representation the two sides afford, and
rounding happens once, at the end, on the canonical side. Two cases pin it,
and between them they separate every candidate implementation:

* `Coordinate(101, ticks) * 0.5` is `50` — exactly `101/2`, then one
  half-to-even rounding. Coercing the operand first would give `0`
  (`round(0.5)`), and skipping the final rounding would give `50.5`.
* `Coordinate(Fraction(1, 3), quarters) * 0.5` is `Fraction(1, 6)` — `0.5`
  *is* exactly `1/2`, so the exact lane stays exact. Doing this one in float
  would yield an ugly dyadic instead of a sixth.

Additive operands follow the opposite rule and are converted first, because
an added quantity is measured in the field's unit rather than standing
outside it.

Unit mismatch and cross-timeline-id mismatch are asserted to raise `TypeError`
once per call, from metadata, never per row.

**Validity Rationale:** Checking the ratio members directly catches precision
loss that value comparisons alone would hide, because the float side of an
exact cell is *supposed* to look right. Checking that the two sides mirror each
other catches the subtler failure: a cell that is internally inconsistent
answers different questions differently depending on which accessor a caller
reaches for.

### Display shows what the value carries

One formatter (`format_number`) sits behind every pretty rendering — scalar
`__str__`, stamp display, table cells. Having exactly one is the point rather
than a tidiness preference: a display that shows less than the value carries
is a lie the reader has no way to detect, and two formatters drift into
precisely that. Before unification, `str(Coordinate(Fraction(1, 3),
quarters))` read `0.333333` while the stamp rendering of the same position
read `1/3`.

Pinned, exactly:

| Value | Renders |
|---|---|
| `Fraction(1, 3)` quarters | `1/3 quarters` |
| `Fraction(19, 2)` quarters | `19/2 quarters` |
| `Fraction(10, 1)` quarters | `10 quarters` — integral, so no denominator |
| `2.0` seconds | `2 seconds` — integral, so no decimal point |
| `0.1` seconds | `0.1 seconds` |
| `1/3` (float) seconds | `0.3333333333333333 seconds` — every digit it round-trips with |
| `1234567.5` seconds | `1234567.5 seconds` — large values are not rounded away |
| `1e-7` seconds | `0.0000001 seconds` — never scientific, never `0` |
| `160` ticks | `160 ticks` |

The last two rows were live defects, not hypotheticals: the old scalar
formatter rendered `1234567.5` as `1234568` and `1e-7` as `0`. A test asserts
the scalar and stamp paths produce identical strings for the same value, so
they cannot drift apart again. `repr()` is the other lane and was already
exact — it is left alone.

### Scalar construction: the unit chooses the representation

A scalar holds exactly one value, so something has to decide how it is
written — and that decision belongs to the unit, not to whichever Python
type the caller's literal happened to have. `Coordinate(2, quarters)` and
`Coordinate(1.5, quarters)` are both quarter positions and both come out
exact (`Fraction(2, 1)`, `Fraction(3, 2)`); they no longer differ because one
was typed with a decimal point. The tests pin each arm, because the failure
mode here is two adjacent literals on the same unit disagreeing about their
own type, which then propagates through arithmetic (the left operand decides)
into results that differ depending on operand order.

An explicit `number_type=` overrides the default and is validated against
what the unit admits — that is how a caller deliberately chooses the float
lane on a fractional unit.

Coercion toward the default never loses information, and each rule is pinned:

| Input | Unit default | Result | Why |
|---|---|---|---|
| `2` | `fraction` | `Fraction(2, 1)` | exact widening |
| `1.5` | `fraction` | `Fraction(3, 2)` | exact dyadic |
| `0.0001` | `fraction` | dyadic, denominator `2**66` | **no int64 ceiling here** — Python `Fraction` is arbitrary-precision, and the storage refusal belongs at the field boundary where the ceiling actually exists |
| `10` | `float` | `10.0` | widens, and raises if it would not survive the trip |
| `Fraction(1, 3)` | `float` | `Fraction(1, 3)` **kept** | degrading an exact input silently is the thing this scheme exists to prevent; it takes an explicit `number_type=float` |
| `120.7` | `int` (discrete) | `121` | a measurement read off a float clock |
| `Fraction(5, 24)` | `int` (discrete) | **raises** | an exact non-integral value is a unit mix-up, not a rounding candidate |

The 0.0001 row is worth reading twice: it is the case where the scalar path
and the storage path deliberately differ. The scalar accepts it and holds the
exact ratio; storing it in a *fraction-canonical field* raises, because that
is where int64 lives. Both are asserted.

**The unit chooses only for values a caller AUTHORS.** A value the library
*derived* — a conversion result, offset arithmetic, a stored row, an
interpolated position — keeps the representation its computation produced.
The two rules answer different questions: authoring asks "how should a
quarter position be written?", where the literal's Python type is an accident
worth normalising away; deriving asks "what did this computation actually
establish?", where the type is the answer and normalising it away would claim
precision nothing supports.

The distinction changes behaviour rather than being a matter of taste, and
`tests/test_rational_coordinate_preservation.py` is where it is enforced. A
float tick count converted to quarters stays float; a coordinate reached by
float offset arithmetic stays float; a map with an irrational scalar yields
float. In every one of those the exact dyadic would be numerically identical
to the float, so no value would be lost — what would be lost is the library's
only way of saying "this was measured, not counted".

**The boundary is the scalar constructor**, and that phrasing is exact rather
than approximate, because it puts a value the caller did type on the derived
side:

```python
Coordinate(9.5, quarters)                          # Fraction(19, 2) — authored
timeline.get_timestamp(9.5).get_coordinate("clt1") # 9.5            — derived
```

Same literal, same unit, same caller, two representations. That is deliberate
and the tests pin it: a stamp's axis seeds every child coordinate, unit
conversion and interval taken from it, so coercing the axis would make a whole
cross-section read as exact on the strength of one approximate query. A float
query means "approximately here", and it has to survive the cross-section or
it means nothing.

A pleasant consequence: since a float prints as a decimal and a `Fraction`
prints as a ratio, the rendering now *shows* which regime a value came from.
`9.5 quarters` reads as measured; `19/2 quarters` reads as exact.

### Stamp currencies: the float lane and the exact lane

A stamp answers in two currencies, and which one a caller gets is a property
of the method rather than of the data. The tests pin both, because a method
that quietly switched lanes would be invisible until a dataframe column
turned into an object column or a conversion lost a third of a beat.

| Lane | Members | Why |
|---|---|---|
| **float** | `get()`, subscript (`stamp["id"]`, `stamp["quarters"]`), `to_dict()`, raw stamp-table columns | A uniform numeric currency that tables, dataframes and downstream arithmetic can rely on. An exact ratio here would turn a float column into an object column. |
| **exact** | `get_coordinate()`, `get_unit()`, conversion evaluation, `axis` | Carries whatever representation the coordinate actually has, so 160 ticks at 480 per quarter converts to exactly `Fraction(1, 3)` quarters rather than `0.3333333333333333`. |

Rendered output (`__str__`, `_repr_html_`) reads from the exact lane and
formats it for a human: that same conversion displays as `1/3 quarters`.
Non-numeric conversion outputs — labels, mappings — are not numbers in either
currency and pass through both lanes untouched.

**Interpolated values are float even on a fraction-canonical timeline.** An
interpolated position is an estimate between two anchors, so typing it as an
exact rational would claim the alignment pinned down something it did not. A
coordinate that lands exactly on an anchor keeps the axis's own
representation, because that one *is* claimed.

### `test_number_storage.py` - One struct, one canonical side, one builder

**Purpose:** Pins the storage contract every coordinate in the library rests
on, and the rules by which a source value becomes a stored one.

**The struct.** `{value: float64, numerator: int64, denominator: int64}`. Both
sides carry the number on every non-null row; a null sub-field means the whole
row is null. Which side is authoritative is declared per field, in
`number_type` metadata, and never inferred from the row.

**What the builder must produce.** Expected values are exact, never ranges:

| Input | `number_type` | Canonical side | Mirror |
|---|---|---|---|
| `0.1` | `float` | `0.1` | `3602879701896397/36028797018963968` |
| `1/3.0` | `float` | `0.3333333333333333` | `6004799503160661/18014398509481984` |
| `2.0` | `float` | `2.0` | `2/1` |
| `1.5` | `float` | `1.5` | `3/2` |
| the same four | `fraction` | the same four ratios | `float(ratio)`, bit-for-bit |
| `[1.4, 2.5, -0.6]` | `int` | `[1, 2, -1]`, all `den = 1` | the ints as floats |

The float mirrors are the **exact dyadic** ratios, because every finite double
is exactly one rational with a power-of-two denominator. Nothing here searches
for a tidier ratio nearby: `limit_denominator` has zero occurrences in the
library and the tests grep for it to keep it that way.

The `int` row settles ties on the even integer — `round(2.5) == 2`, Python's
own rule and PyArrow's `half_to_even`. This is asserted rather than assumed,
because the alternative (half-away-from-zero) drifts a column of `.5` values
consistently upwards, and a rounding rule that is only implicit is a rounding
rule nobody checks. Negative ties are pinned separately (`-2.5 → -2`,
`-1.5 → -2`, `-0.5 → 0`), since that is where the two conventions visibly
differ in sign and a positive-only probe would miss it.

All four modes are pinned, not just the default: for `[1.4, 2.5, -0.6]`,
`"floor"` gives `[1, 2, -1]`, `"ceil"` gives `[2, 3, 0]` and `"truncate"`
gives `[1, 2, 0]`. The same four names and the same `"round"` default apply
wherever the library makes a value integral, including `TimeScalar.to_int()`
— one vocabulary, one default, asserted in both places.

**The opt-in provenance flag.** `preserve_source_floats` keeps the incoming
floats on the float side of an `int` field instead of mirroring the stored
integer, so a cell can record what was measured beside what was stored:
`[1.4, 2.5]` stores numerators `[1, 2]` with `value` still `[1.4, 2.5]`.
It is construction-only — provenance floats do **not** survive arithmetic,
and a test asserts that adding zero rewrites them to exact mirrors
(`[1.0, 3.0]`). Otherwise a value that was never authoritative would
propagate as though it were.

**The vectorised path must equal the scalar path.** The builder takes a numpy
route for plain numeric columns and a per-value route for anything mixed,
textual or rational. The tests fuzz several thousand doubles — including the
sub-`2**-10` band where the exact dyadic denominator overflows int64 — and
assert the two routes agree cell for cell, and that the canonical float side
survives bit-for-bit in every case. Two implementations of one rule are two
chances to be wrong, so the equality is asserted rather than trusted.

**Where int64 runs out.** A double below roughly `2**-10` *may* need a
denominator past `2**62` — only the full-mantissa ones do, which is why the
fuzz test sees 362 of 10,009 rather than every sub-threshold value
(`2**-11` itself needs only 2048). Where it happens:

* the canonical float side always keeps the double untouched;
* the **mirror** falls back to `round(value * 2**62) / 2**62`, reduced.
  Worked example: `0.0001` is canonically `0.0001`, and its stored mirror is
  `461168601842739 / 4611686018427387904` — not `Fraction(0.0001)`, whose
  denominator is `2**66`;
* an **exact** field refuses the value outright rather than storing a
  degraded canonical side, and the error names `number_type float` as the
  place to put it. A canonical value is exact or it is an error; best effort
  belongs to mirrors only.

**The ceiling constrains storage, not retrieval.** Python `Fraction` is
arbitrary-precision, so `to_fraction()` and every as-fraction accessor
recompute the exact dyadic from the canonical float instead of reading the
stored mirror. Pinned directly: for `0.0001` the stored mirror is asserted to
be the approximation *and* `to_fraction()` is asserted to return the exact
`Fraction(0.0001)` anyway. Reading the mirror there would be a silent
exactness violation on precisely the values this limit identifies.

**Refusals.** An *exact* non-integral value entering an integer-valued field
raises — `Coordinate(Fraction(5, 24), TimeUnit.ticks)` is a unit mix-up, not a
rounding candidate, and rounding it to zero would bury the mistake somewhere
far from its cause. Inexact floats are made integral, because reading a tick
position off a float clock is exactly what rounding is for. `Duration` is
asserted alongside `Coordinate`: the rule lives on their shared base, so a gap
on one of them would be a design error rather than a missing branch.

**Conversion is the exception, deliberately.** Converting quarters to ticks at
a given resolution quantizes by definition, so `quantize_to_unit` rounds where
the constructor refuses. Tests assert both sides of that line, since a single
rule in both places would either forbid legitimate conversion or license the
silent rounding the refusal exists to prevent.

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
   - Frozen model (immutable): attribute assignment raises `pydantic.ValidationError`
   - Hashable (usable in sets/dicts)

2. **Conversion Tests** (9 tests)
   - `to_float()`, `to_int()`, `to_fraction()` methods
   - Type preservation and truncation behavior

3. **Property Tests** (8 tests)
   - `number_type` property (INT, FLOAT, FRACTION)
   - `domain` property (physical, logical, graphical)
   - Boolean values rejected at construction by the `value` field validator,
     which raises `TypeError` — asserted as the concrete class, not a bare
     `Exception`. (The `TypeError` propagates unwrapped because pydantic only
     re-wraps `ValueError`/`AssertionError` raised inside validators.)

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

### `test_score_scalars.py` - Circle 1 Score Scalars

**Purpose:** Validates construction and protocol conformance for the score-level
scalars `MidiPitch`, `SpecificPitch`, `Note`, `Measure`, and `DcmlHarmony`.

**Test Categories:** construction, protocol conformance (`GenericPitchLike`,
`NoteLike`, `MeasureLike`, `HarmonyLabelLike`, `DcmlHarmonyLike`,
`SemanticTypeLike`), `semantic_type`, `metadata_dict`, and immutability.

**Concrete exceptions:** each scalar is a frozen pydantic v2 `BaseModel`, so
mutating a field raises `pydantic.ValidationError` (message contains
`"frozen"`). The `test_frozen_immutable` cases assert `pytest.raises(
ValidationError)` — the concrete class, not a bare `Exception`.

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
   - C-Map conversion values assert exact `==`, not `pytest.approx`: the
     `TableMap` anchors (e.g. `[0,960]->[0,2]`, `[0,20]->[0,10]`) are exactly
     representable, so linear interpolation is bit-exact (480 ticks -> `1.0` s,
     1.5 s -> `720.0` ticks, child 10 -> `5.0` s).

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

   the C-Map visibility rule: timestamps surface the full
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

**Exact expected strings (zero-tolerance; the canonical ♯/♭ characters):**

Pitch scalars — `repr()` then `str()`:

| Scalar | construction | `repr()` | `str()` |
|--------|--------------|----------|---------|
| `EnharmonicPitchClass` | `(0)` | `EPC(C)` | `C` |
| `EnharmonicPitchClass` | `(1)` | `EPC(C♯/D♭)` | `C♯/D♭` |
| `GenericPitchClass` | `(0)` | `GPC(C)` | `C` |
| `GenericPitch` | `(0, 4)` | `GP(C4)` | `C4` |
| `SpecificPitchClass` | `(step="C", alter=1)` | `SPC(C♯)` | `C♯` |
| `EnharmonicPitch` | `(56)` (black) | `EP(G♯/A♭3)` | `G♯/A♭3` |
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
| `Note(start=0q, duration=1q, pitch=EnharmonicPitch(61))` | `C♯/D♭4 @0 quarters+1 quarters` |
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
   components and ignores the lossy float projection. Integer-valued float
   components from artifacts written by earlier releases are accepted and
   losslessly normalized to integers; fractional float components raise
   `ValueError` rather than being rounded.

**Validity Rationale:** A single owner plus a required version means a stored
table can always be interpreted, and a future payload change is a bump rather
than a guessing game. One rational struct means a reader never has to sniff
between two key spellings to recover an exact ratio.

---

### `test_wire_format.py` - The rational wire dict

**Purpose:** Pins the JSON wire format shared by every `to_dict` in the
library, and its boundary with the Arrow storage cell.

**Two shapes that look alike and are not the same thing.** A storage cell lives
in a column whose metadata declares which of its two sides is authoritative, so
the cell itself never has to say; both sides are always populated. A JSON value
— a map's offset, a claim's coordinate, a serialized timeline length — stands
alone with no schema beside it, so it carries its own answer instead:

```json
{"value": 3.3333333333333335, "numerator": 10, "denominator": 3}
```

`rational_to_wire` writes it and `wire_to_rational` reads it. A `Fraction`
keeps its exact ratio; anything else encodes as `{"value": x, "numerator":
null, "denominator": null}` and decodes back to a plain `float`. In the wire
dict — and **only** there — a null ratio is the marker of inexactness.

The tests assert both halves of that boundary, because collapsing them is the
tempting mistake in either direction: giving the wire dict a mandatory ratio
would turn every serialized float into an exact dyadic on read-back and change
what round-trips out of maps, timelines and claims; giving the storage cell an
optional one would put readers back to sniffing rows for a fact the schema
already knows.

Integer-valued float ratio members found in artifacts written by earlier
releases decode losslessly as integers; ratio members with a fractional part
are rejected and never rounded. `is_rational_wire` recognises the shape for the
few slots (a `ConstantMap` value) whose payload is genuinely open-ended.

There is exactly one encoding. `Fraction` objects are never emitted raw, and
the `"n/d"` strings the maps used to write are gone — `wire_to_rational`
rejects a string rather than parsing it, so a stale payload fails at the
boundary instead of decoding into a plausible wrong number.

### Coordinate cell rendering

`Coordinate.to_dict()` and `Duration.to_dict()` emit the **storage cell**, so
both sides are populated whatever the value's kind: an integer, a `Fraction`
and a float all come back with a `value`, a `numerator` and a `denominator`.
A float's ratio members are the exact dyadic of the double, which is a fact
about the double rather than a guess about what it meant. Null members appear
only in the JSON wire dict, which is a different encoding with a different
job — see `test_wire_format.py` above. Tests compare the complete
dictionaries and verify that `Note.to_dict()` and `Measure.to_dict()` embed
those cells unchanged.

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
2. **Immutability**: Frozen pydantic models are tested for mutation rejection;
   assignment raises `pydantic.ValidationError`, pinned as the concrete class
   (never a bare `Exception`)
3. **Type Safety**: Invalid types are verified to raise the concrete error
   class (`TypeError` for bad `Coordinate` value/unit types, including bool)
4. **Roundtrip**: Serialization/parsing operations preserve data exactly
