# Conversion Map Tests

This directory contains tests for the `timetoalign.maps` module, which implements coordinate conversion maps.

## Test Coverage Summary

| Module | Coverage | Status |
|--------|----------|--------|
| `maps/base.py` | 74% | Good |
| `maps/linear.py` | 64% | Good |
| `maps/table.py` | 66% | Good |
| `maps/composite.py` | 79% | Good |
| `maps/periodic.py` | 79% | Good |
| `maps/combination.py` | 81% | Good |

## Test Files

### `test_linear.py` - Linear Transformation Maps

**Purpose:** Validates affine transformations (`LinearMap`, `ScalarMap`, `ShiftMap`).

**Test Categories:**
- **Initialization**: Validates attributes and constraints (non-zero scalar).
- **Conversion**: Scalar and array conversions match mathematical expectations.
- **Inverse**: Inverse maps behave correctly ($f^{-1}(f(x)) = x$).
- **Composition**: Composing two linear maps results in a single linear map.
- **Fraction Support**: Validates high-precision arithmetic.

### `test_table.py` - Table-Based Maps

**Purpose:** Validates lookup and interpolation logic (`TableMap`).

**Test Categories:**
- **Interpolation**: Linear, Nearest, Previous (Step-Left), Next (Step-Right).
- **Extrapolation**: Extrapolate (linear), Constant (clamp), Error, NaN.
- **Inverse**: Inversion by swapping axes (requires monotonicity).
- **Factory Methods**: `from_tempo_changes` correctly builds maps from MIDI tempo data.

### `test_composite.py` - Composite Maps

**Purpose:** Validates maps composed of other maps (`ChainMap`, `PiecewiseMap`).

**Test Categories:**
- **ChainMap**:
    - Validates sequence execution ($f(g(x))$).
    - Unit compatibility checks between steps.
    - Inverse chain construction.
- **PiecewiseMap**:
    - Region selection based on break points.
    - Delegation to sub-maps.
    - Array conversion optimization.
    - Naive inversion support.

### `test_periodic.py` - Periodic Maps (RotationMap, FloorMap)

**Purpose:** Validates cyclic and floor-division transformations for metrical calculations.

**Test Categories:**

#### RotationMap
- **Initialization**: Validates period, scale, base, offset attributes.
- **Beat Rotation**: 4/4 time cycles through beats 1,2,3,4,1,2,3,4...
- **Beat Rotation 3/4**: 3/4 time cycles through beats 1,2,3,1,2,3...
- **Beat Rotation 6/8**: Compound meter with eighth-note beats.
- **Offset**: Handles non-zero starting positions (e.g., anacrusis).
- **Not Invertible**: Correctly reports `is_invertible = False` (many-to-one).
- **Serialization**: `to_dict()` / `from_dict()` roundtrip preserves all parameters.
- **Angle Normalization**: Handles negative inputs via modulo.

#### FloorMap
- **Initialization**: Validates divisor and base parameters.
- **Measure Numbers 4/4**: Quarters 0-3.99 -> Measure 1, 4-7.99 -> Measure 2, etc.
- **Measure Numbers 3/4**: 3 quarters per measure.
- **Zero-Indexed**: Supports base=0 for 0-indexed results.
- **Offset**: Handles non-zero divisor offsets.
- **Not Invertible**: Correctly reports `is_invertible = False` (many-to-one).
- **Page Numbers**: General use case for pagination.

#### Integration Tests
- **Measure/Beat Consistency**: FloorMap + RotationMap jointly cover all quarters.
- **SUPRA Compatibility**: Validates against SUPRA reference data (222 measures, 888 quarters).

**Validity Rationale:**

These maps implement the metrical coordinate transformations required by BeatGrid:
- `FloorMap`: quarters -> measure_number (integer division by quarters_per_measure)
- `RotationMap`: quarters -> beat_in_measure (cyclic modulo)

Both are explicitly NOT invertible because they are many-to-one mappings.

---

### `test_combination.py` - Multi-Output Maps (CombinationMap)

**Purpose:** Validates maps that produce multiple outputs from a single input.

**Test Categories:**
- **Initialization from Dict**: Maps specified as `{"name": map}` dictionary.
- **Initialization from Sequence**: Maps specified as `[("name", map), ...]` for ordering.
- **Empty Maps Error**: Raises ValueError for empty map collection.
- **Scalar Conversion**: Returns `{"name": value}` dict for scalar input.
- **Array Conversion**: Returns `{"name": array}` dict for array input.
- **Metrical Combination**: Combines FloorMap + RotationMap for (measure, beat) tuples.
- **XY Coordinates**: Combines two linear maps for (x, y) output.
- **Not Invertible**: Correctly reports `is_invertible = False`.
- **Get Map**: Can retrieve individual sub-maps by name.
- **Source Unit Validation**: All sub-maps must have compatible source units.
- **Source Unit Inheritance**: CombinationMap inherits source_unit from sub-maps.
- **Serialization**: `to_dict()` / `from_dict()` roundtrip.
- **SUPRA Metrical Positions**: Validates against SUPRA reference (measure 222, beat 4 at quarter 887).

**Validity Rationale:**

CombinationMap enables multi-valued lookups required by the TTA model:
- A single coordinate can map to (measure, beat, beat_type) tuples
- This is essential for the TimeStamp cross-section feature
- The map is NOT invertible because multiple outputs cannot uniquely determine input

---

## Integration Tests

Integration with the `Timeline` class is tested in `tests/timelines/test_maps_integration.py`.

## Validity Rationale

These tests verify the core mapping capabilities required by the TTA model:
- **Accuracy**: Mathematical transformations must be precise (using Fractions where possible).
- **Invertibility**: All maps must support inversion for bi-directional alignment.
- **Non-Invertibility**: Some maps (RotationMap, FloorMap, CombinationMap) are explicitly many-to-one.
- **Composition**: Maps must be composable to form complex chains.
- **Performance**: Array operations should use vectorized numpy implementations.
