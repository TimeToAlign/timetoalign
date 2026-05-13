# Unfolding via Slicing — Test Strategy & Validation

**Phase:** 3.10 (extended)
**Test file:** `test_unfolding.py`
**Total tests:** 88 (78 original + 10 group unfolding)
**Implementation prompt:** `.agent/prompts/unfolding_via_slicing.md`

---

## 1. Problem Under Test

The `create_unfolded_timeline()` function produces unfolded timelines from a
folded score timeline and a Flow object. The original implementation (flow.py)
operated in MC-number space rather than quarterbeat space, producing wrong
coordinates for any score with non-uniform measure durations.

Phase 3.10 replaces per-event FlowMap coordinate remapping with **structural
slicing**: compute QB boundaries from Flow + MeasureData, extract slices of
the source timeline at those boundaries, and concatenate the slices into a
new SegmentLine.

The extension (group unfolding) demonstrates that one FlowMap can unfold an
entire TimelineGroup — regardless of member domains — by resolving section
boundaries through GroupTimestamps and slicing each timeline at the
corresponding interpolated coordinates.

Key primitives:
1. `Timeline.get_slice(start, end)` — extract a portion of a timeline
2. `SegmentLine.get_slice(start, end)` — override for nested SegmentLines
3. `compute_qb_sections(flow, controller)` — convert Flow sections to QB ranges
4. Rewritten `create_unfolded_timeline()` — slice + concatenate approach

---

## 2. Testing & Validation Strategy

### 2.1 Four-Layer Testing Pyramid

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

### 2.2 Unit Tests: `TestGetSlice`

**What:** Validates the new `Timeline.get_slice()` method in isolation
using synthetic timelines with known events.

**Why here:** `get_slice()` is the core primitive upon which unfolding depends.
It must correctly handle:
- Coordinate shifting (all coords shifted by `-start`)
- Left-inclusive, right-exclusive boundary semantics `[start, end)`
- Interval event truncation at slice boundaries
- Child timeline recursive slicing
- Number type preservation (Fraction stays Fraction)
- Concrete class preservation (CLT.get_slice() returns CLT)

**Strategy:** Construct a `ContinuousLogicalTimeline` with known events at
known coordinates, slice at various boundaries, and assert exact coordinate
values in the result. No external data files required.

**Validation criteria (ZERO TOLERANCE):**
- Exact event count in slice
- Exact coordinate values after shifting
- Exact truncated interval start/end
- Exact slice length = `end - start`
- `type(slice)` is same as `type(source)`
- `slice.number_type` == `source.number_type`

### 2.3 Unit Tests: `TestComputeQBSections`

**What:** Validates QB boundary computation from Flow + FlowController.

**Why here:** The QB boundary computation translates MC-based
PlaythroughSection ranges into quarterbeat coordinate ranges using
MeasureUnit `duration_qb` data. This is the critical step that eliminates
the MC-space bug.

**Strategy:**
1. Load folded measures TSV via TSVLoader → FlowController
2. Compute Flow (DEFAULT mode) → get PlaythroughSections
3. Call `compute_qb_sections(flow, controller)`
4. Validate each section's QB start against the `quarterbeats` column in
   the folded TSV (the TSV's `quarterbeats` column IS the gold standard
   for MC-to-QB mapping)

**Validation criteria (ZERO TOLERANCE):**
- `qb_start` for each section matches the `quarterbeats` value of the
  section's `mc_start` row in the folded TSV
- `qb_end` for each section matches the `quarterbeats` value of the
  section's `mc_end` row (or `quarterbeats + duration_qb` of the last MC
  if `mc_end` is beyond the final MC)
- Sum of all `(qb_end - qb_start)` equals `flow.total_quarterbeats`

### 2.4 Integration Tests: `TestSegmentLineAssembly`

**What:** Validates that slices can be correctly assembled into a SegmentLine.

**Strategy:** Use a synthetic timeline, slice it at known boundaries, and
concatenate slices into a SegmentLine. Verify structural properties.

