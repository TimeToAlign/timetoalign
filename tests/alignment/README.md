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
| `TestTimelineGroupUnifiedTimestamp` | Unified TimeStamp API (Phase 6.5), InterpolationMap-based coordinate resolution |

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

## Unified TimeStamp API Tests (`test_groups.py::TestTimelineGroupUnifiedTimestamp`)

### What We're Validating

Phase 6.5 introduced a unified `TimeStamp` architecture where both `Timeline` (with children) and `TimelineGroup` (with member timelines) use the same coordinate resolution mechanism via `InterpolationMap`. This enables O(log n) coordinate conversion without table scans.

### Key API

```python
from timetoalign.core import TimeStamp, TimeIntervalStamp

# TimelineGroup unified API
group = TimelineGroup(id="my_group", timelines=[audio, dgt])
ts = group.get_unified_timestamp(75.0, "audio")
ts["dgt"]                  # Converted coordinate via InterpolationMap
ts.axis                    # 75.0 (source coordinate)
ts.source_id               # "audio"

# Interval stamps
interval = group.get_unified_interval_stamp(0.0, 100.0, "audio")
interval.duration          # 100.0
interval["dgt"]            # (start, end) tuple on dgt timeline
```

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_get_unified_timestamp_basic` | Creates valid `TimeStamp` object with correct axis and source_id |
| `test_get_unified_timestamp_coordinate_conversion` | Converts coordinates between timelines via InterpolationMap |
| `test_get_unified_timestamp_bidirectional` | Conversion works in both directions (audio->dgt and dgt->audio) |
| `test_get_unified_timestamp_unknown_timeline_raises` | KeyError for unknown timeline IDs |
| `test_get_unified_interval_stamp` | Creates `TimeIntervalStamp` with correct duration and interval conversion |
| `test_unified_timestamp_with_three_timelines` | Coordinate conversion works with 3+ timelines |
| `test_unified_timestamp_same_timeline_returns_axis` | Subscript with source ID returns axis value |
| `test_interpolation_maps_built_on_add` | Maps are built automatically when timelines are added |
| `test_interpolation_maps_updated_on_remove` | Maps are rebuilt when timelines are removed |
| `test_implements_timestamp_source_protocol` | TimelineGroup implements `TimeStampSource` protocol |
| `test_get_related_timeline_ids` | `_get_related_timeline_ids()` returns all timeline IDs |
| `test_get_available_units_returns_empty` | Groups don't have C-Maps (empty list) |

### InterpolationMap Management

The TimelineGroup maintains a dictionary of pairwise `InterpolationMap` objects:

```python
group._interpolation_maps = {
    "audio:dgt1": InterpolationMap(...),  # audio -> dgt1
    "dgt1:audio": InterpolationMap(...),  # dgt1 -> audio
    "audio:score": InterpolationMap(...), # audio -> score
    ...
}
```

Maps are:
- **Built** when `add_timeline()` is called (for all pairwise combinations)
- **Rebuilt** when `remove_timeline()` is called (removing invalidated maps)
- **Used** by `get_unified_timestamp()` for O(log n) coordinate lookup

### Relationship to Timeline TimeStamp

The same `TimeStamp` class works for both:

| Source | Method | Child/Member Access |
|--------|--------|---------------------|
| `Timeline` | `get_timestamp(coord)` | `ts["child:id"]` via offset subtraction |
| `TimelineGroup` | `get_unified_timestamp(coord, source_id)` | `ts["other_id"]` via InterpolationMap |

Both implement the `TimeStampSource` protocol, enabling code reuse.

---

## AlignmentAnchor Tests (`test_anchors.py::TestAlignmentAnchor`)

### What We're Validating

**Phase 6.2 redesign:** AlignmentAnchor is now a **pure coordinate pair** — a neutral record associating one coordinate on timeline A with one coordinate on timeline B. It contains no claim semantics (`is_synchronous`, `is_explicit`, `id` fields were removed). Claim semantics live exclusively on `MatchClaim`.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_basic_creation` | Anchor stores two timeline IDs and two coordinates (no semantic flags) |
| `test_connects` / `test_connects_both` | Query methods correctly identify connected timelines |
| `test_get_coordinate_for` | Coordinate retrieval by timeline ID |
| `test_from_dict_roundtrip` | Serialization preserves all fields exactly (no legacy fields) |
| `test_frozen_dataclass` | Immutability enforced (frozen dataclass) |

### Why Immutability Matters

