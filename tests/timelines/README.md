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

## Test Files

### `test_timeline_relationships.py` - Region, SegmentLine, derive(), Hierarchical Queries

**74 tests** covering TTA architecture harmonization concepts. See detailed
documentation below in its own section.

---

### `test_base.py` - Core Timeline Functionality

**Purpose:** Validates the fundamental Timeline contract and behavior.

**Test Categories:**

1. **Construction Tests** (11 tests)
   - Empty timeline creation with defaults
   - Timeline with explicit length, unit, number_type
   - Custom ID vs auto-generated ID
   - Locked state on creation
   - Factory methods: `from_events()`, `from_event_store()`

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
   - `to_dict()` / `from_dict()` roundtrip
   - Children serialized recursively
   - Segment events regenerated on deserialization

7. **Magic Methods Tests** (5 tests)
   - `__len__`, `__repr__`, `__str__`, `__contains__`

8. **Future API Stubs Tests** (5 tests)
   - `add_conversion_map()`, `convert_to()` raise `NotImplementedError`
   - `add_match()`, `add_break()`, `add_jump()` raise `NotImplementedError`

9. **Performance Tests** (2 tests)
   - Adding 10,000 events: < 5 seconds
   - Creating 1,000 timelines: < 2 seconds

**Validity Rationale:**

These tests verify the fundamental Timeline contract from the TTA manuscript:
- A Timeline is a positive coordinate axis with an origin (zero) and measuring unit
- Events are stored efficiently in an EventStore (PyArrow-backed)
- Timelines can expand (if unlocked) but cannot contract below content
- Coordinates are validated against the timeline's unit

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

2. **Adding Children Tests** (9 tests)
   - Basic child addition
   - Offset storage and retrieval
   - Child locking upon embedding
   - Segment event creation in parent's EventStore
   - Auto-expansion of parent
   - Multiple children

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

**Validity Rationale:**

The TTA model specifies that timelines can contain nested "children" (segments)
that share the same coordinate type. These tests verify:
- Children must have matching units (type safety)
- Children are locked upon embedding (immutability)
- Children appear as interval events in the parent's EventStore
- Traversal orders work correctly for hierarchical access

---

### `test_types.py` - Domain-Specific Timeline Subclasses

**Purpose:** Validates the 6 timeline types (3 domains x 2 modalities).

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

**Validity Rationale:**