**Validation criteria:**
- Segments are contiguous (each starts where previous ended)
- Total SegmentLine length = sum of slice lengths
- All events from individual slices appear in the SegmentLine
- Segment type matches source timeline class

### 2.5 Gold Standard Tests: `TestUnfoldingGoldStandard`

**What:** End-to-end validation of the complete unfolding pipeline against
ms3-generated `*_unfolded.measures.tsv` files.

**Strategy:**
1. Load folded measures TSV → FlowController → compute Flow
2. Create source timeline from MeasureData
3. Call `create_unfolded_timeline(source, flow, controller)`
4. Compare result against gold standard unfolded TSV

**Validation criteria (ZERO TOLERANCE):**
- **EXACT** row count match
- **EXACT** `mc_playthrough` sequence (monotonic 1, 2, 3, …)
- **EXACT** `mn_playthrough` values including suffixes (a, b, c, …)
- **EXACT** `quarterbeats` values as `Fraction` (NOT float comparison)
- **EXACT** total unfolded length = `final_quarterbeats + final_duration_qb`
- **EXACT** `mc` values (original folded MC, may repeat)
- **EXACT** `mn` values (original folded MN, may repeat)

---

## 3. Gold Standard Data Inventory

All files under `tests/data/score/`. The `*_unfolded.measures.tsv` files are
generated by ms3 (the MuseScore 3 corpus analysis library) and represent the
authoritative unfolded measure sequences.

### 3.1 Specimen Summary

| # | Specimen Key | Folded | Unfolded | Ratio | Challenge |
|---|-------------|--------|----------|-------|-----------|
| 1 | `rachmaninoff` | 374 | 374 | 1.00 | No flow control — baseline |
| 2 | `polyrhythm_only` | 14 | 14 | 1.00 | Line breaks only |
| 3 | `musete` | 58 | 138 | 2.38 | D.S. al Fine, anacrusis, 6/8 |
| 4 | `rondeau` | 60 | 138 | 2.30 | Rondeau form (D.S.) |
| 5 | `op18_no4_mov4` | 226 | 291 | 1.29 | Repeats + Volta brackets |
| 6 | `woo71` | 397 | 505 | 1.27 | Complex split bars |
| 7 | `flow_only` | 15 | 30 | 2.00 | D.S./D.C. + Voltas |

### 3.2 Exact Final Values (for test assertions)

| Specimen | Last mc_playthrough | Last mn_playthrough | Last quarterbeats | Last duration_qb | Total QB |
|----------|--------------------|--------------------|-------------------|------------------|----------|
| rachmaninoff | 374 | 374a | 2989/2 | 4 | 2997/2 |
| polyrhythm_only | 14 | 9a | 42 | 3 | 45 |
| musete | 138 | 14e | 765/2 | 3/2 | 384 |
| rondeau | 138 | 56b | 194 | 1 | 195 |
| op18_no4_mov4 | 291 | 226a | 1113 | 3 | 1116 |
| woo71 | 505 | 371a | 2153/2 | 3/2 | 1078 |
| flow_only | 30 | 3a | 73 | 2 | 75 |

### 3.3 File Paths

Folded measures TSV files (inputs):
```
rachmaninoff_concerto2/score/Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff.measures.tsv
flow_control/polyrythm_only/out_of_the_flow_experience-polyrhythm_only.measures.tsv
couperin_concerts/c05n05_musete.measures.tsv
couperin_concerts/c11n08_Rondeau.measures.tsv
beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/op18_no4_mov4_flow.measures.tsv
beethoven_woo71/WoO71.measures.tsv
flow_control/flow_only/out_of_the_flow_experience-flow_only.measures.tsv
```