```python
def test_frozen_dataclass(self):
    with pytest.raises(AttributeError):
        basic_anchor.coordinate_a = 200.0
```

Anchors are value objects — identified entirely by their coordinates. Immutability prevents subtle bugs where coordinate modifications propagate unexpectedly through a MatchGraph.

---

## MatchClaim Tests (`test_anchors.py::TestMatchClaim`)

### What We're Validating

**Phase 6.2/6.3 redesign:** MatchClaim now has `timeline_a_id` and `timeline_b_id` as **top-level fields** (not derived from anchors). Anchors are `Optional` — only synchronous claims have them. Four case-specific constructors:

| Constructor | Case | Synchronous | Anchors |
|-------------|------|-------------|---------|
| `from_events()` | Two timed events correspond | Yes (default) | Auto-built from event coordinates |
| `from_projection()` | Event projected onto timeline | Yes | Auto-built from event + target coord |
| `nomatch()` | Event has no equivalent | No | None |
| `implicit()` | Generated by MatchGraph extension | Yes | From given coordinates |

**Phase 6.8:** Legacy constructors `instant()` and `interval()` were removed. All 72 call sites across 6 test files and `table_schema.py` were migrated to direct `MatchClaim()` construction with explicit `AlignmentAnchor` objects.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_instant_creation` | Single anchor → `is_interval == False`, timeline IDs are top-level |
| `test_interval_creation` | Two anchors → `is_interval == True` |
| `test_mismatched_anchors_raises` | **Critical invariant**: Start and end anchors must connect same timeline pair |
| `test_synchronous_requires_anchor` | `__post_init__` rejects synchronous claims without anchors |
| `test_non_synchronous_rejects_anchors` | `__post_init__` rejects non-synchronous claims with anchors |
| `test_get_coordinates_for_interval` | Can retrieve both start and end coords for each timeline |
| `test_from_events_constructor` | `from_events()` builds anchor from event coordinates |
| `test_nomatch_constructor` | `nomatch()` has no anchors, `is_synchronous=False` |
| `test_implicit_constructor` | `implicit()` records `source_claim_id` for traceability |

### The Mismatch Test in Detail

```python
def test_mismatched_anchors_raises(self):
    start = AlignmentAnchor(timeline_a_id="tl1", ..., timeline_b_id="tl2", ...)
    end = AlignmentAnchor(timeline_a_id="tl1", ..., timeline_b_id="tl3", ...)  # Different!

    with pytest.raises(ValueError, match="must connect same timelines"):
        MatchClaim(timeline_a_id="tl1", timeline_b_id="tl2",
                   start_anchor=start, end_anchor=end)
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

## Offset Arithmetic Tests (`../timelines/test_offset_arithmetic.py`)

### What We're Validating

