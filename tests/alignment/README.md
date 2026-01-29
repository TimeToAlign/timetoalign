# Alignment Module Tests - Validation Strategy

This document explains **why** the test suite provides evidence that the alignment code is correct, following the TimeToAlign! Zero Tolerance Validation Policy.

## Test Philosophy

The alignment module implements the TTA manuscript's multi-level hierarchy:

```
AlignmentAnchor (atomic) -> MatchClaim (low) -> MatchGraph (mid) -> MatchLine (high)
        |                        |
        v                        v
   start/end params         TimelineGroup (timestamp table)
```

**NOTE (Phase 7.4):** The `PerfectAlignment` class is **deprecated**. TimelineGroup now uses a timestamp-based architecture where alignment is specified via `start`/`end` parameters to `add_timeline()`. See `test_groups.py` for the new API.

Each test validates a **specific claim** from the manuscript specification. Tests are not exploratory--they verify exact behaviors required by the model.

---

## TimelineGroup Architecture (Phase 7.4)

### Timestamp Table Design

The group stores alignment data as a PyArrow table:

```
| dgt1_image | dgt1_holes | dlt1_raw |
|------------|------------|----------|
| 0.0        | null       | null     |  <- group start (image only)
| 15343.0    | 0.0        | 0.0      |  <- musical region starts
| 293119.0   | 277776.0   | 871800.0 |  <- musical region ends
| 299400.0   | null       | null     |  <- group end (image only)
```

Between any two adjacent rows, ALL non-null timelines have bijective linear mapping.

### Key Changes from PerfectAlignment

| Before (deprecated) | After (Phase 7.4) |
|---------------------|-------------------|
| `PerfectAlignment(source_start=0, source_end=277776, ref_start=15343, ref_end=293119)` | `group.add_timeline(holes, start=(15343.0, "dgt1"), end=(293119.0, "dgt1"))` |
| Per-timeline alignment objects | Timestamp table with one column per timeline |
| `group.reference_timeline_id` | Reference timeline is first column in table |

---

## TimelineGroup Tests (`test_groups.py`)

### What We're Validating

The manuscript states Groups contain timelines with "perfect alignment"--any coordinate in one timeline maps to exactly one coordinate in every other timeline.

### Key Test Classes (Phase 7.4)

| Class | Tests |
|-------|-------|
| `TestGroupTimestamp` | View object creation, coordinate access, `present_timelines` property |
| `TestTimelineGroupCreation` | Empty groups, groups with initial timelines, ID generation |
| `TestTimelineGroupAddTimeline` | Linear alignment, partial alignment with `start`/`end`, duplicate detection |
| `TestTimelineGroupTimestamps` | Timestamp count, boundary retrieval, table structure |
| `TestTimelineGroupInterpolation` | `get_timestamp_at()` for exact matches and interior points |
| `TestTimelineGroupConversion` | `convert()` method, same-timeline identity, cross-timeline mapping |
| `TestTimelineGroupLocking` | Lock/unlock, `allow_extension` parameter |
| `TestBackwardCompatibility` | Deprecated `from_reference()` and `iter_timelines()` methods |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_add_with_partial_alignment` | Partial ranges work: `start=(15343, "dgt1")` maps holes 0 -> image 15343 |
| `test_interpolation_exact_boundary` | Exact boundary coordinates return stored values (no interpolation) |
| `test_interpolation_interior_point` | Interior points are linearly interpolated |
| `test_conversion_same_timeline` | Self-conversion returns input unchanged (reflexivity) |
| `test_conversion_cross_timeline` | **Core functionality**: Coordinate conversion via timestamp lookup |
| `test_floating_point_precision` | Boundary values are EXACT (no floating-point error from interpolation round-trip) |

### The Floating-Point Precision Test

```python
def test_floating_point_precision(self):
    # Partial alignment: holes [0, 277776] -> image [15343, 293119]
    group.add_timeline(holes, start=(15343.0, "dgt1"), end=(293119.0, "dgt1"))

    # Boundary coordinates must be EXACT
    result = group.convert(0.0, source="holes", target="dgt1")
    assert result == 15343.0  # EXACT, not pytest.approx()
```

This test validates that the source timeline's coordinate is stored exactly, not computed through interpolation (which would introduce floating-point error).

---

## AlignmentAnchor Tests (`test_anchors.py::TestAlignmentAnchor`)

### What We're Validating

The manuscript defines an anchor as "a claim that two coordinates from different timelines are equivalent." Anchors are the atomic unit of alignment.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_basic_creation` | Anchor stores two timeline IDs and two coordinates |
| `test_connects` / `test_connects_both` | Query methods correctly identify connected timelines |
| `test_conceptual_anchor` | `is_synchronous=False` flag preserved (for non-temporal matches) |
| `test_inferred_anchor` | `is_explicit=False` flag preserved (for Group-extended anchors) |
| `test_from_dict_roundtrip` | Serialization preserves all fields exactly |

