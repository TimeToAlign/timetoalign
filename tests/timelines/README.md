# Timeline Tests

This directory contains comprehensive tests for the `timetoalign.timelines` module,
which implements the central Timeline class and its 6 domain-specific subclasses.

## Test Coverage Summary

| Module | Coverage | Status |
|--------|----------|--------|
| `timelines/base.py` | 94% | Excellent |
| `timelines/types.py` | 100% | Complete |
| `timelines/mixins.py` | 100% | Complete |
| `timelines/beatgrid.py` | 95% | Excellent |
| `timelines/regions.py` | 94% | Excellent |

### Merged Score Event Coordinates

The score-timeline regression inspects the flattened Partitura event table
directly.  It counts populated ``start``, ``end``, and ``duration`` structs,
checks that every populated struct has an exact pair, and verifies that all
instant control and annotation rows keep null ``end`` and ``duration`` cells.

### `test_groups.py` - Timeline Groups

`TimelineGroup` and `GroupTimestamp` are timeline-layer concepts, so their tests
reside beside the timeline implementation. Boundary tests construct
`IdCoordinate` values to retain both the reference timeline and its unit; raw
`(coordinate, timeline_id)` pairs are intentionally outside the accepted
coordinate contract. Event aggregation tests assert `EventData` results because
the group preserves Arrow schemas, null-fills fields that are absent from some
member timelines, and adds a constant `timeline_id` provenance column. A member's
own `timeline_id` is overwritten by authoritative group membership. Columns
present in multiple members must retain the same Arrow type; incompatible types
raise an exact `ValueError` naming the column and both types, while genuinely
missing columns remain null-filled. DataFrame views are tested only through
`EventData.to_dataframe()`.

## Test Files

### `test_coordinate_resolution.py` - Public Coordinate Resolution

These tests pass foreign-unit coordinates through timeline entry points that
read or update events, regions, children, lengths, and slices. Each entry point
must delegate to the same coordinate resolver and preserve its exact missing
C-Map error, demonstrating that coordinate normalization is consistent across
the public timeline surface.

### `test_offset_arithmetic.py` - Nested Offset Arithmetic

These tests validate exact coordinate transfer between parents, children, and
deeper descendants. Parent-to-descendant lookup checks every embedding span,
while descendant-to-parent lookup and `get_coordinate()` compose all offsets
into the ancestor coordinate system. Integer and `Fraction` cases assert exact
results, unknown IDs retain their established return or exception behavior, and
timestamp cross-sections keep their left-inclusive, right-exclusive bounds.

### `test_fraction_generation.py` - Exact Logical Coordinate Generation

These tests generate fraction-typed metrical timelines and inspect the stored
PyArrow coordinate structs. Beat and measure event coordinates must retain the
exact numerator/denominator pairs derived from the musical positions, including
fractional positions such as `Fraction(3, 2)`. The tests also verify that
`Timeline.from_events()` preserves an exact maximum coordinate as the timeline
length. These assertions protect the rational fields that downstream alignment
and serialization use; the convenience float field alone is not sufficient.

### `test_fraction_engines.py` - Exact Coordinate Propagation

These tests exercise exact coordinate handling across nested timelines and
segment-based copies. Event coordinates entered as `Fraction` values are
stored as Arrow coordinate structs with a float projection and an authoritative
numerator/denominator pair. When an event is shifted by a child offset or a
segment start, the tests assert the resulting `Fraction` values and the exact
stored pairs, so the float projection and rational pair are updated together.

The event checks also reject any returned coordinate struct whose float value
does not equal the value represented by its pair. This protects both the
single-event lookup path and the bulk event path, including instant and
interval coordinate fields. Segment extraction and region-based child creation
are checked independently: each must subtract the exact segment or region
start while preserving the resulting rational representation in the copied
event data.

The timestamp checks distinguish the two public surfaces: `Stamp.get()`
continues to return a raw float, while `get_coordinate()` returns the exact
`Fraction` represented by a stored coordinate for a fraction-typed timeline.
An interpolated timestamp remains marked with `is_interpolated=True` and is
allowed to expose a float because interpolation is inherently float-based.

### `test_base.py` - Core Timeline Functionality

**Purpose:** Validates the fundamental Timeline contract and behavior.

**Test Categories:**

1. **Construction Tests** (12 tests)
   - Empty timeline creation with defaults
   - Timeline with explicit length, unit, number_type
   - Custom ID vs auto-generated ID
   - Locked state on creation
   - Factory methods: `from_events()`, `from_event_store()`
   - The experimental base class remains available as an explicit
     `create_child(..., child_class=Timeline)` override

2. **Coordinate Factory Tests** (6 tests)
   - `make_coordinate()` preserves value types (int, float, Fraction)
   - Origin is always zero
   - Start/end property aliases

3. **Event Management Tests** (9 tests)
   - Adding instant events, interval events, mixed events
   - `get_events()` filtering by temporal_type, event_type
   - Segment events excluded by default

4. **Length and Expansion Tests** (7 tests)
   - Length can expand (unlocked)
   - Length cannot contract below content
   - Auto-expansion behavior
   - `allow_expansion` override for locked timelines

5. **Locking Tests** (4 tests)
   - Default unlocked state
   - Children become locked
   - Locked timelines reject expansion

6. **Serialization Tests** (5 tests)
   - `to_dict()` / `from_dict()` roundtrip; `to_dict()` omits events by
     default, so the event-bearing cases pass `events=True` explicitly
     (see `test_external_references.py` for the full flag matrix)
   - Children serialized recursively
   - Segment events regenerated on deserialization
   - Base-class deserialization dispatches the serialized ``class`` tag through
     the timeline-type registry, preserving each concrete timeline type and
     rejecting calls through a mismatched concrete subclass
   - Duplicate serialized class tags reject registration by a different class;
     registering the already-recorded class remains idempotent
   - `length` and every child `offset` are emitted as the **rational wire
     dict** (`{value, numerator, denominator}`), the one JSON encoding of a
     rational number in this library; the same shape carries the event
     coordinates, so a `Fraction` timeline serializes to JSON and comes back
     exact. The format and its fixpoint guarantee are specified in
     `tests/core/README.md` (`test_wire_format.py`), which also holds the
     exact-value tests for timeline lengths, offsets, and BeatGrid.

7. **Magic Methods Tests** (5 tests)
   - `__len__`, `__repr__`, `__str__`, `__contains__`

8. **Future API Stubs Tests** (2 tests)
   - `add_conversion_map()`, `convert_to()` raise `NotImplementedError`
9. **Performance Tests** (2 tests)
   - Adding 10,000 events: < 5 seconds
   - Creating 1,000 timelines: < 2 seconds

**Validity Rationale:**

These tests verify the fundamental Timeline contract:
- A Timeline is a positive coordinate axis with an origin (zero) and measuring unit
- Events are stored efficiently in an EventStore (PyArrow-backed)
- Timelines can expand (if unlocked) but cannot contract below content
- Coordinates are validated against the timeline's unit

---

### `test_external_references.py` - Incoming External References and `to_dict()` Flags

**Purpose:** Validates the per-timeline table of *incoming* external
references — annotations living outside TimeToAlign that point **at** this
timeline's events — and the serialization flags that decide whether events
and references appear in `to_dict()` output.

**Test Categories:** schema (12 tests), adding and normalization (12),
malformed-row rejection (12), event-id validation (10), the `to_dict()` flag
matrix (12), child forwarding (6), `from_dict` tolerance (5), and round-trip
(7) — 76 tests in total.

#### Canonical Arrow schema

`Timeline.external_references` always returns a `pa.Table`, never `None`.
An untouched timeline returns a zero-row table carrying exactly this schema:

| column | Arrow type | nullable |
|---|---|---|
| `event_id` | `string` | no |
| `external_id` | `string` | no |
| `access_points` | `list<struct<uri: string, kind: string>>` | no |
| `comment` | `string` | yes |

`event_id` names an event of *this* timeline; `external_id` is the identifier
the annotation carries inside the external resource; `access_points` holds the
locators that resolve that resource, with `kind` an open vocabulary
(`"relative_path"` and `"url"` are the usual values, but any string is
accepted). The access-point list may be empty, but the cell is never null.
Both struct fields are non-nullable. The tests assert the schema field by
field, including nullability, so a silent type drift fails.

#### `add_external_references()` normalization

Rows may be given as dicts or as a `pa.Table`; a table is read through
`to_pylist()` so both inputs follow one validation path. Per row:

- `access_points` omitted or `None` → stored as `[]`.
- `comment` omitted → stored as `None`.
- Unknown columns raise `ValueError` naming every unknown key. Unknown keys
  inside an access point raise `ValueError` the same way.
- `event_id` and `external_id` must be `str`; `comment` must be `str` or
  `None`; `uri` and `kind` must both be `str`. Anything else raises
  `ValueError` naming the row index and the offending field.
- A non-mapping row, or a non-mapping access point, raises `TypeError`.

Calls append: two calls of one row each and one call of two rows produce the
same two-row table. The method returns `self`, so calls chain.

#### Validation `KeyError` contract

With `validate=True` (the default) every `event_id` must appear in this
timeline's **own** event table (`Timeline.events`) — child events do not
count, because the column is defined as an event of this timeline. When one
or more ids are absent the call raises `KeyError` whose message names **all**
missing ids, sorted and quoted, in a single message of the form:

