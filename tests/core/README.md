# Core Module Tests

This directory contains tests for the `timetoalign.core` module, which provides fundamental types and enums for the TimeToAlign! library.

## Test Coverage Summary

| Module | Status |
|--------|--------|
| `core/types.py` | Complete |
| `core/enums.py` | Complete |
| `core/ids.py` | Complete |
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
