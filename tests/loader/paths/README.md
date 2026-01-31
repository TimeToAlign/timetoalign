# Path API Tests

This directory contains tests for the `timetoalign.loader.paths` subpackage.

## Test Files

### `test_paths.py`

Tests for `Path`, `LinearPath`, and `PolylinePath` classes.

## Test Coverage

### LinearPath Tests

| Test | Purpose | Validation |
|------|---------|------------|
| `test_horizontal_path` | Horizontal line (y constant) | `is_horizontal()` returns True, pixel_length = x1 - x0 |
| `test_vertical_path` | Vertical line (x constant) | `is_vertical()` returns True, pixel_length = y1 - y0 |
| `test_diagonal_path` | 3-4-5 triangle diagonal | pixel_length = 500 (exact Pythagorean) |
| `test_coord_to_xy_*` | Forward C-map | Exact (x, y) at start, end, midpoint |
| `test_xy_to_coord_*` | Inverse C-map | Exact coordinate recovery, None for off-path points |
| `test_distance_to_path` | Perpendicular distance | Exact distance calculation |
| `test_invalid_*` | Error handling | ValueError for invalid configurations |

### PolylinePath Tests

| Test | Purpose | Validation |
|------|---------|------------|
| `test_simple_polyline` | Two-segment path | n_segments = 2, length = end_coord - start_coord |
| `test_coord_to_xy_*` | Coordinate mapping per segment | Exact (x, y) via linear interpolation |
| `test_xy_to_coord` | Reverse mapping | Exact coordinate recovery |
| `test_pixel_length` | Total Euclidean length | Sum of segment lengths |
| `test_invalid_*` | Error handling | ValueError for < 2 waypoints, coord mismatch |

### Contiguity Tests

| Test | Purpose | Validation |
|------|---------|------------|
| `test_contiguous_paths` | Adjacent paths | `is_contiguous_with()` returns True when end_coord == start_coord |
| `test_non_contiguous_paths` | Gap between paths | `is_contiguous_with()` returns False |

## Validation Logic

### How We Know the Math is Correct

1. **Linear Interpolation**: `coord_to_xy` uses the formula:
   ```
   t = (coord - start_coord) / length
   x = start_point[0] + t * (end_point[0] - start_point[0])
   y = start_point[1] + t * (end_point[1] - start_point[1])
   ```
   Tests verify exact results at t=0, t=0.5, and t=1.

2. **Projection for Inverse**: `xy_to_coord` projects the point onto the line using dot product:
   ```
   t = (P - start) · (end - start) / |end - start|²
   ```
   Tests verify round-trip: `xy_to_coord(coord_to_xy(c)) == c`.

3. **Distance Calculation**: Uses perpendicular distance formula with endpoint clamping for points outside the segment.

## Known Limitations

- **Tolerance-based inverse mapping**: `xy_to_coord` returns None for points farther than `tolerance` pixels from the path. The default tolerance is 10 pixels.
- **No arc-length parameterization**: PolylinePath uses coordinate-based (not arc-length-based) interpolation, so timeline coordinates do not correspond to physical distance along the path.

## Relationship to TimeAxisPath

The `Path` classes in `loader.paths` differ from `TimeAxisPath` in `graphical/paths.py`:

| Aspect | TimeAxisPath | Path |
|--------|--------------|------|
| Coordinate system | Path-local (0 to length) | Timeline (start_coord to end_coord) |
| Primary use | Image-space operations | Timeline segment composition |
| C-map semantics | Implicit (to_2d/from_2d) | Explicit (coord_to_xy/xy_to_coord) |

Both can coexist; TimeAxisPath is lower-level while Path is designed for timeline construction.