```
Timeline 'spine' has no event(s) with id: 'ghost_a', 'ghost_b'
```

Validation runs before anything is appended, so a rejected call leaves the
table byte-for-byte unchanged. `validate=False` skips the check entirely and
accepts ids that name no event — the escape hatch deserialization uses.

#### `to_dict()` flag matrix

`to_dict(*, events: bool = False, external_references: bool = False)`. Both
keys are **absent** unless requested; requesting `external_references` emits
the key even when the table is empty. The four combinations are asserted
exactly:

| `events` | `external_references` | `"events"` key | `"external_references"` key |
|---|---|---|---|
| `False` | `False` | absent | absent |
| `True` | `False` | present | absent |
| `False` | `True` | absent | present (may be `[]`) |
| `True` | `True` | present | present |

The remaining keys are identical in all four cases: `id`, `name`, `class`,
`unit`, `number_type`, `length`, `locked`, `meta`, `children`,
`conversion_maps`. The tests assert that exact key set for the default call.

Reference rows serialize as plain dicts with `access_points` a nested list of
`{"uri": ..., "kind": ...}` dicts, so the payload is JSON-safe; JSON safety of
the whole timeline payload is covered by `tests/core/test_wire_format.py`.

#### Child flag forwarding

`children` recursion forwards **both** flags unchanged. A parent serialized
with `events=True, external_references=False` yields children that carry
`"events"` and lack `"external_references"`, and so on for every combination.
The tests check a two-level hierarchy (parent → child → grandchild) so
forwarding is verified through more than one recursion step. Each level emits
its own rows: a reference added to the child appears in the child payload
only. An `"events"` list also carries the `Segment` bookkeeping event that
`add_child()` records — the expected ids spell it out, since `from_dict()`
skips and regenerates it.

#### Round-trip

`from_dict()` tolerates absent `"events"` and `"external_references"` keys: a
default payload reconstructs a timeline with zero events and an empty
reference table, and the structural fields (id, length, children, offsets,
conversion maps) still round-trip. When `"external_references"` is present it
is restored with `validate=False`, so a payload carrying references but no
events round-trips intact — the restored table equals the original via
`pa.Table.equals`. Re-serializing with the same flags reproduces the input
dictionary (the fixpoint guarantee stated in `tests/core/README.md`).

The rational wire format for `length`, child `offset`s, and event coordinates
is untouched by these flags.

`to_typed()` carries the reference table over to the re-typed instance; Arrow
tables are immutable, so the same table object is shared.

**Validity Rationale:**

The direction is deliberately incoming: a timeline records what points at it,
never what it points to, so any number of independent external tools can
annotate the same events without the timeline knowing about them. Keeping the
table on the Timeline base class (an engine mixin, like events and regions)
means every timeline in a hierarchy carries its own references, addressed by
its own event ids. Slimming `to_dict()` keeps structural serialization cheap
for large hierarchies, where the event rows dominate the payload; callers that
need contents opt in.

---

### `test_nesting.py` - Child Timeline (Segment) Tests

**Purpose:** Validates hierarchical timeline nesting and traversal.

**Test Categories:**

1. **Child Validation Tests** (5 tests)
   - Matching units accepted
   - Mismatched units rejected
   - Non-Timeline objects rejected
   - Duplicate children rejected
   - Negative offsets rejected

2. **Adding and Appending Children Tests** (13 tests)
   - Basic child addition
   - Offset storage and retrieval
   - Child locking upon embedding
   - Segment event creation in parent's EventStore
   - Auto-expansion of parent
   - Multiple children
   - `append_child()` requires an unlocked parent, reports the exact standard
     lock error, preserves keyword-only identity arguments, and places a named
     child at the previous end while expanding the parent
   - `append_segment()` uses the same lock gate when its SegmentLine is already
     embedded as a child

3. **Get Child Tests** (4 tests)
   - Retrieve child by ID
   - Retrieve offset by ID
   - KeyError for nonexistent children

4. **Iteration Tests** (9 tests)
   - Empty timeline iteration
   - Sorted order (by offset)
   - Breadth-first traversal
   - Depth-first traversal
   - `include_self` parameter
   - `recursion_limit` parameter
   - Absolute offset calculation

5. **Unit Validation Tests** (4 tests)
   - Logical cannot contain physical
   - Physical cannot contain logical
   - Same domain, different units rejected

6. **Performance Tests** (2 tests)
   - Adding 1,000 children: < 10 seconds
   - Iterating depth-100 hierarchy: < 1 second

7. **Cross-Unit Child Addition via Conversion Map** (11 tests)
   - `use_conversion_map=True` auto-selects parent's C-Map (e.g., SamplesToSeconds)
   - Converted child ID is `{original}[{parent_unit}]` (e.g., `notes[samples]`)
   - Event coordinates correctly converted (seconds → samples via inverse C-Map)
   - Original child is NOT modified or locked (only the derived copy is locked)
   - Lookup by string target unit name (`use_conversion_map="seconds"`)
   - Direct `ConversionMap` object accepted
   - Without `use_conversion_map`, unit mismatch still raises `ValueError`
   - `use_conversion_map=True` raises when no matching C-Map attached
   - Same-unit child passes through unchanged (no `[unit]` suffix)
   - `allow_expansion=True` works with unit conversion
   - Converted copy is locked, original is not

8. **Segment Duration Exactness Tests** (2 tests)
   - `add_child` records the segment event's `duration` from the child's
     `length`. When both the segment's `start` and `end` carry an exact
     ratio (`numerator`/`denominator` populated, i.e. an int or `Fraction`
     coordinate), `duration` is recomputed via exact `Fraction` arithmetic
     rather than a float `end - start` subtraction, so an integral length
     (`Fraction(2, 1)`) and a non-integral one (`Fraction(7, 3)`) both
     round-trip through `parent.to_dict()["events"][0]["duration"]` as the
     exact rational wire dict (`rational_to_wire`) for the child's length —
     not a rounded float projection.

9. **Child Construction and Boundary Tests**
   - `create_child()` defaults its offset to zero and returns the parent's
     exact concrete class for all six concrete timeline types
   - Coordinate objects remain valid for child lengths and offsets
   - BeatGrid children and slices are `ContinuousLogicalTimeline` instances
     because they represent plain logical material rather than new grids
   - `create_children_from_boundaries()` creates named, contiguous children
     that tile the parent exactly, supports explicit names, and reports the
     same boundary-validation errors as `create_regions_from_boundaries()`

**Validity Rationale:**

The TTA model specifies that timelines can contain nested "children" (segments)
that share the same coordinate type. These tests verify:
- Children must have matching units (type safety)
- Children are locked upon embedding (immutability)
- Children appear as interval events in the parent's EventStore
- Traversal orders work correctly for hierarchical access
- Cross-unit nesting works via C-Map inversion (e.g., EEP notes in seconds
  added as child of audio DPT in samples, using `SamplesToSeconds` inverse)

---

### `test_types.py` - Domain-Specific Timeline Subclasses

**Purpose:** Validates the 6 timeline types (3 domains x 2 modalities), the
dynamic `SegmentLine[T]` class family, and timeline serialization dispatch.

**Timeline Types:**

| Type | Domain | Modality | Default Unit | Default Number Type |
|------|--------|----------|--------------|---------------------|
| `ContinuousLogicalTimeline` | Logical | Continuous | quarters | Fraction |
| `DiscreteLogicalTimeline` | Logical | Discrete | ticks | int |
| `ContinuousPhysicalTimeline` | Physical | Continuous | seconds | float |
| `DiscretePhysicalTimeline` | Physical | Discrete | samples | int |
| `ContinuousGraphicalTimeline` | Graphical | Continuous | centimeters | float |
| `DiscreteGraphicalTimeline` | Graphical | Discrete | pixels | int |

**Test Categories:**

1. **Parametrized Type Tests** (24 tests, 4 per type)
   - Default unit is valid
   - Default number_type is valid
   - Domain derived correctly
   - Can hold events

2. **Logical Timeline Tests** (8 tests)
   - Allowed units (beats, quarters, measures, ticks, number)
   - Continuous accepts float/Fraction, rejects int
   - Discrete accepts int only, rejects float
   - Continuous rejects ticks, Discrete rejects quarters

3. **Physical Timeline Tests** (8 tests)
   - Allowed units (seconds, milliseconds, minutes, samples, frames)
   - Continuous accepts float/Fraction, rejects int
   - Discrete accepts int only
   - Unit restrictions enforced

4. **Graphical Timeline Tests** (8 tests)
   - Allowed units (pixels, meters, cm, mm, inches, points)
   - Similar pattern to other domains

5. **Domain Property Tests** (3 tests)
   - Each domain class returns correct Domain enum

6. **Inheritance Tests** (6 tests)
   - All concrete types inherit from correct base classes

7. **Cross-Domain Compatibility Tests** (3 tests)
   - Logical cannot contain physical
   - Physical cannot contain graphical
   - Graphical cannot contain logical

8. **Parameterized SegmentLine and Serialization Tests**
   - Repeated parameterization returns the identical cached class
   - Dynamic classes inherit the APIs and restrictions of both `SegmentLine`
     and their timeline parameter
   - Invalid and repeated parameterization raises `TypeError`
   - Nested class tags resolve recursively and preserve exact error messages
   - Pickle reconstructs dynamic classes by module reference
   - Captured 1.0.1 payloads deserialize to the same nested structure
   - `to_typed()` recursively re-types children and retains exact classes