### Why Immutability Matters

```python
def test_frozen_dataclass(self):
    with pytest.raises(AttributeError):
        basic_anchor.coordinate_a = 200.0
```

Anchors represent **claims**. A claim cannot change after creation--you make a new claim instead. This prevents subtle bugs where anchor modifications propagate unexpectedly through a MatchGraph.

---

## MatchClaim Tests (`test_anchors.py::TestMatchClaim`)

### What We're Validating

The manuscript defines a Match as connecting **events** (not just coordinates). Events can be instants (single point) or intervals (start + end). A MatchClaim implements this with 1 or 2 anchors.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_instant_creation` | Single anchor -> `is_interval == False` |
| `test_interval_creation` | Two anchors -> `is_interval == True` |
| `test_mismatched_anchors_raises` | **Critical invariant**: Start and end anchors must connect same timeline pair |
| `test_get_coordinates_for_interval` | Can retrieve both start and end coords for each timeline |
| `test_interval_factory` | Convenience method produces correct structure |

### The Mismatch Test in Detail

```python
def test_mismatched_anchors_raises(self):
    start = AlignmentAnchor(timeline_a_id="tl1", ..., timeline_b_id="tl2", ...)
    end = AlignmentAnchor(timeline_a_id="tl1", ..., timeline_b_id="tl3", ...)  # Different!

    with pytest.raises(ValueError, match="must connect same timelines"):
        MatchClaim(start_anchor=start, end_anchor=end)
```

This prevents creating semantically invalid claims. An interval match between `(tl1, tl2)` and `(tl1, tl3)` would represent... what? The constraint catches this at construction time.

---

## MatchMetadata Tests (`test_anchors.py::TestMatchMetadata`)

### What We're Validating

The manuscript requires matches to include "the agent/author, decision criteria, and certainty level." This is provenance data for research reproducibility.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_certainty_validation` | Certainty must be in [0, 1] |
| `test_certainty_boundaries` | Boundary values (0.0, 1.0) are valid |
| `test_from_dict_roundtrip` | Datetime serialization works (ISO format) |

---

## SUPRA Integration Tests (`test_supra_integration.py`)

### What We're Validating

The SUPRA (Stanford University Piano Roll Archive) tests validate the **partial alignment** feature using real-world data from piano roll digitization. This is the canonical use case for the new Phase 7.4 API.

### Data Source

| Parameter | Value | Description |
|-----------|-------|-------------|
| Roll | WM 990 | Welte-Mignon red roll, T-100 |
| DRUID | fd660zf8362 | Stanford Digital Repository ID |
| IMAGE_HEIGHT | 299,400 | Full image height in pixels |
| FIRST_HOLE | 15,343 | Pixel row of first musical hole |
| LAST_HOLE | 293,119 | Pixel row of last musical hole |
| MUSICAL_LENGTH | 277,776 | `last_hole - first_hole` |
| MUSICAL_HOLES | 30,092 | Individual hole punches |
| MUSICAL_NOTES | 8,718 | Notes after merging adjacent holes |

### Test Classes

| Class | Tests |
|-------|-------|
| `TestSUPRADataLoading` | `IIIFManifestLoader` dimensions, `ATONLoader` metadata (EXACT values) |
| `TestSUPRATimelineCreation` | Timeline lengths match loader data |
| `TestSUPRAAlignmentBundle` | Partial alignment via `start`/`end` parameters, coordinate transfer |
| `TestSUPRAOrderIndependence` | Same alignment specifications produce same results regardless of add order |
| `TestSUPRASummary` | Bundle summary structure and determinism |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_iiif_dimensions_exact` | IIIF loader returns `width=4096, height=299400` (EXACT) |
| `test_aton_metadata_exact` | ATON loader returns EXACT counts from gold standard |
| `test_transfer_holes_to_image` | Holes coord 0 -> Image pixel 15343 (EXACT, no tolerance) |
| `test_transfer_image_to_holes` | Inverse transfer: Image 15343 -> Holes 0 (EXACT) |
| `test_three_timeline_same_partial_alignment` | Three timelines with same partial alignment produce consistent transfers |

### Alignment Diagram

```
DGT1 (Full Image: 0 - 299,400 px)
  |
  +-- [15,343 px] --- DGT1_holes (Musical Region: 0 - 277,776 px) --- [293,119 px]
                            |
                            | Partial alignment via start/end
                            v
                      DLT1 (MIDI: 0 - 871,800 ticks)