**Phase 6.1:** Parent–child coordinate transfer uses exact offset arithmetic (`child_coord = parent_coord - offset`) instead of InterpolationMap. This eliminates floating-point drift that was conceptually wrong and numerically unnecessary.

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_parent_to_child_basic` | `_get_child_coordinate()` returns exact result |
| `test_parent_to_child_out_of_bounds` | Returns None for coordinates outside child span |
| `test_child_to_parent_basic` | `_get_parent_coordinate_from_child()` returns exact result |
| `test_roundtrip_exact` | parent→child→parent produces exact original coordinate |
| `test_recursive_grandchild` | Offset arithmetic works through nested children |
| `test_timestamp_uses_offset` | `TimeStamp.get()` resolves children via offset, not InterpolationMap |
| `test_zero_offset_child` | Edge case: child at offset 0 |
| `test_multiple_children` | Multiple children resolved independently |
| `test_exact_boundary_coordinates` | Boundary values (0, length-epsilon) are handled correctly |

### Design

The `Timeline._get_interpolation_map()` method (part of the `TimeStampSource` protocol) now returns `None` for `Timeline` instances. `TimeStamp.get()` tries offset arithmetic first via duck-typing (`_get_child_coordinate`), falling back to InterpolationMap for `TimelineGroup`.

---

## MatchGraph Phase 6.4 Tests (`test_graph.py`)

### What We're Validating

Phase 6.4 overhauled the MatchGraph to enforce the design principle that only synchronous claims produce graph edges, while non-synchronous claims are stored as metadata. The `extend_to_groups()` method now creates proper `MatchClaim.implicit()` objects with `source_claim_id` traceability, and filtering supports domain/unit/timeline constraints.

### New Test Classes (Phase 6.4)

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestMatchGraphNonSynchronousClaims` | 4 | Non-synchronous claims stored as metadata, no edges created |
| `TestMatchGraphGetStamps` | 4 | `get_stamps()` returns one stamp per connected component |
| `TestMatchGraphExtendToGroupsImplicitClaims` | 5 | Implicit claims created with correct coordinates and traceability |
| `TestMatchGraphExtendToGroupsFilters` | 4 | `include_timelines`, `exclude_timelines`, `include_domains`, `include_units` |
| `TestMatchGraphFilterPhase64` | 3 | `filter()` preserves non-synchronous claims for remaining timelines |
| `TestMatchStampGetGroupCoordinates` | 2 | Fixed `get_group_coordinates()` using `timeline_ids` (was broken) |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_non_synchronous_claims_stored_as_metadata` | Non-synchronous claims don't create edges; graph has 0 edges |
| `test_synchronous_and_non_synchronous_separation` | `synchronous_claims` and `non_synchronous_claims` properties partition correctly |
| `test_get_stamps_returns_one_per_component` | Connected components yield separate stamps |
| `test_get_stamps_matches_legacy_for_single_claim` | Backward compatibility with `get_match_stamps()` |
| `test_implicit_claims_have_source_id` | Implicit claims trace back to originating explicit claim |
| `test_two_groups_full_connectivity` | Core test: 1 explicit claim between TL1∈{TL1,TL4,TL5} and TL2∈{TL2,TL6} produces 5 connected timelines with correct interpolated coordinates |
| `test_include_timelines_filter` | Only specified timelines appear in extension |
| `test_include_domains_filter` | Only timelines from specified domains appear |
| `test_filter_preserves_relevant_non_synchronous` | `filter()` keeps non-synchronous claims whose timelines survive filtering |
| `test_get_group_coordinates_basic` | Returns coordinates for all group members via `TimelineGroup.convert()` |

### The Two-Groups Connectivity Test

```python
def test_two_groups_full_connectivity(self):
    # Group A = {TL1, TL4, TL5}, Group B = {TL2, TL6}
    # One explicit claim: TL1@100 <-> TL2@200
    # After extend_to_groups():
    #   - TL4, TL5 get coordinates via Group A interpolation from TL1@100
    #   - TL6 gets coordinate via Group B interpolation from TL2@200
    #   - All 5 timelines connected in one component
    stamps = graph.get_stamps()
    assert len(stamps) == 1
    assert len(stamps[0].coordinates) == 5  # All timelines present
```

This is the core Phase 6.4 test: it verifies that group extension creates implicit claims with coordinates derived from `TimelineGroup.convert()`, producing a fully connected component from a single explicit claim.

---

## MatchLine Phase 6.5 Tests (`test_matchline.py`)

### What We're Validating

Phase 6.5 introduced `MatchLine`, an ordered sequence of `MatchStamp` objects for a given source timeline. It is the bridge between `MatchGraph` (Phase 6.4) and `WarpMap` (Phase 6.6). A MatchLine collects stamps, sorts them by source coordinate, and exposes `get_coordinate_pairs()` for WarpMap construction.

### Test Classes

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestMatchLineBasic` | 6 | Construction, sorting, empty/single stamp, filtering of stamps missing source |
| `TestTargetTimelineIds` | 4 | `target_timeline_ids()` returns only timelines with >= 2 stamps |
| `TestGetCoordinatePairs` | 6 | Extraction of `(source_coord, target_coord)` pairs, partial stamps, error on self-target |
| `TestFromClaims` | 5 | `from_claims()` with ordering, interval claims, group extension, non-synchronous exclusion |
| `TestFromGraphs` | 6 | `from_graphs()` merging, deduplication, Hendrix M6-M9 pattern |
| `TestMatchLineSerialization` | 4 | `to_dict()`/`from_dict()` round-trip, `__repr__` |
| `TestMatchLineIntegration` | 2 | Thoresen segment claims end-to-end, group extension coordinate pairs |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_stamps_sorted_by_source_coordinate` | Stamps are auto-sorted by source coordinate even if provided out of order |
| `test_stamps_without_source_are_dropped` | Stamps missing the source timeline are silently dropped (with log warning) |
| `test_target_timeline_ids_two_or_more` | `target_timeline_ids()` excludes timelines appearing in < 2 stamps (minimum for interpolation) |
| `test_same_as_source_raises` | `get_coordinate_pairs()` raises ValueError when target == source |
| `test_from_claims_with_group_extension` | `from_claims()` with group parameters adds group member coordinates (audio mapped linearly) |
| `test_from_claims_non_synchronous_excluded` | Non-synchronous claims (NOMATCH) do not produce stamps |
| `test_from_graphs_hendrix_pattern` | Four contiguous M-box graphs merged into 5 unique source coordinates (boundary deduplication) |
| `test_from_graphs_keeps_richer_stamp` | Deduplication keeps the stamp with more timelines |
| `test_thoresen_matchline` | Thoresen segment claims produce correct boundary pairs: (0,0) to (4835,4328) |

### The Hendrix Pattern Test

```python
def test_from_graphs_hendrix_pattern(self):
    # 4 contiguous M-boxes, each with 2 boundary claims
    # Boundaries: 0, 100, 200, 300, 400
    # Adjacent M-boxes share boundary coordinates -> deduplicated
    graphs = [MatchGraph([...]) for i in range(4)]
    line = MatchLine.from_graphs(graphs, source_timeline_id="score")
    assert line.n_stamps == 5  # 5 unique coordinates
    assert line.source_coordinates == [0.0, 100.0, 200.0, 300.0, 400.0]