**Validity Rationale:**

TimeToAlign defines 6 timeline types across 3 domains (Logical, Physical,
Graphical) and 2 modalities (Continuous, Discrete). Each type has:
- Restricted allowed units (domain-specific)
- Appropriate default unit and number_type
- Consistent behavior with base Timeline

---

### `test_beatgrid.py` - Metrical Timeline (BeatGrid)

**Purpose:** Validates the BeatGrid specialized timeline for metrical structure.

**BeatGrid Specification:**

| Property | Value |
|----------|-------|
| Base Class | `ContinuousLogicalTimeline` |
| Unit | `quarters` (fixed) |
| Number Type | `Fraction` (for exact rhythmic representation) |
| Built-in C-Maps | `measure_map`, `beat_map`, `metrical_map` |

**Test Categories:**

1. **Basic Tests** (6 tests)
   - Default initialization (4/4 time, quarter-note beat)
   - Invalid beats_per_measure (< 1) raises ValueError
   - Invalid beat_unit (<= 0) raises ValueError
   - 4/4 time: 4 quarters per measure, 4 beats per measure
   - 3/4 time: 3 quarters per measure, 3 beats per measure
   - 6/8 time: 3 quarters per measure (6 eighth-note beats = 3 quarter-note beats)

2. **Metrical Map Tests** (5 tests)
   - `measure_at()`: Returns 1-indexed measure number
   - `beat_at()`: Returns 1-indexed beat within measure (cyclic)
   - `metrical_position()`: Returns `{"measure": N, "beat": B}` dict
   - `quarter_at()`: Inverse lookup (measure, beat) -> quarter coordinate
   - `quarter_at()` validation: Rejects measure < start_measure, beat < 1
    - Public coordinate queries preserve native `Fraction` values, convert
      foreign-unit coordinates through attached C-Maps, and reject missing maps
    - `beat_at()` returns exact `Fraction` values; callers can explicitly convert
      the result to `float` when needed
    - 6/8 and 2/2 beat queries scale quarter offsets by `quarters_per_beat`:
      in 6/8, quarter 1/2 is beat 2 and quarter 5/2 is beat 6; in 2/2,
      quarter 2 is beat 2
    - Serialization rebuilds BeatGrid's attached meter maps from its metrical
      construction parameters, preserving anacrusis labels and tempo state
    - `to_dict()` excludes the three metrical maps (meter/beat/metrical) from
      the serialized `conversion_maps` list, since `from_dict()` rebuilds them
      from construction parameters instead; a plain grid serializes an empty
      list, a `from_tempo` grid serializes exactly its tempo map, and any
      user-attached map is serialized and restored via `ConversionMap.from_dict`
      alongside it

3. **Materialization Tests** (4 tests)
   - `materialize_beats()`: Creates Beat instant events at each beat position
   - `materialize_beats(include_downbeats_only=True)`: Only beat 1
   - `materialize_measures()`: Creates Measure interval events
   - Partial measures at end handled correctly

4. **Factory Method Tests** (4 tests)
   - `from_tempo(length_quarters=...)`: Length specified in quarters
   - `from_tempo(length_seconds=...)`: Length converted via tempo
   - `from_tempo()` creates tempo C-Map (quarters -> seconds)
   - Validation: Must provide exactly one of length_seconds or length_quarters

5. **Cross-Domain Relationship Tests** (2 tests)
   - BeatGrid relates to physical timelines via C-Maps (not as child)
   - `start_measure` offset for non-default numbering

6. **SUPRA Validation Tests** (10 tests)
   - **Purpose:** Validate against SUPRA reference data (Wagner Meistersinger Prelude)

**SUPRA Validation Details:**

The SUPRA tests use the Wagner Meistersinger Prelude as a gold standard reference:

| Parameter | Value | Source |
|-----------|-------|--------|
| Total Length | 888 quarter notes | DCML score annotation |
| Time Signature | 4/4 throughout | Score metadata |
| Total Measures | 222 | 888 / 4 = 222 |
| First Beat | 1.3 seconds (approx) | Audio alignment |
| Last Measure End | ~2 seconds before audio end | Audio alignment |

**SUPRA Test Cases:**

1. **Basic Dimensions**: length=888, n_measures=222, quarters_per_measure=4
2. **Measure Boundaries**: Measure 1 @ quarter 0, Measure 222 @ quarter 884
3. **All Measure Starts**: Exactly 222 distinct measure numbers (1-222)
4. **Beat Positions**: All quarters map to beats 1.0, 2.0, 3.0, or 4.0
5. **Reverse Lookup**: `quarter_at(m, b)` correctly inverts `measure_at()` + `beat_at()`
6. **Round Trip**: `quarter_at(measure_at(q), beat_at(q)) == q` for all positions
7. **Tempo Derivation**: At 120 BPM, 888 quarters = 444 seconds
8. **Array Operations**: Vectorized measure_at/beat_at produce correct arrays
9. **Metrical Position Array**: Combined (measure, beat) tuple output
10. **Event Materialization**: Creates exactly 888 beat events, 222 measure events

**Validity Rationale:**

BeatGrid is a proper ContinuousLogicalTimeline, not a utility wrapper:
- **It IS a timeline** with its own coordinate system (quarters in Fractions)
- **It can hold events** (Beat, Measure events via materialization)
- **It has built-in C-Maps** for metrical conversion
- **It works as a child** of any compatible parent timeline

The SUPRA validation proves the implementation against real-world musical data.
If BeatGrid correctly handles 888 quarters across 222 measures for Wagner's
Meistersinger Prelude, it will handle any standard Western musical content.

**Cross-Domain Relationships:**

Per the TTA model, children must share the parent's measuring unit. A BeatGrid
(in quarters) cannot be a direct child of a physical timeline (in seconds).
Instead, cross-domain relationships are established via:
- **C-Maps**: The tempo map converts quarters to seconds
- **Alignment Anchors**: Match objects link events across domains

---

### `test_maps_integration.py` - Conversion Maps on Timelines

**TableMap honesty (`TestTableMapHonesty`):** `add_conversion_map` used to
wrap every `TableMap` in an `InterpolationMap`, silently converting its
interpolation `kind` to linear and every `extrapolate` policy to linear
extrapolation — a timestamp could contradict the very map attached to the
timeline. Maps are now stored directly, so the tests pin the honest
behaviour end-to-end: `kind='previous'` step values survive to
`get_unit()`; `extrapolate='error'` raises for out-of-bounds coordinates;
`extrapolate='constant'` clips to the exact boundary value. All assertions
are exact — no `pytest.approx`.

**Timeline + MetricMap round trip
(`TestTimelineSerializationWithMeterMap`):** `ConversionMap.from_dict`
previously dispatched through a hand-written table that omitted the meter
maps, so `Timeline.from_dict()` raised `ValueError: Unknown map type:
MetricMap` for any timeline carrying one. The registry is now populated by
`__init_subclass__`; the test attaches a `MetricMap`, round-trips through
`Timeline.to_dict`/`from_dict`, and asserts `meter(4.0) == 2` exactly.

---

### `test_integration.py` - Loader Integration Tests

**Purpose:** Validates Timeline integration with EventStore and loaders.

**Test Categories:**

1. **EventStore Integration** (3 tests)
   - Timeline from empty EventStore
   - Timeline from populated EventStore
   - Unit/number_type preservation

2. **MIDI Loader Integration** (4 tests)
   - Performance MIDI to Timeline
   - Score MIDI to Timeline
   - Nested MIDI timelines
   - Real file benchmarks

3. **Score Loader Integration** (2 tests)
   - Note events from score
   - Combined score data

4. **Complex Hierarchy Tests** (2 tests)
   - Multi-level nesting with events at each level
   - Serialization roundtrip of complex hierarchies

5. **Performance Integration** (2 tests)
   - 50,000 events to Timeline: < 5 seconds
   - Real MIDI file loading benchmark

6. **Edge Cases** (4 tests)
   - Empty event list
   - Instant-only events
   - Interval-only events
   - Zero-duration intervals

**Validity Rationale:**

The Timeline class must integrate seamlessly with the loader infrastructure:
- Events from EventStore can populate Timelines
- Multiple sources can be combined hierarchically
- Real-world test data produces valid timelines

---

## Profiling Results

Performance benchmarks are collected via the `profiler` fixture and reported
at the end of test sessions. Key benchmarks:

| Operation | Target | Actual |
|-----------|--------|--------|
| Add 10,000 events | < 5s | ~0.5s |
| Create 1,000 timelines | < 2s | ~0.1s |
| Add 1,000 children | < 10s | ~3s |
| Iterate depth-100 | < 1s | ~0.01s |
| Timeline from 50k events | < 5s | ~1s |

---

## Running Tests

```bash
# Run all timeline tests
pytest tests/timelines/ -v

# Run with coverage
pytest tests/timelines/ --cov=timetoalign.timelines --cov-report=term-missing

# Run specific test file
pytest tests/timelines/test_base.py -v

# Run performance tests only
pytest tests/timelines/ -v -k "performance"
```

---

### `test_timeline_relationships.py` - Unified Verb×Noun API, Regions, SegmentLine, derive()

**Purpose:** Validates the unified verb×noun Timeline API (Phases A-D) plus TTA
architecture harmonization features that distinguish between different timeline
relationship concepts.

**~170 tests**, including 13 real-data tests using Wagner Walküre Act III
measures.

