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

### `test_interpolation.py` - InterpolationMap

**Purpose:** Validates `InterpolationMap`, the anchor-pair engine used by
`TimelineGroup` and `WarpMap`. `InterpolationMap` is a `ConversionMap`
subclass like every other map in this package, so its tests exercise the
shared interface rather than a bespoke value-passing API.

**Test Categories:**
- **Conversion via `__call__`/`convert_array`**: scalar and array forward
  conversion, replacing the old `forward(values)` method form.
- **Inverse via `inverse()`**: the map-returning form (`inverse()(x)`),
  replacing the old `inverse(values)` method form. Covers increasing and
  decreasing target arrays, extrapolation, and the non-invertible error.
- **Inverse caching**: `inverse()` returns the same instance on repeated
  calls, and the returned map's own `inverse()` yields back the original
  instance (symmetric cache) — this matters because inverting is not free
  (it validates monotonicity and may reverse arrays), so callers that
  round-trip through `.inverse().inverse()` should not pay for it twice.
- **ConversionMap family membership**: `issubclass(InterpolationMap,
  ConversionMap)`; a `Coordinate` input is checked against the map's
  `source_unit` by the inherited `__call__`, so a mismatched unit raises
  `ValueError` without any InterpolationMap-specific code.
- **Serialization**: `to_dict()`/`from_dict()` round-trips arrays, ids, and
  units exactly; `ConversionMap.from_dict()` dispatches to
  `InterpolationMap` via the self-registering type registry.
- **Read-only coordinate arrays**: `source_coords`/`target_coords` are
  copied and frozen (`setflags(write=False)`) on construction, so mutating
  either raises `ValueError`; this also protects the cached inverse from
  desynchronizing, since the caller can no longer mutate one map's arrays
  in place and have it silently affect the other's converted values.
- **Selector matching**: `matches_selector()` (inherited from `ConversionMap`,
  overridden here) matches an `InterpolationMap`'s `source_id` in addition to
  its `id`/`name`, since group converter maps are addressed by the source
  timeline id in conversion-map specifications.
- **Exact assertions**: all numeric expectations use `==`/`np.array_equal`
  rather than `pytest.approx`/`assert_array_almost_equal` — the anchor
  values chosen throughout are exactly representable in binary floating
  point, so the computed conversions are exact.
- **Extraction factory removed**: `InterpolationMap` no longer offers a
  TableMap-extraction constructor that degrades a `TableMap`'s
  interpolation kind and extrapolation policy to plain linear
  interpolation/extrapolation — `Timeline.add_conversion_map` now stores
  `TableMap` instances directly (see `test_maps_integration.py`), so the
  factory and its tests are gone.

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

### `test_meter.py` - Meter-Aware Maps (MetricMap, MetricalPositionMap)

**Purpose:** Validates `MetricMap.from_verovio_timemap` and the
`MetricalPositionMap` reverse lookup it feeds.

**Test Categories:**

#### MetricMap.from_verovio_timemap

A Verovio timemap is a JSON list whose measure-start entries carry a
`measureOn` xml:id and a `meterSig` of the form `"<measure_number>
<num>/<den>"`.  The factory collects each `measureOn` entry's `qstamp`
(absolute quarters) as a measure boundary, parses the measure-number token
as the label, and bounds the last measure by the timemap's final `qstamp`.

Validated against the Chopin Nocturne specimen (`performance_precision`
corpus) — zero-tolerance, exact values only:

- `n_measures == 38`
- `total_length == Fraction(425, 2)` (212.5 quarters)
- `starts[0] == Fraction(0)`, `starts[1] == Fraction(1, 2)` (0.5),
  `starts[2] == Fraction(13, 2)` (6.5), `starts[37] == Fraction(413, 2)`
  (206.5)
- `mns[0] == "1"`, `mns[-1] == "38"`; `mcs == list(range(1, 39))`
- last measure length == `Fraction(6)` (212.5 − 206.5)
- a timemap with no `measureOn` entries raises `ValueError`

#### MetricMap.quarters_at

`MetricMap.quarters_at(mc)` returns a measure's downbeat quarter position
directly — the reverse of `MetricMap.__call__` (quarters -> MC), and the
same value `get_measure_info(mc)["start"]` already exposed, now reachable
without building the `dict`. Validated against the same specimen boundaries
(`quarters_at(1)`, `quarters_at(2)`, `quarters_at(3)`); an unknown MC raises
`ValueError`.

#### MetricalPositionMap reverse lookup

`MetricalPositionMap(meter_map).quarters_at(mc, beat)` returns the
quarter position of a measure's beat, computed as
`meter_map.quarters_at(mc) + (beat - 1)`. Validated against the same specimen
boundaries (e.g. `quarters_at(2)` == `starts[1]` == the downbeat of MC 2),
and `mn_at(quarters)` returns the measure-number label at a position.

**Validity Rationale:**

The Verovio timemap supplies what a bare `.meter` file cannot: an upper
bound for the final measure.  A `.meter` file encodes only meter *changes*
(this specimen lists 4 rows across 38 measures), so the timemap's terminal
`qstamp` is required to close the last bar.  Exact-value assertions pin the
boundary arithmetic.

#### `ConversionMap.from_dict` registry dispatch

`MetricMap`, `BeatInMeasureMap`, and `MetricalPositionMap` round-trip
through `ConversionMap.from_dict()` using the self-registering class
registry (`__init_subclass__`), the same mechanism every other map type in
this package uses — there is no hand-written type-name table to keep in
sync as new map classes are added. `MetricalPositionMap.to_dict()` no
longer emits a redundant `map_type` key: the base `ConversionMap.to_dict()`
already writes `type` as the class name, which is exactly what the
registry dispatches on.

---

## Serialization

Every map's `to_dict()` is JSON-serializable: rational parameters (scalars,
offsets, boundaries, measure starts and lengths, table anchors) are emitted as
the **rational wire dict** `{value, numerator, denominator}` rather than as
`Fraction` objects or `"n/d"` strings, and `from_dict()` reads that shape and
nothing else. `to_dict()` also always emits `name`, and every subclass
`from_dict()` passes it to the constructor, so a custom map name round-trips.

The format, the fixpoint guarantee, and the cross-package JSON-safety sweep
are specified in `tests/core/README.md` (`test_wire_format.py`), which holds
the map name and `ConstantMap` `Fraction` round-trip tests.

## Integration Tests

Integration with the `Timeline` class is tested in `tests/timelines/test_maps_integration.py`.

## Validity Rationale

These tests verify the core mapping capabilities required by the TTA model:
- **Accuracy**: Mathematical transformations must be precise (using Fractions where possible).
- **Invertibility**: All maps must support inversion for bi-directional alignment.
- **Non-Invertibility**: Some maps (RotationMap, FloorMap, CombinationMap) are explicitly many-to-one.
- **Composition**: Maps must be composable to form complex chains.
- **Performance**: Array operations should use vectorized numpy implementations.