```

This validates the Hendrix M6-M9 use case from the conceptual model: multiple MatchGraphs representing contiguous subsections can be merged into a single ordered MatchLine for WarpMap generation.

---

## AlignmentBundle Phase 6.7 Tests (`test_bundle.py`)

### What We're Validating

Phase 6.7 replaced the ad-hoc `TableMap`-based WarpMap dictionary in `AlignmentBundle` with the new `MatchLine` → `WarpMap` pipeline. The bundle now lazily builds `WarpMap` objects on first cross-group `transfer()` call and caches them, invalidating the cache when `add_match_claims()` is called.

### New Test Classes (Phase 6.7)

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestCrossGroupTransfer` | 6 | `transfer()` across groups via WarpMap (direct, boundary, interpolation, reverse, non-existent path) |
| `TestIndirectTransfer` | 2 | Within-group convert then cross-group warp (indirect path) |
| `TestGroupExtension` | 2 | Claims connect score→audio; transfer propagates to midi via group membership |
| `TestGetTimestampAtCrossGroup` | 3 | `get_timestamp_at()` propagation across groups (flat, nested, prefix formats) |
| `TestCommensurabilityWithClaims` | 3 | `are_commensurable()` returns True when claims connect groups (direct + via membership) |
| `TestCacheInvalidation` | 2 | WarpMap cache cleared on `add_match_claims()` |
| `TestEdgeCases` | 6 | No claims, non-synchronous claims, single claim insufficient for WarpMap |
| `TestAddMatchClaimsAPI` | 3 | Chaining, accumulation, no-arg validation |
| `TestAddGroupWithCrossGroupTransfer` | 4 | `add_group()` + cross-group claims + transfer end-to-end |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_cross_group_transfer_direct` | Score@0.0 → Audio@0.0 via WarpMap (exact boundary) |
| `test_cross_group_transfer_interpolation` | Interior coordinates interpolated correctly |
| `test_cross_group_transfer_reverse` | Bidirectional: Audio→Score as well as Score→Audio |
| `test_indirect_transfer_through_group` | MIDI→Audio via group convert, then Audio→Score via WarpMap |
| `test_group_extension_transfer` | Claims between Score and Audio propagate to MIDI via recording group membership |
| `test_get_timestamp_at_cross_group_flat` | `get_timestamp_at()` returns coordinates for timelines in both groups |
| `test_commensurable_via_claims` | `are_commensurable()` detects cross-group connectivity through claims |
| `test_cache_invalidated_on_add_claims` | New claims clear cached WarpMaps; subsequent transfer uses updated data |
| `test_no_cross_group_claims_returns_none` | `transfer()` returns None when no claims connect the groups |
| `test_non_synchronous_claims_no_transfer` | Non-synchronous claims (NOMATCH) don't produce WarpMaps |

### Design: Lazy WarpMap Cache

```python
# Bundle maintains:
_warp_map_cache: dict[tuple[str, str], WarpMap]  # (source_group, target_group) -> WarpMap
_cache_claims_hash: int  # Invalidation key