**TimeToAlign Concepts Tested:**

| Concept | Definition | Test Category |
|---------|------------|---------------|
| **Region** | A named TimeInterval (NOT a timeline) | `TestRegionDataclass`, `TestTimelineRegionManagement` |
| **Child** | A timeline nested in a parent (same unit) | `TestCreateChildFromRegion`, `TestCreateChildrenFromRegions` |
| **Segment** | A Child that is contiguous with siblings | `TestSegmentLineBasics` |
| **SegmentLine** | A parent where ALL children are Segments | `TestCreateSegmentLine`, `TestCreateSegmentLineFromRegions` |
| **Derivative** | A new timeline created via C-map (different unit) | `TestTimelineDerive` |

**Unified Verb×Noun API Methods (new):**

| Verb | Region | Child | SegmentLine |
|------|--------|-------|-------------|
| `create_` | `create_region()`, `create_regions_from_boundaries()`, `create_regions_by_grouping()`, `create_regions_by_splitting()` | `create_child_from_region()`, `create_children_from_regions()` | `create_segment_line()`, `create_segment_line_from_regions()`, `create_segment_line_by_grouping()`, `create_segment_line_by_splitting()` |
| `get_` | `get_region()`, `get_regions_at()` | `get_children_at()` | — |
| `has_` | `has_region()` | `has_child()` | `has_segment()` |
| `list_` | `list_regions()` | `list_children()` | `list_segments()` |
| `add_` | `add_region()` (overloaded) | — | — |

**Removed Methods:** `partition()`, `region_to_child()`, `get_region_object()`.

**Changed Methods:** `get_region()` now returns `Region` object (was dict), raises
`KeyError` if not found (was `None`). `__contains__` now checks regions AND children.

**Test Categories:**

1. **Region Dataclass Tests** (9 tests)
   - Creation with name, start, end, meta
   - Duration computation (end - start)
   - as_interval property (tuple)
   - contains() follows [start, end) convention (left-inclusive, right-exclusive)
   - overlaps() detection
   - Rejects end < start
   - Rejects mismatched units
   - Immutability (frozen dataclass)

2. **Timeline Region Management Tests** (12 tests)
   - add_region() returns Region object
   - get_region() returns Region object (updated from dict)
   - get_region() raises KeyError if not found (updated from None)
   - has_region(), iter_regions(), list_regions()
   - n_regions property
   - Duplicate name rejection
   - **Region creation succeeds on a locked timeline.** Length-locking guards
     a timeline's own coordinate contract with its parent (`set length`), not
     the addition of named annotations within the existing coordinate space.
     Regions are pure annotations that change nothing structural — they are
     strictly less structural than children, and child creation is already
     unguarded on a locked timeline. So `add_region`, `create_region`,
     `create_regions_from_boundaries`, and `create_regions_by_splitting` all
     succeed on a `locked=True` timeline with exact bounds/names: `add_region`
     and `create_region` produce the requested `[start, end)` region;
     `create_regions_from_boundaries([0, 40, 100], prefix="sec")` yields
     `sec_1 [0, 40)` and `sec_2 [40, 100)`; and
     `create_regions_by_splitting("breaks", prefix="mov")` on an event-free
     timeline yields the single whole-span region `mov_1 [0, 100)`. (Distinct
     from `create_child_from_region`, which remains lock-guarded — see the
     create_child_from_region group below.)

3. **Phase A — create_region() / add_region() overloaded** (5 tests)
   - `create_region(name, start, end)` creates and registers a Region
   - `add_region(Region)` accepts existing Region object
   - `add_region(name, start, end)` backwards-compatible string overload

4. **Phase A — create_regions_from_boundaries()** (5 tests)
   - Creates N-1 regions from N boundary coordinates
   - Names follow configurable format pattern
   - Validates sorted, non-negative boundaries

5. **Phase A — create_regions_by_grouping()** (6 tests)
   - Groups adjacent events by field value
   - Auto-disambiguates recurring group values (e.g., 4/4 → 3/4 → 4/4)
   - Supports custom `name_format` with `{value}` and `{run}` placeholders
   - Raises ValueError for missing field

6. **Phase A — create_regions_by_splitting()** (5 tests)
   - Splits at events matching a predicate (field name or dict filter)
   - Supports `include_before_first` and `include_after_last`
   - Deduplicates split points at timeline boundaries

7. **Phase B — create_child_from_region()** (7 tests, replaces old partition())
   - Creates child at region's offset
   - Copies events within region to child
   - Adjusts event coordinates relative to child origin
   - copy_events=False creates empty child
   - Raises KeyError for nonexistent region
   - Raises RuntimeError on locked timeline

8. **Phase B — create_children_from_regions()** (3 tests)
   - Creates children for all or specified regions
   - Returns list of created children

9. **Phase B — get_regions_at() / get_children_at()** (6 tests)
   - `get_regions_at(coord)` returns all regions containing that coordinate
   - `get_children_at(coord)` returns all children whose span includes that coordinate

10. **Phase B — list_children() / has_child()** (4 tests)
    - `list_children()` returns sorted list of child IDs
    - `has_child(id_or_obj)` checks by string or Timeline object

11. **Phase C — create_segment_line()** (4 tests)
    - Creates SegmentLine from boundary coordinates
    - Does NOT modify source timeline
    - Returns `SegmentLine[type(source)]` with the source timeline API

12. **Phase C — create_segment_line_from_regions()** (3 tests)
    - Creates SegmentLine from contiguous regions
    - Validates contiguity

13. **Phase C — create_segment_line_by_grouping()** (3 tests)
    - Shortcut: groups events and creates SegmentLine directly
    - Does NOT add intermediate regions to source

14. **Phase C — create_segment_line_by_splitting()** (3 tests)
    - Shortcut: splits and creates SegmentLine directly

15. **Phase C — SegmentLine list_segments() / has_segment()** (5 tests)
    - `list_segments()` returns ordered segment IDs
    - `has_segment()` checks by ID or object
    - `__contains__` override on SegmentLine checks segments

16. **Phase D — __contains__ checks regions AND children** (4 tests)
    - String `in tl` checks region names AND child IDs
    - Region object `in tl` checks by name
    - Timeline object `in tl` checks by identity

17. **SegmentLine Basics and Casting Tests**
    - Empty creation
    - append_segment() adds contiguous children
    - Segment offsets form contiguous sequence
    - Rejects non-contiguous offsets
    - First segment must start at 0
    - get_segment_by_index()
    - get_segment_at() finds segment by coordinate
    - `is_segment_line()` uses exact structural coverage, including
      zero-length children, and rejects an empty child collection
    - `as_segment_line()` preserves content while enforcing contiguity and a
      homogeneous child class
    - `to_timeline()` removes segment enforcement without losing content
    - Boundary-created children make the parent structurally segmentable;
      casting returns the parent's concrete dynamic SegmentLine class with the
      exact child count, names, and offsets
    - A SegmentLine nested beneath a parent renders as one collapsed child row,
      without rendering each of its segments as additional rows

18. **SegmentLine from_segmentation Tests**
    - Creates correct number of segments
    - Segments have correct lengths
    - Copies events to respective segments
    - Requires at least 2 split coordinates
    - Fails if source has existing children
    - Rejects invocation through a parameterized class whose parameter differs
      from the source's exact class

19. **Timeline.derive() Tests** (8 tests)
    - Creates timeline in target unit
    - Creates correct Timeline subclass for domain
    - Attaches inverse C-map for roundtrip
    - Roundtrip accuracy verification
    - Raises ValueError without C-map
    - Uses custom name if provided
    - copy_events=True copies and converts events
    - copy_events=False (default) creates empty timeline

20. **get_timeline_class() Tests** (7 tests)
    - Returns correct class for all 6 domain/modality combinations
    - Raises ValueError for unknown domain

21. **get_events_at() Tests** (10 tests)
    - Returns instant events at exact coordinate
    - Uses tolerance for instant matching
    - Interval left-inclusive (start included)
    - Interval right-exclusive (end excluded)
    - Interval middle coordinates included
    - Includes events from children
    - include_children=False excludes child events
    - Returns dict keyed by timeline ID
    - Returns empty dict when no match
    - Accepts Coordinate object input

22. **Real Data Tests (Ms3Loader)** (13 tests)
    - See "Real Data Validation" section below

23. **Integration Tests** (3 tests)
    - Regions used to create SegmentLine structure
    - Derived timeline can have children added
    - SegmentLine with individual segment C-maps

**Validity Rationale:**

TimeToAlign concepts validated here:
- A Region is a named part of a timeline that is defined by a TimeInterval.
- When all Children of the same parent timeline are contiguous, they are
  Segments and the parent is a SegmentLine.
- A ConversionMap implies the presence of a derived timeline in the target unit.

These tests ensure:
1. Region is NOT a Timeline (immutable dataclass, no events/C-maps)
2. SegmentLine enforces strict contiguity (no gaps/overlaps)
3. derive() creates proper cross-domain relationships via C-maps
4. Inverse C-maps enable accurate roundtrip conversions
5. get_events_at() enables point-in-time queries following [start, end) interval semantics
6. Coordinate errors propagate across event range filters, point queries,
   region and child lookups, length assignment, region creation, and
   `SegmentLine.get_slice()`
7. The unified verb×noun API provides consistent naming across all noun types
8. Real data from Ms3Loader validates the API against production musicological data
9. Dynamic SegmentLine classes preserve both segment behavior and the complete
   API of their parameter timeline class