Unfolded measures TSV files (gold standard):
```
rachmaninoff_concerto2/score/Piano_Concerto_No._2_Opus_18_1st_Movement__Rachmaninoff_unfolded.measures.tsv
flow_control/polyrythm_only/out_of_the_flow_experience-polyrhythm_only_unfolded.measures.tsv
couperin_concerts/c05n05_musete_unfolded.measures.tsv
couperin_concerts/c11n08_Rondeau_unfolded.measures.tsv
beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/op18_no4_mov4_flow_unfolded.measures.tsv
beethoven_woo71/WoO71_unfolded.measures.tsv
flow_control/flow_only/out_of_the_flow_experience-flow_only_unfolded.measures.tsv
```

### 3.4 Unfolded TSV Schema

Key columns in `*_unfolded.measures.tsv`:

| Column | Type | Description |
|--------|------|-------------|
| `mc` | int | Original MC from folded score (repeats for repeated measures) |
| `mn` | int/str | Original MN (repeats for repeated measures) |
| `mc_playthrough` | int | Monotonically increasing index in unfolded sequence |
| `mn_playthrough` | str | MN with occurrence suffix (a, b, c, …) |
| `quarterbeats` | str(Fraction) | Cumulative position in unfolded sequence |
| `duration_qb` | str(float) | Measure duration in quarter beats |

The `quarterbeats` column contains fraction strings (e.g., `3/2`, `765/2`)
or integer strings (e.g., `0`, `42`). These must be parsed with
`fractions.Fraction()` for exact comparison.

The `duration_qb` column contains float strings (e.g., `1.5`, `3.0`, `4.0`).
These should also be converted to `Fraction` for exact comparison.

---

## 4. Parallel-Safety Considerations

All tests in this file are parallel-safe (pytest-xdist compatible):

- **No shared mutable state:** Each test creates its own timeline instances.
  FlowController/TSVLoader are constructed fresh per fixture invocation.
- **No inter-test ordering:** Tests are fully independent.
- **No file mutations:** Gold standard TSVs are read-only.
- **Session-scoped fixtures** are used only for read-only data loading
  (loading TSV files) to avoid redundant I/O across workers.

---

## 5. Relationship to Existing Tests

| Existing Test File | Relationship |
|-------------------|-------------|
| `test_flow.py` | Tests Flow computation (MC sequences). We reuse the same `data_dir` fixture pattern and TSVLoader approach. |
| `test_flow_csv_validation.py` | Tests flow CSV serialization parity. Unaffected by unfolding changes. |
| `test_flow_control_parity.py` | Tests cross-loader flow computation parity. Unaffected. |
| `test_types.py` | Tests SegmentLine basics. `get_slice()` indirectly fixes `get_slice_from_segments()`. |
| `test_base.py` | Tests Timeline fundamentals. `get_slice()` is a new method tested here. |

---

## 6. Known Limitations and Edge Cases

### 6.1 Anacrusis (Incomplete First Measure)
The Musete specimen begins with an anacrusis (MC 1, duration 1.5 QB instead of
3.0 QB). The unfolding must correctly handle this: when MC 1 repeats, the
repeated instance also has duration 1.5 QB. The gold standard confirms this.

### 6.2 Split Bars (WoO71)
Beethoven WoO71 has "split bars" where a single notated measure is divided
into two MCs. The unfolding must preserve these splits exactly. The gold
standard has 505 unfolded rows from 397 folded rows.

### 6.3 Volta Brackets (Op.18 No.4 iv)
Volta brackets cause different MCs to be played on different passes. The
unfolding must select the correct volta on each pass. The gold standard
confirms 291 unfolded rows from 226 folded rows.

### 6.4 Rondeau Form (c11n08)
The Rondeau has a complex return pattern (ABACADA). Each section return
uses a D.S.-like mechanism. The gold standard confirms 138 unfolded rows.

### 6.5 D.S./D.C. with Voltas (flow_only)
The flow_only specimen combines D.S., D.C., and volta brackets. This is
the most complex flow control test case. 30 unfolded rows from 15 folded.

---

## 7. Group Unfolding Tests: `TestGroupUnfolding`

### 7.1 What