# On transfer():
warp = self._get_or_build_warp_map(source_group_id, target_group_id)
result = warp.forward(source_coord)
```

The cache is keyed by `(source_group_id, target_group_id)` and invalidated whenever `add_match_claims()` is called. This avoids redundant `MatchLine.from_claims()` + `WarpMap.from_match_line()` computation for repeated queries.

---

## WarpMap Phase 6.6 Tests (`test_warpmap.py`)

### What We're Validating

Phase 6.6 introduced `WarpMap`, a standalone class that materialises warped timeline copies from alignment data. It wraps an `InterpolationMap` internally for O(log n) coordinate conversion and bridges the gap between `MatchLine` (Phase 6.5) and `AlignmentBundle` (Phase 6.7).

### Test Classes

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestWarpMapConstruction` | 5 | Basic init, `from_match_line()`, `from_coordinate_pairs()`, rejection of <2 points |
| `TestForwardInverse` | 5 | Linear mapping, identity, extrapolation, inverse round-trip |
| `TestMaterialise` | 7 | Event warping (instant/interval), child warping, region warping, event count, empty timeline |
| `TestMaterialiseTypeConversion` | 3 | CLT→CPT type conversion, unit propagation, region unit conversion |
| `TestSerialization` | 4 | `to_dict()`/`from_dict()` round-trip, repr |
| `TestMultiTarget` | 1 | Different WarpMaps from same MatchLine for different targets |
| `TestIntegrationWithClaims` | 1 | End-to-end: MatchClaim → AlignmentAnchor → MatchLine → WarpMap |
| `TestEdgeCases` | 10 | Non-linear warping, single-point rejection, degenerate intervals, large datasets, overlapping regions |

### Key Evidence

| Test | Validates |
|------|-----------|
| `test_forward_inverse_roundtrip` | `inverse(forward(x)) ≈ x` for all x in domain |
| `test_materialise_warps_instant_events` | Instant event coordinates warped correctly (reads `start` struct dict, not `instant`) |
| `test_materialise_warps_interval_events` | Start/end/duration all warped; duration uses `forward(start+dur) - forward(start)` for non-linear correctness |
| `test_materialise_warps_children` | Child offsets converted, child count preserved |
| `test_materialise_warps_regions` | Region boundaries converted, region names preserved |
| `test_type_conversion_clt_to_cpt` | Source CLT (quarters) → target CPT (seconds): correct type and unit |
| `test_full_pipeline` | MatchClaim → AlignmentAnchor → MatchLine → WarpMap → forward/inverse |

### EventData Struct Dict Discovery

A key implementation discovery documented in the tests: EventData converts `{"instant": 0.0}` to `{"start": {"value": 0.0, "numerator": None, "denominator": None}}` internally. The `instant` key is NOT preserved — it becomes `start`. The `temporal_type` field distinguishes instant vs interval events. WarpMap's `_warp_events()` handles both the struct dict format and plain floats.

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

**Phase 6.8 Status**: Deprecated `MatchClaim.instant()`/`.interval()` removed; all callers migrated. Full alignment suite: 367 passed, 56 skipped. The skips are pre-existing stubs in `test_thoresen_poc.py` and graphical loader tests requiring PyMuPDF.

### Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_groups.py` | 58 | TimelineGroup, GroupTimestamp, and unified TimeStamp API |
| `test_bundle.py` | 61 | AlignmentBundle: 30 original (linear/partial alignment) + 31 new (Phase 6.7: cross-group transfer, timestamps, commensurability, caching, edge cases) |
| `test_anchors.py` | ~55 | AlignmentAnchor (Phase 6.2), MatchClaim (Phase 6.3), MatchMetadata |
| `test_graph.py` | 54 | MatchGraph operations (Phase 6.4: +19 tests for implicit claims, filtering, stamps) |
| `test_matchline.py` | 33 | MatchLine construction, from_claims, from_graphs, coordinate pairs, serialization (Phase 6.5) |
| `test_warpmap.py` | 36 | WarpMap construction, forward/inverse, materialise (events, children, regions, type conversion), serialization, end-to-end pipeline (Phase 6.6) |
| `test_supra_integration.py` | 13 | SUPRA piano roll workflow (partial alignment) |
| `test_thoresen_poc.py` | 35 | Thoresen graphical analysis workflow |
| `../timelines/test_offset_arithmetic.py` | 11 | Parent–child offset arithmetic (Phase 6.1) |

### Deprecated Tests

The following test methods use the deprecated `PerfectAlignment` class and will be removed in a future version:

- `TestBackwardCompatibility.test_from_reference_still_works`
- `TestBackwardCompatibility.test_iter_timelines_still_works`

These tests verify backward compatibility during the migration period.