---

### Real Data Validation (`TestUnifiedAPIWithRealData`)

**Purpose:** Validates the unified verb×noun API using real musicological data from
Wagner's Walküre Act III (measures.tsv loaded via Ms3Loader).

**Test Data Provenance:**

| Property | Value | Source |
|----------|-------|--------|
| File | `Wagner_WWV086B-3.measures.tsv` | DCML Ms3 corpus (MuseScore annotation) |
| Location | `tests/data/score/wagner_walkure/01_RawData/score_musescore/` | |
| Total Measures | 1733 | Exact count from TSV rows |
| Timeline Length | 6699.5 quarter beats | Computed from last event end coordinate |
| Unique Time Signatures | 8 (`9/8`, `3/4`, `2/2`, `12/8`, `2/4`, `4/4`, `6/4`, `6/8`) | TSV `timesig` column |
| Adjacent Timesig Runs | 22 | Adjacent-grouping count |
| Break Events | 405 (347 line + 58 page, 0 section) | TSV `breaks` column |
| All Break Coordinates | 405 unique | Verified no duplicate end coordinates |

**Fixture Strategy:**

The `wagner_timeline` fixture uses `MeasureData.create_timeline()` which directly
assigns the MeasureData as the timeline's event store. This preserves all 32 fields
(including `timesig`, `breaks`, `keysig`) that the base `EventData.from_dicts()`
would discard (it only keeps the 7 base schema fields). Each test invocation
creates a fresh `Ms3Loader` instance, ensuring no shared state between tests.

**Gold Standard Counts (all EXACT, no approximations):**

| Test | Assertion | Value | Derivation |
|------|-----------|-------|------------|
| `test_event_count` | `n_events` | 1733 | TSV row count |
| `test_create_regions_by_grouping_timesig` | region count | 22 | Adjacent-run counting on timesig field |
| `test_create_regions_by_splitting_breaks` | region count | 406 | 405 unique split points + 1 |
| `test_create_regions_by_splitting_page_breaks_only` | region count | 59 | 58 unique page break coords + 1 |
| `test_create_regions_by_splitting_section_breaks` | region count | 1 | 0 section breaks → 1 region (whole timeline) |
| `test_create_segment_line_by_grouping_timesig` | segment count | 22 | Same as timesig runs |
| `test_create_segment_line_by_splitting_page` | segment count | 59 | Same as page break regions |
| `test_create_child_from_region_with_real_data` | child length | 968.0 | First 9/8 region span (0.0–968.0) |
| `test_create_child_from_region_with_real_data` | child events | 216 | Measures in 0.0–968.0 range |
| `test_create_children_from_regions_all` | children count | 22 | One child per timesig region |

---

### `test_flow.py` - Flow Control and Unfolding

**Purpose:** Validates the Flow API that computes unfolded measure sequences from flow control data (repeats, voltas, D.S., D.C., etc.).

**Architecture (Feb 2026 redesign):**

The Flow API uses a **MeasureUnit-based architecture** with FlowControlElement integration:

| Class | Purpose |
|-------|---------|
| `MeasureUnit` | Fundamental building block with FlowControlElement fields |
| `AtomicSection` | Smallest traversal unit (future: `typed_measures`, `groups`) |
| `PlaythroughSection` | Contiguous atomics in traversal (future: `typed_measures`, `groups`) |
| `Flow` | Sequence of PlaythroughSections, delegates iteration to controller |

**MeasureUnit FlowControlElement Fields:**
- `timesig_duration_qb`: Expected duration from time signature
- `jump_from`: True if MC is a jump origin (D.C., D.S., multiple next)
- `jump_to`: True if MC is a jump target (segno, coda, non-adjacent next target)
- `segno`, `coda`, `fine`, `section_break`: Marker fields
- `flow_control_types`: Tuple of FlowControlElement.value strings for serialization
- `to_dict()` / `from_dict()`: Round-trip serialization support

**Naming Rationale**: Named "Section" (not "Segment") to avoid confusion with TimeToAlign's `Segment` concept (a child timeline contiguous with siblings). These are flow control concepts, not timeline children.

**Interval Convention**: Uses **right-open** `[mc_start, mc_end)` intervals, aligning with:
- TimeToAlign TimeInterval definition (left-inclusive, right-exclusive)
- Python `range()` semantics
- partitura convention

| Old (Inclusive) | New (Right-open) | Meaning |
|-----------------|------------------|---------|
| `mc_start=1, mc_end=5` | `mc_start=1, mc_end=6` | MCs 1,2,3,4,5 (5 MCs) |
| `mc_count = end - start + 1` | `mc_count = end - start` | Direct subtraction |

**Current state (Feb 2026):**

- `MeasureUnit` replaces `FlowStep` as the fundamental building block
- `ScoreFlowController.iter_units()` iterates over MeasureUnits
- `ScoreFlowController.iter_sections(mode=None)` defaults to AtomicSections
- `Flow._controller_ref` links Flow to its controller for `iter_units()` access
- `Flow.steps` removed entirely (section-based only)
- FlowControlElement fields on `MeasureUnit` (jump_from, jump_to, segno, coda, fine, etc.)
- `MeasureUnit.from_dict()` for DataFrame round-trip serialization
- Old `get_atomic_sections()` deprecated with DeprecationWarning
- `iter_mcs()` removed (derive from sections instead)
- `_build_units()` uses helper methods for FlowControl detection
- Typed subclasses (`IncompleteMeasure`, `CompleteMeasure`, `OverlengthMeasure`)
  produced by the Typing step
- MeasureGroup hierarchy (`MeasureGroup`, `SplitMeasure`, `VoltaGroup`,
  `CompleteMeasureGroup`, `IncompleteGroup`, `OverlengthGroup`) produced by the
  Grouping step

**Test Categories:**

1. **Dataclass Tests** (22 tests)
   - `TestMeasureUnit`: Creation, immutability, `to_dict()`, `from_dict()`, round-trip, FlowControlElement fields
   - `TestAtomicSection`: Creation, `mc_range`, `mc_count`, frozen, validation
   - `TestPlaythroughSection`: Creation, `mc_range`, `mc_count`, frozen, `to_mc_sequence()`

2. **Typed Measure Tests** (13 tests)
   - `TestTypedMeasures`: Creation and inheritance of typed subclasses
     - `IncompleteMeasure`: Creation with `position` field, is MeasureUnit subclass
     - `CompleteMeasure`: Creation, is MeasureUnit subclass
     - `OverlengthMeasure`: Creation, is MeasureUnit subclass
     - FlowControlElement field preservation in typed measures
     - `IncompletePosition` enum values
   - `TestAtomicSectionTypedMeasures`: `typed_measures` field on AtomicSection
   - `TestPlaythroughSectionTypedMeasures`: `typed_measures` field on PlaythroughSection

3. **MeasureGroup Tests** (16 tests)
   - `TestMeasureGroup`: MeasureGroup base class and subclasses (12 tests)
     - `MeasureGroup`: Base frozen dataclass with `members`, `mc_start`, `mc_end`, `total_duration_qb`
     - `SplitMeasure`: IncompleteMeasures that sum to time signature
     - `IncompleteGroup`: Isolated IncompleteMeasures (anacrusis, final)
     - `VoltaGroup`: Measures under same volta bracket with `volta_number`
     - `CompleteMeasureGroup`: Adjacent CompleteMeasures
     - `OverlengthGroup`: OverlengthMeasures grouped together
   - `TestBuildGroups`: ScoreFlowController grouping algorithm (4 tests)
      - `_build_groups()`: Grouping-step algorithm
     - `_group_voltas()`, `_group_splits()`, `_group_incompletes()`
     - `_group_overlengths()`, `_group_completes()`
     - `groups` field on AtomicSection and PlaythroughSection

4. **Flow Serialization Tests** (17 tests)
   - `TestFlow`: Empty flow, simple flow, flow with repeats, `to_dataframe()`
   - `TestFlowSectionBased`: `from_sections()`, `from_records()`, `to_records()`, `to_csv_rows()`, `is_equivalent()`, `to_mc_sequence()`, `to_atomic_sequence()`, `diff_flows()`, `unfolded_length`
   - `TestFlowCSVLoading`: `Flow.from_csv()`, invalid mode raises, `load_valid_flows()`

5. **ScoreFlowController Tests** (6 tests)
   - `iter_units()`: Iterate over MeasureUnits
   - `iter_sections(mode=None)`: AtomicSections by default
   - `get_sections()`: Unified API (replaces get_atomic_sections)
   - `get_sections(mode)`: Returns PlaythroughSections for specified mode
   - `from_atomic_sections()` class method
   - `compute_flow()` populates sections with controller ref

6. **Integration Tests** (10 tests)
   - `TestExample1Rachmaninoff`: No flow control baseline (3 tests)
   - `TestExample3CouperinMusete`: D.S. al Fine (4 tests, all pass)
   - `TestFlowMap`: FlowMap creation
   - `TestPrintedMode`: PRINTED mode returns folded count

**Test Status: 84 passed** (Feb 2026)

**New Methods (Feb 2026):**

- `Flow.to_atomic_sequence()`: Returns flattened list of atomic section IDs from all sections
- `Flow.diff_flows()`: Shows differences between flows using sequence alignment (difflib)

**c05n05_musete Fix (Feb 2026):**