Validates that a single FlowMap (derived from one score timeline's flow)
can unfold ALL timelines in a TimelineGroup, regardless of their domain.
Uses the Beethoven Op.18 No.4 iv multimodal score group:

| Timeline | Type | Domain | Length |
|----------|------|--------|--------|
| CLT1 | ContinuousLogicalTimeline | Logical | 878.5 quarters |
| DGT1 | SegmentLine[SegmentLine[DGT]] | Graphical | 106,425 pixels |
| OpenScore | ContinuousLogicalTimeline | Logical | 878.5 quarters |

The FlowMap has 11 PlaythroughSections, producing 1116 unfolded QB total.

### 7.2 Strategy

1. Build the score group with 3 timelines (CLT1, DGT1, OpenScore)
2. Compute QB sections from the ABC v2.6 FlowController
3. For each PlaythroughSection, retrieve start/end GroupTimestamp
4. Use interpolated coordinates for each timeline to `get_slice()`
5. `append_segment()` to build unfolded SegmentLines

### 7.3 Test Inventory (10 tests)

| Test | Validates |
|------|-----------|
| `test_prerequisite_folded_lengths` | Source timelines have expected folded lengths (878.5 QB) |
| `test_prerequisite_qb_sections` | QB sections count (11) and total (1116 QB) |
| `test_all_timelines_produce_correct_segment_count` | Each unfolded timeline has 11 segments |
| `test_clt1_unfolded_length` | CLT1 unfolded = 1116 QB |
| `test_openscore_unfolded_length` | OpenScore unfolded = 1116 QB |
| `test_dgt1_unfolded_longer_than_original` | DGT1 unfolded > 106,425 px |
| `test_segments_are_contiguous` | All SegmentLines have contiguous segments |
| `test_segment_types_preserved` | CLT1→CLT, OpenScore→CLT, DGT1→SegmentLine |
| `test_clt1_segment_lengths_match_qb_sections` | Individual segment lengths match section durations |
| `test_create_unfolded_timeline_matches_group_unfolding` | Consistency: single-TL vs group unfolding |

### 7.4 Helpers and Fixtures

| Name | Type | Purpose |
|------|------|---------|
| `beethoven_score_group` | `@pytest.fixture(scope="session")` | Builds the full score group with flow data |
| `_build_dgt1()` | Function | Constructs nested SegmentLine[SegmentLine[DGT]] from OMR CSV |
| `_build_openscore()` | Function | Loads OpenScore via TSVLoader, extracts movement 4 |
| `_unfold_group()` | Function | Unfolds all group members via QB sections |

---

## 8. Bug Fixes Applied During Group Unfolding Work

### 8.1 `quarterbeats` vs `quarterbeats_all_endings` (TSVLoader)

**Root cause:** `TSVLoader._load_notes()` (and other `_load_*` methods)
always used the `quarterbeats` column. This column assigns NaN to measures
inside volta first-endings. The `quarterbeats_all_endings` column assigns
positions to all measures.

**Impact:** For Beethoven Op.18 No.4 iv: timeline length was 868q (wrong)
instead of 878.5q (correct). The 10.5q difference = sum of durations of
3 volta-first-ending measures (MCs 44, 93, 102).

**Fix:** Added `TSVLoader._resolve_quarterbeats()` (~line 281 in tsv.py)
that prefers `quarterbeats_all_endings` when present. Updated all 4 loader
methods (`_load_notes`, `_load_measures`, `_load_annotations`, `_load_controls`).

### 8.2 `SegmentLine.get_slice()` for Nested SegmentLines

**Root cause:** `Timeline.get_slice()` creates the target with
`self.__class__(length=slice_length, ...)`. But `SegmentLine.validate_child`
checks `offset == self.length` for contiguity, so adding the second child
fails because `self.length` is the pre-set slice length, not the cumulative
child length.

**Fix:** Added `SegmentLine.get_slice()` override (~line 1215 in types.py)
that creates with `length=0`, preserves `segment_type`/`inner_segment_type`,
and sets final length after all children are added.