```

### ZERO TOLERANCE Policy Compliance

Per the engineering standards:

1. **EXACT COUNTS REQUIRED**: All assertions use exact expected values from the gold standard
2. **NO TOLERANCE**: Boundary coordinates (0, 15343, 293119, 277776) are compared with `==`, not `pytest.approx()`
3. **DOCUMENTED ROOT CAUSE**: Interior point comparisons document why floating-point arithmetic is involved (irrational scale factors)

---

## Integration Tests

### Thoresen PoC Setup (`test_groups.py::TestGroupIntegration`)

```python
def test_thoresen_poc_setup(self):
    """
    DGT1 (2009): 5 equal segments, 4875 pixels total
    DGT2 (2010): 5 varying segments, 4328 pixels total
    Both map to 150 seconds of audio.
    """
```

This test validates that the Group infrastructure can model the Thoresen proof-of-concept from the manuscript. It creates two independent groups (DGT1+audio, DGT2+audio) and verifies coordinate conversions match expected values.

**Why exact values**: The pixel counts (4875, 4328) and segment lengths come from the manuscript. The test verifies that our implementation produces the same results the manuscript describes.

### Thoresen Segment Claims (`test_anchors.py::TestClaimIntegration`)

```python
def test_thoresen_segment_claims(self):
    """Creates 5 interval MatchClaims for segment correspondence."""
    segment_lengths_dgt1 = [975, 975, 975, 975, 975]
    segment_lengths_dgt2 = [866, 867, 867, 864, 864]
```

This test validates that MatchClaims can represent the segment-to-segment correspondence needed for the Thoresen PoC. It verifies:
- All 5 claims are intervals (not instants)
- All claims connect the same timeline pair
- Cumulative offsets are correct (first segment starts at 0, last ends at total length)

---

## What's NOT Tested (Yet)

The following will be validated in Week 3-4:

1. **WarpMap creation** - Piecewise linear interpolation from MatchLine
2. **Event H transfer** - The manuscript's canonical validation: transfer an event from DGT2 to DGT1

---

## Graphical Loader Tests (`test_graphical_loader.py`)

### What We're Validating

The graphical loader creates `GraphicalBundle` objects from images, mapping 2D pixel coordinates to 1D timeline coordinates.

### Key Components

| Component | Purpose |
|-----------|---------|
| `TimeAxisPath` | Abstract path mapping 1D -> 2D coordinates |
| `HorizontalLinePath` | Time axis as horizontal line (most common) |
| `ImageSource` | Unified image interface (files, PDFs) |
| `GraphicalSegment` | Source + path + timeline offset |
| `GraphicalBundle` | Complete timeline with coordinate conversion |
| `GraphicalLoader` | Factory for building bundles |

### Test Data

Test images are in `tests/alignment/data/thoresen/`:

| File | Description |
|------|-------------|
| `thoresen_2009_sound-objects_p312_page1_1.jpeg` | DGT1: single image, 5 horizontal systems |
| `thoresen_2010_form-building-patterns_p90-91_page*.jpeg` | DGT2: 5 separate images |

### Coordinate Data (from Applications.ipynb)

**DGT1 (2009):**
- Single image with 5 horizontal systems
- x-boundaries: (2, 969) for all systems = 967 pixels each
- y-positions: [18, 205, 396, 588, 785]
- Total width: 4835 pixels

**DGT2 (2010):**
- 5 separate images with varying dimensions
- Segment bounds (x0, x1, y): [(8,874,15), (7,874,18), (7,874,19), (8,872,15), (9,873,20)]
- Segment lengths: [866, 867, 867, 864, 864]
- Total width: 4328 pixels

**Event H (rect_h2):**
- Segment index: 1 (second segment)
- Local coordinates: [378, 517] (385-7 to 385-7+139)
- Global coordinates: [866+378, 866+517] = [1244, 1383]

### Why These Values Are Exact

The pixel coordinates come from:
1. Manual measurement in image editing software (x0, x1, y for each system)
2. Ground truth TSV files with annotated event locations
3. Cross-validation between Applications.ipynb calculations and test assertions

Any discrepancy between these sources indicates a bug that must be investigated--not tolerated

---

## Running the Tests

```bash
cd timetoalign
python -m pytest tests/alignment/ -v
```

**Phase 7.4 Status**: 272 tests pass, 2 skipped. Coverage is ~80% for the alignment module.

### Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_groups.py` | 45 | TimelineGroup and GroupTimestamp (Phase 7.4 API) |
| `test_bundle.py` | 30 | AlignmentBundle with linear and partial alignment |
| `test_anchors.py` | 50 | AlignmentAnchor, MatchClaim, MatchMetadata |
| `test_graph.py` | 35 | MatchGraph operations |
| `test_supra_integration.py` | 13 | SUPRA piano roll workflow (partial alignment) |
| `test_thoresen_poc.py` | 35 | Thoresen graphical analysis workflow |

### Deprecated Tests

The following test methods use the deprecated `PerfectAlignment` class and will be removed in a future version:

- `TestBackwardCompatibility.test_from_reference_still_works`
- `TestBackwardCompatibility.test_iter_timelines_still_works`

These tests verify backward compatibility during the migration period.