The gold standard CSV was updated to include all 7 section occurrences in playthrough order:

| # | MC Range | Atomic IDs | Notes |
|---|----------|------------|-------|
| 1 | (1-17) | A;B | First refrain |
| 2 | (1-32) | A;B;C | Second refrain + 1e couplet |
| 3 | (17-32) | C | Repeat of 1e couplet |
| 4 | (6-17) | B | D.S. back to segno |
| 5 | (32-59) | D | First 2e couplet |
| 6 | (32-59) | D | Repeat of 2e couplet |
| 7 | (6-17) | B | Final D.S. al Fine |

**Validity Rationale:**

Following the project's ZERO TOLERANCE validation policy, all tests use **exact value comparisons**:
- EXACT section counts (no ranges or minimums)
- EXACT MC ranges: `(mc_start, mc_end)` pairs must match exactly (right-open)
- EXACT section order (positional comparison)

#### Volta-follows-volta invariant (`TestFlowInvariants`)

**Purpose.** Validate `ScoreFlowController.check_invariants()`, a
detect-and-report structural-invariant check over the atomic flow graph. It
never raises; it returns a list of `FlowDiagnostic` describing each violation
and an empty list when the flow is well-formed.

**The invariant.** In the atomic flow graph a volta section can never have a
`to` edge to another volta section. A prima volta's only out-edge is the repeat
back-edge (to the repeat-start, a non-volta section); a seconda volta is
reached only from the repeat-start and continues into the music after the
bracket (also non-volta). Two flow-adjacent voltas therefore indicate a
malformed `next` array — most often a jump target that resolved to the wrong
ending. This is the `to` (flow) edge relation, NOT score-order adjacency: volta
sections ARE naturally adjacent in MC order, which is correct; they must merely
never be connected by a `to` edge. A section "is a volta" iff its first
measure's `volta is not None` — the same criterion the label generator's
volta-flag and the ASCII diagram's `┌N` corner use.

**Fixture — clean score → no diagnostics.** A repeat with a prima/seconda
volta, then a non-volta section, with a section break two measures after the
seconda volta. Eight MCs (4/4 throughout):

| MC | mn | volta | next | section_break | role |
|----|----|-------|------|---------------|------|
| 1 | 1 | None | [2] | — | repeat-start body |
| 2 | 2 | None | [3] | — | body |
| 3 | 3 | None | [4, 5] | — | branch into the two endings |
| 4 | 3 | 1 | [1] | — | prima volta (repeats back to MC 1) |
| 5 | 4 | 2 | [6] | — | seconda volta (continues sequentially) |
| 6 | 5 | None | [7] | — | continuation after the bracket |
| 7 | 6 | None | [8] | yes | continuation, with section break |
| 8 | 7 | None | [-1] | — | final section |

This is a well-formed score. The atomic partition is `A [1,4)` (to A1, A2),
`A1 [4,5)` prima (to A), `A2 [5,8)` seconda (to B), `B [8,9)` final. The seconda
volta absorbs its continuation up to the next genuine boundary (the section
break at MC 7 puts a boundary at MC 8) — the correct behaviour, matching how a
seconda volta continues in real scores (see the design note below). The only
volta sections are A1 (`to=(A,)` → A non-volta) and A2 (`to=(B,)` → B
non-volta), so `controller.check_invariants() == []`.

**Fixture — malformed score → exactly one diagnostic.** A seven-MC fixture that
mis-resolves the prima volta's `next` so it points forward to the seconda volta
(`MC 4`, volta 1, `next=[5]`) instead of back to the repeat-start (`next=[1]`).

| MC | volta | next | resulting section | `to` |
|----|-------|------|-------------------|------|
| 1–3 | None / None / None | [2]/[3]/[4,5] | A `[1,4)` | (A1, A2) |
| 4 | 1 | [5] | A1 `[4,5)` | (A2,) ← violation |
| 5 | 2 | [6] | A2 `[5,8)` | () |
| 6–7 | None / None | [7]/[-1] | (absorbed into A2) | — |

The prima-volta section `A1` then carries `to=(A2,)` where `A2` is the
seconda-volta section. `check_invariants()` returns exactly one
`FlowDiagnostic(kind="volta_follows_volta", section_id="A1", mc=4)`; its message
names both section ids `'A1'`/`'A2'` and hints that the source section's
next/jump target is mis-resolved.

Following the project's ZERO TOLERANCE policy, all assertions are exact:
diagnostic count, the `to` edges, the volta values at each section start, and
the diagnostic's `kind` / `section_id` / `mc` plus the substring identities in
its message.

**Design note — a closing volta does NOT force an atomic boundary.** The
volta-boundary rule adds a boundary at the *onset* of a volta bracket (a
`volta` value change *into* a non-None ending), NOT at the measure where a
bracket closes (`volta n → None`). A seconda (or final) volta therefore
continues into the music that follows it, absorbing it up to the next genuine
boundary — a later jump target or `section_break`. This is intentional and
matches every `.flow.csv` gold standard: e.g. Op.18 No.4 iv's seconda voltas
are the atomic sections `(45, 78)` and `(103, 227)`, each spanning far beyond
the single volta measure. Adding a boundary at the volta-close transition would
split those sections (`(45, 46)` + `(46, 78)`, …), changing the atomic
partition, the section labels (`A, B, C, D, D1, D2, E, F, F1, F2, G, G1, G2`
would gain extra letters), and the unfolded flow — breaking the gold for Op.18
and the segment-naming integration test. The detect-and-report invariant above
is the right home for "this volta arrangement looks wrong": a malformed flow is
surfaced as a `FlowDiagnostic`, not silently re-partitioned.

---

### `test_flow_intervals.py` - Interval-Built FlowMaps

**Purpose:** Validates constructing a `FlowMap` directly from anything that
describes an interval — a singleton or a collection — through the single
polymorphic positional argument of `FlowMap(source)`, and the
`Timeline.create_flow_map(intervals)` convenience that constructs, attaches,
and returns such a map. There are no new `from_*` constructors: one argument
accepts singleton-or-collection via coercion, plus keyword-only options
(`id`, `resolve`), matching `create_regions_from_boundaries(boundaries, *, …)`.

**Motivating case.** A performance that skips score measures 42 and 43. The
child timeline lives in quarterbeat (QB) space and keeps two played spans,
`[0, 123)` and `[129, length)`. Measures 42–43 occupy QB `123–129`; they fall
in the gap and map to nothing. The two played spans concatenate in the
unfolded (target) axis, so QB `129` in the source becomes QB `123` in the
target.

#### Coercion primitives (`_interval_value`, `_as_interval`, `_coerce_intervals`)

The module-private helpers in `timetoalign/timelines/flow/sections.py` are
duck-typed (no hard imports of `Timeline`/`Region`/`Coordinate`). `_as_interval`
recognises descriptors in strict priority order and each variant yields an
**exact** `(Fraction, Fraction, label)` triple. The `label` is a best-effort
identity — a region name for a `str` or a `Region`, the `name`/`id` for a
`Timeline`, and `None` for a bare coordinate pair or a nameless event — carried
through so unfolding can name the child timeline and Region it derives from
each span:

| Input | Recognised as | Expected `(start, end, label)` |
|-------|---------------|--------------------------------|
| `(0, 123)` (raw ints) | 2-element sequence | `(Fraction(0), Fraction(123), None)` |
| `(Coordinate(0), Coordinate(129))` | 2-element sequence | `(Fraction(0), Fraction(129), None)` |
| `Region("A8_1", start=0, end=123)` | has `.start`/`.end` | `(Fraction(0), Fraction(123), "A8_1")` |
| a `Timeline` of length 200 | has `.origin`/`.length` | `(Fraction(0), Fraction(200), tl.name)` |
| `Note(start=0, end=123)` interval event | has `.start`/`.end` | `(Fraction(0), Fraction(123), None)` |
| `"A8_1"` with a `resolve` callable | `str` → resolved region | `(Fraction(0), Fraction(123), "A8_1")` |
| `"A8_1"` with `resolve=None` | `str`, no resolver | raises `ValueError` |

`_coerce_intervals` disambiguates singleton-vs-collection by trying the whole
spec as one interval first, and only iterating on failure:

- A `str` is **always** a singleton — never iterated character by character
  (`_coerce_intervals("A8_1", resolve=…)` → one interval, not five).
- `[0, 123]` is one coordinate pair (singleton), yielding one interval.
- `[region1, region2]` and `["A8_1", "A8_2"]` are collections, yielding two
  intervals each (the singleton attempt fails because the first element is not
  a coordinate value, so the fallback iterates).
- `[(0, 123), (129, 200)]` yields two intervals.
- Any interval with `end < start` raises `ValueError`.

All assertions are exact `Fraction` equality — no ranges, no `pytest.approx`.

#### Interval-built `FlowMap`

Sections are built directly from the coerced `(start, end, label)` ranges with
a **cumulative target position** (identical math to `from_qb_sections`), each
section carrying its `label`, and `flow` is `None`. For the two motivating
spans `[0, 123)` and `[129, 252)` (length 252):