The TTA manuscript defines 6 timeline types across 3 domains (Logical, Physical,
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

### `test_timeline_relationships.py` - Region, SegmentLine, derive(), partition()

**Purpose:** Validates the TTA architecture harmonization features that distinguish
between different timeline relationship concepts.

**TTA Manuscript Concepts Tested:**

| Concept | Definition | Test Category |
|---------|------------|---------------|
| **Region** | A named TimeInterval (NOT a timeline) | `TestRegionDataclass`, `TestTimelineRegionManagement` |
| **Child** | A timeline nested in a parent (same unit) | Tested in `test_nesting.py` |
| **Segment** | A Child that is contiguous with siblings | `TestSegmentLineBasics` |
| **SegmentLine** | A parent where ALL children are Segments | `TestSegmentLineFromSegmentation` |
| **Derivative** | A new timeline created via C-map (different unit) | `TestTimelineDerive` |

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

2. **Timeline Region Management Tests** (9 tests)
   - add_region() returns Region object
   - get_region() returns dict (backwards compat)
   - get_region_object() returns Region
   - has_region(), iter_regions(), list_regions()
   - n_regions property
   - Duplicate name rejection
   - Locked timeline rejection

3. **Partition Tests** (7 tests)
   - partition() creates child at region's offset
   - Copies events within region to child
   - Adjusts event coordinates relative to child origin
   - copy_events=False creates empty child
   - Raises KeyError for nonexistent region
   - Raises RuntimeError on locked timeline

4. **SegmentLine Basics Tests** (8 tests)
   - Empty creation
   - append_segment() adds contiguous children
   - Segment offsets form contiguous sequence
   - Rejects non-contiguous offsets
   - First segment must start at 0
   - get_segment_by_index()
   - get_segment_at() finds segment by coordinate

5. **SegmentLine from_segmentation Tests** (5 tests)
   - Creates correct number of segments
   - Segments have correct lengths
   - Copies events to respective segments
   - Requires at least 2 split coordinates
   - Fails if source has existing children

6. **Timeline.derive() Tests** (8 tests)
   - Creates timeline in target unit
   - Creates correct Timeline subclass for domain
   - Attaches inverse C-map for roundtrip
   - Roundtrip accuracy verification
   - Raises ValueError without C-map
   - Uses custom name if provided
   - copy_events=True copies and converts events
   - copy_events=False (default) creates empty timeline

7. **get_timeline_class() Tests** (7 tests)
   - Returns correct class for all 6 domain/modality combinations
   - Raises ValueError for unknown domain

8. **query_events_hierarchical() Tests** (8 tests)
   - Returns root events when no children
   - Includes events from children
   - Root-relative coordinates in root_start field
   - Nested children (grandchildren) with correct offsets
   - Filter by event_types
   - Filter by coord_range (root-relative)
   - Recursion limit controls depth
   - include_children=False excludes child events

9. **get_events_at() Tests** (10 tests)
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

10. **Integration Tests** (3 tests)
    - Regions used to create SegmentLine structure
    - Derived timeline can have children added
    - SegmentLine with individual segment C-maps

**Validity Rationale:**

From TTA Manuscript (Section 3.4-3.5):
- "A Region is a named part of a timeline that is defined by a TimeInterval."
- "When all Children of the same parent timeline are contiguous, we call them
  Segments and the parent a SegmentLine."
- "A ConversionMap implies the presence of a derived timeline in the target unit."

These tests ensure:
1. Region is NOT a Timeline (immutable dataclass, no events/C-maps)
2. SegmentLine enforces strict contiguity (no gaps/overlaps)
3. derive() creates proper cross-domain relationships via C-maps
4. Inverse C-maps enable accurate roundtrip conversions
5. query_events_hierarchical() enables cross-hierarchy event queries with root-relative coordinates
6. get_events_at() enables point-in-time queries following [start, end) interval semantics

---

### `test_flow.py` - Flow Control and Unfolding (Phase 3.7)

**Purpose:** Validates the Flow API that computes unfolded measure sequences from flow control data (repeats, voltas, D.S., D.C., etc.).

**Architecture (Feb 2026 Redesign → Phase 10 MVP + Cleanup):**

The Flow API uses a **MeasureUnit-based architecture** with FlowControlType integration:

| Class | Purpose |
|-------|---------|
| `MeasureUnit` | Fundamental building block with FlowControlType fields |
| `AtomicSection` | Smallest traversal unit (future: `typed_measures`, `groups`) |
| `PlaythroughSection` | Contiguous atomics in traversal (future: `typed_measures`, `groups`) |
| `Flow` | Sequence of PlaythroughSections, delegates iteration to controller |

**MeasureUnit FlowControlType Fields (Phase 10 MVP Cleanup):**
- `timesig_duration_qb`: Expected duration from time signature
- `jump_from`: True if MC is a jump origin (D.C., D.S., multiple next)
- `jump_to`: True if MC is a jump target (segno, coda, non-adjacent next target)
- `segno`, `coda`, `fine`, `section_break`: Marker fields
- `flow_control_types`: Tuple of FlowControlType.value strings for serialization
- `to_dict()` / `from_dict()`: Round-trip serialization support

**Naming Rationale**: Named "Section" (not "Segment") to avoid confusion with TTA manuscript's `Segment` concept (a child timeline contiguous with siblings). These are flow control concepts, not timeline children.

**Interval Convention**: Uses **right-open** `[mc_start, mc_end)` intervals, aligning with:
- TTA manuscript TimeInterval definition (left-inclusive, right-exclusive)
- Python `range()` semantics
- partitura convention

| Old (Inclusive) | New (Right-open) | Meaning |
|-----------------|------------------|---------|
| `mc_start=1, mc_end=5` | `mc_start=1, mc_end=6` | MCs 1,2,3,4,5 (5 MCs) |
| `mc_count = end - start + 1` | `mc_count = end - start` | Direct subtraction |

**Phase 10 MVP Status (Feb 2026): COMPLETE**

- `MeasureUnit` replaces `FlowStep` as the fundamental building block
- `FlowController.iter_units()` iterates over MeasureUnits
- `FlowController.iter_sections(mode=None)` defaults to AtomicSections
- `Flow._controller_ref` links Flow to its controller for `iter_units()` access
- `Flow.steps` removed entirely (section-based only)

**Phase 10 MVP Cleanup (Feb 2026): COMPLETE**

- Added FlowControlType fields to `MeasureUnit` (jump_from, jump_to, segno, coda, fine, etc.)
- Added `MeasureUnit.from_dict()` for DataFrame round-trip serialization
- Deprecated old `get_atomic_sections()` with DeprecationWarning
- Removed `iter_mcs()` (unnecessary, derive from sections)
- Updated `_build_units()` with helper methods for FlowControl detection

**Deferred to Phase 10.2**: Semantic groupings (`MeasureGroup`, `IncompleteMeasure`, `Volta`, etc.)

**Test Categories:**

1. **Dataclass Tests** (22 tests)
   - `TestMeasureUnit`: Creation, immutability, `to_dict()`, `from_dict()`, round-trip, FlowControlType fields
   - `TestAtomicSection`: Creation, `mc_range`, `mc_count`, frozen, validation
   - `TestPlaythroughSection`: Creation, `mc_range`, `mc_count`, frozen, `to_mc_sequence()`

2. **Flow Serialization Tests** (17 tests)
   - `TestFlow`: Empty flow, simple flow, flow with repeats, `to_dataframe()`
   - `TestFlowSectionBased`: `from_sections()`, `from_records()`, `to_records()`, `to_csv_rows()`, `is_equivalent()`, `to_mc_sequence()`, `to_atomic_sequence()`, `diff_flows()`, `unfolded_length`
   - `TestFlowCSVLoading`: `Flow.from_csv()`, invalid mode raises, `load_valid_flows()`

3. **FlowController Tests** (6 tests)
   - `iter_units()`: Iterate over MeasureUnits (Phase 10 MVP)
   - `iter_sections(mode=None)`: AtomicSections by default (Phase 10 MVP)
   - `get_sections()`: Unified API (replaces get_atomic_sections)
   - `get_sections(mode)`: Returns PlaythroughSections for specified mode
   - `from_atomic_sections()` class method
   - `compute_flow()` populates sections with controller ref

4. **Integration Tests** (10 tests)
   - `TestExample1Rachmaninoff`: No flow control baseline (3 tests)
   - `TestExample3CouperinMusete`: D.S. al Fine (4 tests, all pass)
   - `TestFlowMap`: FlowMap creation
   - `TestPrintedMode`: PRINTED mode returns folded count

**Test Status: 55 passed**

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

Following AGENTS.md Section 3.6 (ZERO TOLERANCE), all tests use **exact value comparisons**:
- EXACT section counts (no ranges or minimums)
- EXACT MC ranges: `(mc_start, mc_end)` pairs must match exactly (right-open)
- EXACT section order (positional comparison)

---

## Validation Methodology

All tests follow these principles:

1. **Positive Tests**: Verify correct behavior under normal conditions
2. **Negative Tests**: Verify errors are raised for invalid input
3. **Boundary Tests**: Test edge cases (empty, zero, max values)
4. **Performance Tests**: Ensure operations complete within time budgets
5. **Roundtrip Tests**: Verify serialization preserves data

Each test class includes a docstring explaining its validity rationale,
linking back to specific requirements from the TTA manuscript and
AGENTS.md engineering standards.
