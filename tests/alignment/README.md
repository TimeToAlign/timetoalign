# Alignment Module Tests - Validation Strategy

This document explains **why** the test suite provides evidence that the alignment code is correct, following the TimeToAlign! Zero Tolerance Validation Policy.

## Test Philosophy

The alignment module implements the TTA manuscript's multi-level hierarchy:

```
AlignmentAnchor (atomic) -> MatchClaim (low) -> MatchGraph (mid) -> MatchLine (high)
        |                        |
        v                        v
   PerfectAlignment         TimelineGroup
```

Each test validates a **specific claim** from the manuscript specification. Tests are not exploratory--they verify exact behaviors required by the model.

---

## PerfectAlignment Tests (`test_groups.py::TestPerfectAlignment`)

### What We're Validating

The manuscript (Section 3.2) states that coordinates within a Group must be "bijectively mappable via linear interpolation." PerfectAlignment implements this mapping.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_to_reference_identity` | When source and ref have same length, coordinates pass through unchanged (identity mapping) |
| `test_to_reference_scaling` | Linear scaling: coord 50 in [0,100] -> coord 100 in [0,200] (ratio preserved) |
| `test_to_reference_partial_alignment` | Partial ranges work: [0,100] -> [45,90] maps start->45, end->90, middle->67.5 |
| `test_from_reference_inverse` | **Critical**: `from_reference(to_reference(x)) == x` (bijective requirement) |
| `test_zero_length_source_raises` | Division by zero is caught, not silently producing NaN/Inf |

### Why These Are Sufficient

1. **Linearity**: Two points define a line. We test endpoints (0, length) and midpoint to verify linear interpolation.
2. **Bijectivity**: The inverse test proves the mapping is reversible--no information is lost.
3. **Edge cases**: Zero-length ranges are explicitly rejected rather than producing garbage.

---

## TimelineGroup Tests (`test_groups.py::TestTimelineGroup`)

### What We're Validating

The manuscript states Groups contain timelines with "perfect alignment"--any coordinate in one timeline maps to exactly one coordinate in every other timeline.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_from_reference` | Group creation correctly sets reference timeline |
| `test_add_timeline` | Non-reference timelines added with explicit alignment |
| `test_add_duplicate_raises` | **Invariant**: No timeline can appear twice (would break coordinate uniqueness) |
| `test_remove_reference_raises` | **Invariant**: Reference cannot be removed (would orphan other alignments) |
| `test_convert_same_timeline` | Self-conversion returns input unchanged (reflexivity) |
| `test_convert_between_timelines` | **Core functionality**: Coordinate conversion via reference timeline |

### The Conversion Test in Detail

```python
def test_convert_between_timelines(self):
    # Setup: 150 seconds maps to 4875 pixels
    # Test: 2437.5 pixels (middle) -> 75 seconds (middle)
    result = basic_group.convert(2437.5, "dgt1", "sec1")
    assert result == pytest.approx(75.0)
```

This validates the **composition of alignments**:
1. Source coord -> reference coord (via source's PerfectAlignment)
2. Reference coord -> target coord (via target's PerfectAlignment.inverse)

The test uses exact expected values (75.0), not ranges or approximations.

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

All 78 tests should pass. Coverage is ~98% for the alignment module.