| Query | Method | Exact result | Derivation |
|-------|--------|--------------|------------|
| `unfold_coordinate(50)` | source → target | `[Fraction(50)]` | span 1: `0 + (50-0)` |
| `unfold_coordinate(125)` | source → target (gap) | `[]` | QB 125 is in the skipped gap |
| `unfold_coordinate(150)` | source → target | `[Fraction(144)]` | span 2: `123 + (150-129)` |
| `fold(144)` | target → source | `Fraction(150)` | inverse of the above |
| `fold(50)` | target → source | `Fraction(50)` | span 1 |
| `total_target_length` | — | `Fraction(246)` | `123 + (252-129)` |
| `n_sections` | — | `2` | two played spans |

`inverse()` round-trips (`inverse().unfold_coordinate(144) == [Fraction(150)]`) and does
not require a non-`None` `flow`. `__repr__` reads the `id`, so an interval map
built with `id="A8"` reprs as `FlowMap(A8: 2 sections)` and its inverse as
`FlowMap(A8_inverse: 2 sections)`.

#### Regression — the `Flow` and `from_qb_sections` paths are unchanged

`FlowMap(flow_obj)` still builds MC-space sections from `flow.sections`
(`unfold_coordinate(3)` over two `[1, 5)` playthrough sections gives
`[Fraction(2), Fraction(6)]`, since MC 3 is visited twice), `id` defaults to
`flow.mode.value`, and `from_qb_sections` is untouched. The polymorphic
positional parameter is named `source`, so `FlowMap(source=flow_obj)` works by
keyword; the historical `FlowMap(flow=flow_obj)` keyword no longer exists (it
raises `TypeError`) — every construction site was migrated to positional and no
compatibility alias is retained.

#### `Timeline.create_flow_map`

`create_flow_map(intervals, *, id="default")` constructs the FlowMap
(resolving region-name strings via `self.get_region`), attaches it under `id`,
and returns it — the `create` verb×noun contract. The four equivalent target
calls all build the same two-span map on a length-252 child:
`create_flow_map(["A8_1", "A8_2"], id="A8")`,
`create_flow_map([region1, region2], id="A8")`,
`create_flow_map([(0, 123), (129, length)], id="A8")`, and the singleton
`create_flow_map(region1, id="X")`. After construction `get_flow_map(id)`
returns the same object, and the timeline's `unfold_coordinate`/`fold`
convenience methods delegate with the exact values above
(`tl.unfold_coordinate(150, "A8") == [144.0]`,
`tl.unfold_coordinate(125, "A8") == []`, `tl.fold(144, "A8") == 150.0`).

#### `Timeline.apply_flow` — the unfolded timeline

`unfold_coordinate` maps a single folded coordinate to a list of unfolded
coordinates; `apply_flow(id)` instead yields the whole unfolded **timeline**.
It slices the source at each section of the attached FlowMap via
`Timeline.get_slice` (which rebases each slice by `-start`) and **appends** the
slices, in target order, as children of a new timeline of the source's **same
concrete type**, whose child offsets accumulate as `0` then `123`. Each section
also becomes a matching named Region in unfolded (target) coordinates. Section
events live in the appended children; the flattened coordinates remain reachable
via `get_events(include_children=True)`. The result carries a reverse FlowMap
(id `"source"`) and the forward FlowMap (id `f"forward_{id}"`). Each child and
Region takes the section's name (a repeat is suffixed `-rend2`, `-rend3`, …).

The fixture is a length-252 source with played spans `A8_1` `[0, 123)` and
`A8_2` `[129, 252)`, instants `e10` at absolute 10 (span 1) and `e140` at
absolute 140 (span 2), and a nested child at offset 40 (span `[40, 60)`, inside
span 1) carrying instant `c5` at local 5. `r = source.apply_flow("A8")` gives
the exact values:

| Query | Exact result | Derivation |
|-------|--------------|------------|
| `type(r) is ContinuousLogicalTimeline` | `True` | same concrete type as source |
| `r.length.value` | `Fraction(246)` | `123 + (252 - 129)` |
| `r.n_children` | `2` | one appended child per played span |
| `r.list_children()` | `["A8_1", "A8_2"]` | children named after the spans |
| child `A8_1` / `A8_2` offset | `Fraction(0)` / `Fraction(123)` | cumulative span lengths |
| child `A8_1` / `A8_2` length | `Fraction(123)` / `Fraction(123)` | span lengths |
| `e10` in child `A8_1` | `Fraction(10)` | slice `[0, 123)`: `10 - 0` |
| `e140` in child `A8_2` | `Fraction(11)` | slice `[129, 252)`: `140 - 129` |
| `A8_1` sub-child offset | `Fraction(40)` | `40 - 0`; `A8_2` has no sub-children |
| sub-child `c5` local coord | `Fraction(5)` | slice `[0, 20)`: `5 - 0` |
| `r.list_regions()` | `["A8_1", "A8_2"]` | one Region per section |
| region `A8_1` / `A8_2` | `[0, 123)` / `[123, 246)` | contiguous target coords |
| `r.get_flow_map("source")` labels | `["A8_1", "A8_2"]` | reverse FlowMap carries labels |
| `r.has_flow_map("forward_A8")` | `True` | forward FlowMap attached |
| `get_events(include_children=True)` | `e10@10`, `c5@45`, `e140@134` (each once) | flattened parent-space coords |
| `["A8_1", "A8_1"]` flow → children/regions | `["A8_1", "A8_1-rend2"]` | repeat gets a `-rend2` suffix |
| `source.apply_flow("nope")` | raises `ValueError` | no FlowMap attached with that id |

---

### `test_segment_naming.py` - Customizable Atomic-Section Labelling

**Purpose:** Validates `SegmentNameGenerator`, the strategy object that the
`ScoreFlowController` uses to label atomic sections, and its integration into
the controller's section-building pass.

**What the generator does.** `generate(volta_flags)` turns a list of
per-section booleans (`volta_flags[i]` is `True` when atomic section `i` opens
a volta bracket) into one label per section. Two policies are configurable at
construction:

- **Alphabet** (`alphabet=`, default `_SECTION_ALPHABET`): base sections walk
  the alphabet; once exhausted it repeats with a numeric suffix (`A2`, `B2`,
  …). The generator never reaches into punctuation or control characters.
- **Volta suffix** (`volta_suffix=`, default `True`): a section that opens a
  volta bracket inherits the preceding base section's label plus a *positional*
  numeric suffix (`1`, `2`, …) — section `B` followed by two endings reads `B,
  B1, B2`, not `B, C, D`. The suffix is positional and independent of the
  volta's own ending number. A non-volta section resets the counter, so two
  independent volta groups read `B, B1, B2` then `C, C1, C2` (never `C3, C4`).
  A leading volta with no preceding base falls back to a base letter (never
  `None1`). With `volta_suffix=False` every section consumes the next base
  label, the historical pure-sequential behaviour.

**Generator unit tests (exact strings):**

| Case | `volta_flags` | Generator config | Expected labels |
|------|---------------|------------------|-----------------|
| Default sequential | all `False` | default | `A, B, C` |
| Alphabet overflow | one flag beyond alphabet length | tiny `alphabet=` | tail label carries the `2` suffix (`…, A2`) |
| Volta suffix | `[False, True, True]` after a base | default | `A, A1, A2` |
| Legacy sequential | `[False, True, True]` | `volta_suffix=False` | `A, B, C` |
| Custom alphabet | all `False` | `alphabet=["X", "Y", "Z"]` | `X, Y, Z` |
| First-section volta | `[True, False, True]` | default | `A, B, B1` (no `None1`) |
| Two volta groups | `[False, True, True, False, True]` | default | `A, A1, A2, B, B1` (counter resets) |

**Integration test (Op.18 No.4 iv specimen).** The folded measures TSV at
`beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/` carries three volta groups.
Building a `ScoreFlowController` over it and reading the atomic sections must
yield, in order:

```
A, B, C, D, D1, D2, E, F, F1, F2, G, G1, G2
```

(13 sections — count unchanged from the pre-volta-suffix labelling). The test
asserts EXACT section ids AND that every `to[]` graph edge references those new
labels (the edges are derived from the same label list, so e.g. `D` points to
`('D1', 'D2')` and `D1` back to `('D',)`). It also confirms section count and
MC ranges are untouched by the relabelling. Passing `volta_suffix=False` to the
controller reproduces the legacy sequential ids `A, B, … M`.

Following the project's ZERO TOLERANCE policy, all assertions are exact string
and exact count comparisons; the data path is resolved relative to the test
file (the pattern already used by `test_unfolding.py` for this specimen).

---

### `test_timestamps.py` - Cross-Section Timestamp Tables

**Purpose:** Validates `get_timestamp_table()` / `to_dataframe()` and the
helpers that build the timestamp axis (event-coordinate collection, boundary
collection, local-coordinate computation) across a timeline hierarchy.

**Fraction-length regression (`TestFractionLengthTimestamps`):**

A logical timeline (quarters/beats) carries `number_type = Fraction`, so its
length is a `Coordinate` whose `value` is a `Fraction`. The bounds check inside
`_compute_local_coordinates` masks out-of-range coordinates by comparing the
local-coordinate array against the length scalar through a PyArrow compute
kernel (`pc.greater`). That kernel rejects a raw `Fraction` argument, so the
length must be coerced to `float` at the kernel boundary — consistent with the
sibling `pc.less(local, 0.0)` and the float64 arrays this internal helper
already operates on. Empirically, only the `pc.greater` comparison broke: the
boundary collector builds a `pa.array(..., type=pa.float64())`, which coerces a
`Fraction` via `__float__`, and the child-offset accumulation starts from a
`float` default so it never reaches a kernel as a raw `Fraction`.

