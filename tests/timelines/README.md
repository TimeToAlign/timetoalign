# Timeline Tests

This directory contains comprehensive tests for the `timetoalign.timelines` module,
which implements the central Timeline class and its 6 domain-specific subclasses.

## Test Coverage Summary

| Module | Coverage | Status |
|--------|----------|--------|
| `timelines/base.py` | 94% | Excellent |
| `timelines/types.py` | 100% | Complete |
| `timelines/mixins.py` | 100% | Complete |

## Test Files

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