| Test | Construction | Exact assertion |
|------|--------------|-----------------|
| `test_compute_local_coordinates_with_fraction_length` | CLT length `9/2`, probe `[0.0, 2.0, 4.5, 5.0]` | local = `[0.0, 2.0, 4.5, None]` (5.0 > 4.5 → null) |
| `test_get_timestamp_table_with_fraction_length` | CLT length `9/2`, events at `0, 3/2, 3` | `num_rows == 3`; axis = `[0.0, 1.5, 3.0]`; root-local = `[0.0, 1.5, 3.0]` |
| `test_to_dataframe_with_fraction_length` | same timeline | shape `(3, 2)`; axis column = `[Fraction(0), Fraction(3,2), Fraction(3)]` (auto-rendered as Fractions for a Fraction-type timeline) |

**Validity Rationale:** The timestamp axis is the spine of every cross-domain
alignment view. A quarters/beats timeline — the most common logical timeline —
must produce timestamp tables and frames without raising. The asserted values
are the exact in-bounds coordinates: the out-of-bounds probe coordinate becomes
`null`, the event coordinates pass through unchanged, and the root timeline's
local coordinates equal the axis because its offset is zero.

---

### `test_timestamps.py` - Cross-Section Timestamp Tables

**Purpose:** Validates `get_timestamp_table()` / `to_dataframe()` and the
helpers that build the timestamp axis (event-coordinate collection, boundary
collection, local-coordinate computation) across a timeline hierarchy.

**Fraction-length regression (`TestFractionLengthTimestamps`):**

A logical timeline (quarters/beats) carries `number_type = Fraction`, so its
length is a `Coordinate` whose `value` is a `Fraction`. The bounds check inside
`_compute_local_coordinates` masks out-of-range coordinates by comparing the
local-coordinate array against the length scalar through a PyArrow compute
kernel (`pc.greater`). That kernel rejects a raw `Fraction` argument, so the
length must be coerced to `float` at the kernel boundary — consistent with the
sibling `pc.less(local, 0.0)` and the float64 arrays this internal helper
already operates on. Empirically, only the `pc.greater` comparison broke: the
boundary collector builds a `pa.array(..., type=pa.float64())`, which coerces a
`Fraction` via `__float__`, and the child-offset accumulation starts from a
`float` default so it never reaches a kernel as a raw `Fraction`.

| Test | Construction | Exact assertion |
|------|--------------|-----------------|
| `test_compute_local_coordinates_with_fraction_length` | CLT length `9/2`, probe `[0.0, 2.0, 4.5, 5.0]` | local = `[0.0, 2.0, 4.5, None]` (5.0 > 4.5 → null) |
| `test_get_timestamp_table_with_fraction_length` | CLT length `9/2`, events at `0, 3/2, 3` | `num_rows == 3`; axis = `[0.0, 1.5, 3.0]`; root-local = `[0.0, 1.5, 3.0]` |
| `test_to_dataframe_with_fraction_length` | same timeline | shape `(3, 2)`; axis column = `[Fraction(0), Fraction(3,2), Fraction(3)]` (auto-rendered as Fractions for a Fraction-type timeline) |

**Validity Rationale:** The timestamp axis is the spine of every cross-domain
alignment view. A quarters/beats timeline — the most common logical timeline —
must produce timestamp tables and frames without raising. The asserted values
are the exact in-bounds coordinates: the out-of-bounds probe coordinate becomes
`null`, the event coordinates pass through unchanged, and the root timeline's
local coordinates equal the axis because its offset is zero.

---

### `test_unfolding.py` - Unfolding via Slicing

**Purpose:** Validates the slice-based unfolding pipeline that replaces the buggy MC-space
FlowMap approach with structural slicing in QB-space.

**Test classes** validating the pipeline:

| Class | Purpose |
|-------|---------|
| `TestGetSlice` | Unit tests for `Timeline.get_slice()` primitive |
| `TestComputeQBSections` | QB boundary computation from Flow + ScoreFlowController |
| `TestSegmentLineAssembly` | Integration: slice + concatenate into a SegmentLine (this module's own manual helper) |
| `TestCreateUnfoldedTimelineIdentity` | Explicit uid on the same-type unfolded timeline |
| `TestUnfoldingGoldStandard` | End-to-end validation against 7 ms3 gold standard specimens |
| `TestGroupUnfolding` | Cross-domain unfolding via GroupTimestamp interpolation |

**Testing Pyramid:**

```
    ┌─────────────────────────────────┐
    │  Group Unfolding Tests          │  ← 3 timelines × 1 FlowMap,
    │  (TestGroupUnfolding)           │     cross-domain (Logical+Graphical)
    ├─────────────────────────────────┤
    │  Gold Standard Tests            │  ← 7 specimens, EXACT match
    │  (TestUnfoldingGoldStandard)    │     against ms3 TSV files
    ├─────────────────────────────────┤
    │  Integration Tests              │  ← SegmentLine assembly from
    │  (TestSegmentLineAssembly)      │     slices, contiguity, length
    ├─────────────────────────────────┤
    │  Unit Tests                     │  ← get_slice() primitive
    │  (TestGetSlice +                │     compute_qb_sections() helper
    │   TestComputeQBSections)        │
    └─────────────────────────────────┘
```

**Test Categories:**

1. **get_slice() Unit Tests** (16 tests)
   - Basic slicing with coordinate shifting (`[start, end)` semantics)
   - Interval event truncation (`truncate_events=True/False`)
   - Child timeline recursive slicing
   - Number type preservation (Fraction stays Fraction)
   - Concrete class preservation (CLT returns CLT)
   - Parameterized SegmentLine slicing preserves its dynamic class
   - Discrete and physical timeline support
   - Error cases (invalid range, out of bounds)

2. **compute_qb_sections() Unit Tests** (8 tests)
   - Sequential score (Rachmaninoff): single pass, total QB = 2997/2
   - D.S. al Fine (Musete): repeated sections, total QB = 384
   - Rondeau form, volta brackets, split bars, D.S./D.C.
   - QB boundaries match folded TSV `quarterbeats` column exactly
   - All sections have strictly positive duration

3. **SegmentLine Assembly Integration Tests** (5 tests)
   - Contiguity enforcement (each segment starts where previous ended)
   - Total length = sum of slice lengths
   - Events preserved in assembled segments
   - Segment type matches source class
   - The assembled line is an instance of both SegmentLine and the source class
   - Repeated section assembly (same range played twice)

4. **Standalone Unfolded Timeline Identity Tests** (2 tests)
   - Explicit `uid` is retained by flat timeline results
   - Explicit `uid` is retained by SegmentLine results

5. **Gold Standard End-to-End Tests** (49 tests, parametrized × 7 specimens)
   - EXACT row count, MC sequence, mc_playthrough, mn_playthrough with suffixes
   - EXACT quarterbeats as Fraction (not float), total unfolded length

6. **Group Unfolding Tests** (10 tests)
   - Uses Beethoven Op.18 No.4 iv multimodal score group (CLT1 + DGT1 + OpenScore)
   - Validates that one FlowMap unfolds ALL timelines regardless of domain
   - Resolves section boundaries through GroupTimestamps
   - Tests: segment counts (11), contiguity, type preservation, length consistency

**Gold Standard Exact Values:**

| Specimen | Folded | Unfolded | Total QB | Challenge |
|----------|--------|----------|----------|-----------|
| rachmaninoff | 374 | 374 | 2997/2 | No flow control (baseline) |
| polyrhythm_only | 14 | 14 | 45 | Line breaks only |
| musete | 58 | 138 | 384 | D.S. al Fine, anacrusis, 6/8 |
| rondeau | 60 | 138 | 195 | Rondeau form (D.S.) |
| op18_no4_mov4 | 226 | 291 | 1116 | Repeats + volta brackets |
| woo71 | 397 | 505 | 1078 | Complex split bars |
| flow_only | 15 | 30 | 75 | D.S./D.C. + voltas |

**Known Edge Cases:**
- **Anacrusis** (Musete): Incomplete first measure (1.5 QB instead of 3.0). Repeated instance preserves short duration.
- **Split bars** (WoO71): Single notated measure divided into two MCs. Preserved exactly through unfolding.
- **Volta brackets** (Op.18): Different MCs played on different passes. Correct volta selected per pass.
- **Rondeau form** (c11n08): ABACADA return pattern via D.S.-like mechanism.

**Bug Fixes Applied:**
- `Ms3Loader._resolve_quarterbeats()`: Prefers `quarterbeats_all_endings` over `quarterbeats` (fixes 10.5q error for volta first-endings).
- `SegmentLine.get_slice()`: Override creates with `length=0` and sets final length after children, fixing contiguity validation.

**Coordinate Handling:** EventData stores instant events under `start` (struct dict),
not `instant`. Use `struct_to_coordinate()` for reading; never cast to `float`
unnecessarily (loses Fraction precision).

---

## Validation Methodology

All tests follow these principles:

1. **Positive Tests**: Verify correct behavior under normal conditions
2. **Negative Tests**: Verify errors are raised for invalid input
3. **Boundary Tests**: Test edge cases (empty, zero, max values)
4. **Performance Tests**: Ensure operations complete within time budgets
5. **Roundtrip Tests**: Verify serialization preserves data

Each test class includes a docstring explaining its validity rationale,
linking back to specific requirements from the TimeToAlign model and the
project's engineering standards.
