# Symbolic Score Loaders: Testing & Verification

This directory contains tests and profiling scripts for the `timetoalign.loader.score` module.

---

## Score Parsing Test Matrix Summary

**Ground Truth Target Flows: COMPLETE (7 specimens, 4+ flow modes each)**

### Specimen Completion Status

| # | Specimen               | Status   | Flow Modes | Folded | Unfolded | Notes                             |
|---|------------------------|----------|------------|--------|----------|-----------------------------------|
| 1 | **Rachmaninoff**       | COMPLETE | 3          | 374    | 374      | No flow control (baseline)        |
| 2 | **polyrhythm_only**    | COMPLETE | 3          | 14     | 14       | Line breaks only                  |
| 3 | **c05n05_musete**      | COMPLETE | 4          | 58     | 138      | D.S. al Fine - music21 diverges   |
| 4 | **c11n08_Rondeau**     | COMPLETE | 4          | 60     | 138      | Rondeau form - music21 diverges   |
| 5 | **op18_no4_mov4_flow** | COMPLETE | 3          | 226    | 291      | Repeats + Voltas - ALL agree      |
| 6 | **flow_only**          | COMPLETE | 4          | 15     | 31       | D.S./D.C. + Voltas - ms3 diverges |
| 7 | **WoO71**              | COMPLETE | 3          | 397    | 505      | Complex split bars                |

### Loader/Format Test Matrix

| Specimen           | TSV (gold) | MeasureMap | Music21 XML | Music21 MEI | Partitura XML | Partitura MEI |
|--------------------|:----------:|:----------:|:-----------:|:-----------:|:-------------:|:-------------:|
| Rachmaninoff       |    GOLD    |    PASS    |    PASS     |    PASS     |     PASS      |     PASS      |
| polyrhythm_only    |    GOLD    |    PASS    |    PASS     |    PASS     |     PASS      |     PASS      |
| c05n05_musete      |    GOLD    |    PASS    |  DIVERGE*   |  DIVERGE*   |     PASS      |     PASS      |
| c11n08_Rondeau     |    GOLD    |    PASS    |  DIVERGE*   |  DIVERGE*   |     PASS      |     PASS      |
| op18_no4_mov4_flow |    GOLD    |    PASS    |    PASS     |    PASS     |     PASS      |     PASS      |
| flow_only          |    GOLD    |    PASS    |   FAIL**    |   FAIL**    |     PASS      |     PASS      |
| WoO71              |    GOLD    |    PASS    |    PASS     |    PASS     |     PASS      |     PASS      |

**Legend:**
- **GOLD**: Gold standard (TSV from ms3, authoritative)
- **PASS**: Flow matches a valid flow mode in `.flow.csv`
- **DIVERGE***: Produces different but documented valid flow (e.g., music21 ignores D.S.)
- **FAIL**: Cannot reproduce any valid flow

### Known Parser Deviations

| Parser | Behavior | Limitation | Affected Specimens |
|--------|----------|------------|-------------------|
| **ms3/TSV** | Gold standard | None | - |
| **MeasureMap** | Matches TSV | None | - |
| **Music21** | `expandRepeats()` only | **Ignores D.S./D.C./Fine** | c05n05, c11n08, flow_only |
| **Partitura** | Region model | Infers missing repeats | - |

### Deviation Details

1. **c05n05_musete (music21)**:
   - Expected: 138 unfolded MCs (D.S. al Fine)
   - music21: 116 MCs (ignores D.S., only handles repeat barlines)
   - Difference: 22 = 11 × 2 (two D.S. returns to Segno)

2. **c11n08_Rondeau (music21)**:
   - Expected: 138 unfolded MCs (Rondeau with D.S.)
   - music21: 120 MCs (incorrect D.S. handling)

3. **flow_only (ms3 vs canonical)**:
   - Canonical: 31 MCs (human interpretation)
   - ms3: 30 MCs (ambiguous encoding)
   - music21: FAILS ("badly formed repeats" error)

---

## Architecture Overview

```
                    +---------------------------------------------+
                    |              FlowController                  |
                    |                                              |
   Input Sources:   |   +-------------------------------------+   |
                    |   |      Atomic Segment Builder          |   |
   next[] arrays ---+-->|  - derives segments from next logic  |   |
   (TSV, mm.json)   |   |  - identifies segment boundaries     |   |
                    |   |    from flow control markers         |   |
   partitura -------+-->|  - tracks jump/break coordinates     |   |
   segments         |   +-------------------+-----------------+   |
                    |                       |                      |
                    |                       v                      |
                    |   +-------------------------------------+   |
                    |   |    Playthrough Segment Grouper       |   |
                    |   |  - uses markers + volta attributes   |   |
                    |   |    to execute flow logic             |   |
                    |   |  - groups atomics per FlowMode       |   |
                    |   +-------------------+-----------------+   |
                    |                       |                      |
                    +---------------------------------------------+
                                            |
                                            v
                              +-------------------------+
                              |         Flow            |
                              |                         |
                              |  PlaythroughSegment[]   |
                              |  mode: FlowMode         |
                              |                         |
                              |  Comparison:            |
                              |  - is_equivalent()      |
                              +-------------------------+
```

All score loaders return a `ScoreStore` containing category-specific data:
- `NoteEventData`: Notes, rests, chords
- `MeasureData`: Measure boundaries with flow control
- `ControlEventData`: Dynamics, tempo, signatures
- `AnnotationEventData`: Text annotations

## Loader/Format Test Matrix

| Format | Loader | Input | Test Against |
|--------|--------|-------|--------------|
| MEI | Music21Loader | `.mei` | Valid flow_modes in .flow.csv |
| MusicXML | Music21Loader | `.musicxml` | Valid flow_modes in .flow.csv |
| MusicXML | PartituraLoader | `.musicxml` | Valid flow_modes in .flow.csv |
| TSV | partitura.load_dcml() | `.tsv` | Valid flow_modes in .flow.csv |
| TSV | TSVLoader | `.tsv` | Gold standard |
| mm.json | MeasureMapLoader | `.mm.json` | Valid flow_modes in .flow.csv |

**Note**: TSVLoader output from `*_unfolded.measures.tsv` serves as the gold standard (`default` flow_mode).

## Test File Organization

| File | Purpose | Concern |
|------|---------|---------|
| `test_loaders.py` | Basic unit tests for each loader | Loader functionality |
| `test_cross_validation.py` | Cross-validates loaders on Chopin (notes, pitch) | Data consistency |
| `test_measuremap_loader.py` | MeasureMapLoader-specific tests | MeasureMap parsing |
| `test_flow_control_parity.py` | Flow control extraction (repeat markers, voltas) | Flow control parsing |
| `test_flow_csv_validation.py` | Validates against .flow.csv ground truth | Flow validation |
| `test_flow_parity.py` | MC sequence parity tests | Flow computation |

## Flow Validation Strategy

### Test Logic

Each `.flow.csv` contains **1-5 valid unfoldings** (flow_mode entries). Tests compare loader output against ALL valid flows:

```python
def test_loader_produces_valid_flow(loader, specimen):
    # Get loader output as Flow
    flow = loader.compute_flow()  # Returns Flow with PlaythroughSegments

    # Load valid flows from ground truth
    valid_flows = load_valid_flows_from_csv(specimen)  # 1-5 Flow objects

    # Test passes if output matches ANY valid unfolding
    assert any(flow.is_equivalent(valid) for valid in valid_flows.values()), \
        f"Loader output doesn't match any valid unfolding"
```

### Test Outcomes

| Outcome | Meaning |
|---------|---------|
| **Match default** | Loader output equals the `default` flow_mode |
| **Match alternative** | Loader output equals another valid flow_mode |
| **No match (FAIL)** | Loader output doesn't match any valid unfolding |

### FlowMode Values

**Deterministic modes (must be identical across all loaders):**

| Value | Description | Source | Required in CSV? |
|-------|-------------|--------|------------------|
| `atomic` | True atomic sections from FlowController (= mode=None) | `timetoalign v0.1.0` | **Always** |
| `single` | Single playthrough (last volta only) | `*.measures.tsv` | **Always** |
| `printed` | All bars as printed (no unfolding) | Computed | Never (deterministic) |

**Contingent modes:**

| Value | Description | Source | Required in CSV? |
|-------|-------------|--------|------------------|
| `default` | Most complete flow (all repeats) | `*_unfolded.measures.tsv` | **Always** |
| `partitura_maximal` | partitura's full unfolding | MusicXML/MEI | Only if diverges from `default` |
| `music21` | music21's expandRepeats() | MusicXML/MEI | Only if diverges from `default` |
| `partitura_minimal` | partitura's atomic segments | MusicXML/MEI | Only if diverges from `atomic` (rare) |

### Implicit Flow Convention

**Only list divergent flows.** The `.flow.csv` files are self-documenting:

- **If `music21` is absent** → assumed to produce `default`
- **If `partitura_maximal` is absent** → assumed to produce `default`
- **If `partitura_minimal` is absent** → assumed to produce `atomic`

This means: if you see `music21`, `partitura_maximal`, or `partitura_minimal` entries in a `.flow.csv`, there is a **known discrepancy** that requires investigation.

## Cross-Validation Tests

We load *Chopin Op. 10 No. 3* using three loaders and verify consistency:

| Loader | Source | Notes | Measures | Controls |
|--------|--------|-------|----------|----------|
| TSVLoader | TSV (ms3) | 498 | - | - |
| PartituraLoader | MusicXML | 498 | 22 | 27 |
| Music21Loader | MusicXML | 498+12 rests | 22 | 11 |

### Validation Checks

1. **Note Count Consistency**: All loaders return 498 Notes (rests tracked separately)
2. **Temporal Schema**: `quarterbeats` stored as Fraction structs `{num, den}`
3. **Pitch Schema**: `midi_pitch` and `spelled_pitch` fully populated
4. **Measure Context**: `mc`, `mn`, `mc_onset` correctly computed

## MeasureMapLoader Tests

### Test Categories

| Class | Description | Tests |
|-------|-------------|-------|
| `TestMeasureMapLoaderBasic` | Basic loader functionality | Import, init, load specimen |
| `TestMeasureMapExpansion` | Compression/expansion logic | Minimal, anacrusis, repeats |
| `TestMeasureMapValidation` | Validation rules | MC unique, qstamp monotonic, next valid |
| `TestMeasureMapTraversal` | Traversal computation | Simple, repeat, unfolded count |
| `TestMeasureMapCrossValidation` | Cross-loader validation | Count match, MC match, flow control |
| `TestMeasureDataSchema` | Schema validation | Flow control fields, identity fields |
| `TestFlowControlSpecimen` | Complex flow control | Load flow_control specimen |

### Gold Standard Specimens

| File | Location | Description | Count |
|------|----------|-------------|-------|
| `WoO71.measures.mm.json` | `beethoven_woo71/` | Folded MeasureMap | 397 MCs |
| `WoO71.measures.tsv` | `beethoven_woo71/` | Folded TSV (ms3) | 397 rows |
| `WoO71_unfolded.measures.tsv` | `beethoven_woo71/` | Unfolded traversal | 505 rows |
| `*.mm.json` | `flow_control/flow_only/` | Complex flow control | Variable |

## Flow Control Parity Tests

Cross-validation tests ensuring all score loaders extract flow control information consistently.

### Loader Model Classification

| Model | Loaders | Behavior |
|-------|---------|----------|
| **Marker** | TSV, MeasureMap, Music21 | Reports barline markers as individual events |
| **Region** | Partitura | Infers missing start/end to create complete regions |

**Marker-based loaders** produce identical counts and are validated together.
**Partitura** is tested separately with adjusted expectations.

### Known Discrepancy: Partitura Region Model

Partitura models repeats as **regions** (start/end boundary pairs) rather than **markers**.
When encountering an orphan repeat end without a start, Partitura infers a start point.

This is **expected behavior** and documented in test docstrings.

## Running Tests

```bash
# Run all score loader tests
pytest tests/loader/score/ -v

# Run specific test file
pytest tests/loader/score/test_flow_csv_validation.py -v

# Run with coverage
pytest tests/loader/score/ --cov=timetoalign.loader.score

# Run diagnostic output
pytest tests/loader/score/test_flow_parity.py::TestDiagnosticOutput -v -s
```

## Music21 MEI Loader: Sparse Skeleton Expansion

### Background

MuseScore 4's MEI export produces a **sparse skeleton representation** for scores that contain multi-measure rests. Rather than writing every measure explicitly, MuseScore collapses runs of empty measures into a compact form: it writes only the structurally significant boundary measures (first/last of each repeat section, volta measures, etc.) and marks them with `metcon="false"` to indicate that their content is omitted. Intermediate measures are implied by **gaps in the `@n` attribute**.

For example, a section of measures 1–9 where measures 3–8 are empty will appear in the MEI as:

```xml
<measure n="2" metcon="false"> ... </measure>
<measure n="9" right="rptend" metcon="false"> ... </measure>
```

The six omitted measures (3–8) are implied but physically absent from the file.

### Problem 1: Sparse Skeleton — Incorrect MC Count

**Specimen:** `op18_no4_mov4_flow` (226 folded measures)

**File:** `tests/data/score/beethoven_op18-4iv_multimodal/op18_no4_mov4_flow/op18_no4_mov4_flow.mei`

The MEI file is only 13 KB, while the equivalent MusicXML is 55 KB. The MEI contains only **27 `<measure>` XML elements** with non-sequential `@n` values (1, 2, 9, 10, 11, 18, 19, 20, 27, 28, 29, 44, 45, 46, 77, 78, 79, 84, 85, 86, 93, 94, 95, 102, 103, 104, 226), implying 205 intermediate measures are omitted.

music21 parses this file and obtains only **21 `Measure` objects** (not even 27 — some share the same offset and are collapsed internally). The `Music21Loader` was assigning sequential `i + 1` as the MC value, yielding only 21 unique MCs instead of 226.

**Gaps in the sparse skeleton:**

| Between measures | Gap (omitted MCs) |
|-----------------|-------------------|
| n=2 → n=9       | 3–8 (6 measures)  |
| n=11 → n=18     | 12–17 (6 measures) |
| n=20 → n=27     | 21–26 (6 measures) |
| n=29 → n=46     | 30–45 (16 measures) |
| n=46 → n=77     | 47–76 (30 measures) |
| n=79 → n=84     | 80–83 (4 measures) |
| n=86 → n=95     | 87–94 (8 measures) |
| n=95 → n=104    | 96–103 (8 measures) |
| n=104 → n=226   | 105–225 (121 measures) |

**Fix:** `Music21Loader._expand_mei_skeleton()` detects sparse MEI files by checking for two conditions:
1. All measure numbers are **unique** (no duplicates from repeated sections in a full-score MEI).
2. The **maximum measure number exceeds the list length**, indicating gaps.

When both conditions hold, it fills the gaps with synthetic proxy measures — lightweight objects that expose the same attributes as a `music21.stream.Measure` (number, offset, duration, barlines) but contain no notes or flow-control markers. This expands the 21-measure list to 226.

The guard conditions prevent false positives: full-score MEI files (like those for `c05n05_musete` or `polyrhythm_only`) have duplicate `@n` values (the same measure number appears in each repeated pass), which immediately disqualifies expansion.

### Problem 2: Missing Volta Information — Incorrect Flow

**Specimen:** `op18_no4_mov4_flow`

The six volta measures (44, 45, 93, 94, 102, 103) are wrapped in `<ending>` elements in the MEI:

```xml
<ending label="1" type="mscore-ending-1">
  <measure n="44" right="rptend" metcon="false"> ... </measure>
</ending>
<ending label="2" type="mscore-ending-2" lendsym="none">
  <measure n="45" metcon="false"> ... </measure>
</ending>
```

**music21's MEI parser does not translate `<ending>` elements into `RepeatBracket` spanners.** Consequences:
1. The six volta measures are **dropped entirely** from the parsed measure list (not present in music21's `part.getElementsByClass(Measure)`).
2. No `RepeatBracket` spanners are created, so `volta_by_offset` remains empty.
3. The `_compute_next_fields` algorithm sees no volta markers and generates a single-pass flow with 5 sections (260 unfolded measures) instead of the correct 11 sections (291 unfolded measures).

Without volta information, the FlowController cannot construct the branching at measure 43 (volta 1 → MC 44, volta 2 → MC 45), measure 92 (volta 1 → MC 93, volta 2 → MC 94), or measure 101 (volta 1 → MC 102, volta 2 → MC 103).

**Fix:** `Music21Loader._parse_mei_measure_info()` parses the raw MEI XML directly using `xml.etree.ElementTree`. It walks every `<measure>` element, tracking whether it is inside an `<ending>` element, and returns a mapping from measure number to `{volta, start_repeat, end_repeat}`. This correctly recovers:
- `volta=1` for measures 44, 93, 102
- `volta=2` for measures 45, 94, 103
- `end_repeat=True` for measures 44, 93, 102
- `start_repeat=True` for measures 10, 19, 28, 78, 85, 95

When loading `.mei` files, `_load_source` uses this pre-parsed data instead of music21's barline/RepeatBracket APIs.

### Why MuseScore Generates Sparse MEI

The `.mscz` source file for `op18_no4_mov4_flow` contains only 23 internal `<Measure>` elements — MuseScore itself stores multi-measure rests in a compressed form in its native format. When exporting to MEI, this compression is preserved. When exporting to MusicXML, all 226 measures are expanded explicitly. This explains the size difference (13 KB MEI vs 55 KB MusicXML).

The MEI skeleton format is **not a bug** — it is valid MEI encoding. The fix is in the loader, not the test data.

### Affected Tests

| Test | Specimen | Pre-fix | Post-fix |
|------|----------|---------|---------|
| `TestMusic21LoaderMEI::test_music21_mei_folded_count[op18_no4_mov4_flow]` | op18_no4_mov4_flow | FAIL (21 ≠ 226) | PASS |
| `TestMusic21LoaderMEI::test_music21_mei_matches_musicxml[op18_no4_mov4_flow]` | op18_no4_mov4_flow | FAIL (5 sections ≠ 11) | PASS |

### Files Modified

- `timetoalign/loader/score/music21.py`:
  - Added `_parse_mei_measure_info(source)` — raw XML parser for MEI flow-control metadata
  - Added `_expand_mei_skeleton(measure_list)` — sparse skeleton expansion with duplicate-guard
  - Modified `_load_source()` — uses MEI-specific data instead of music21 API when `source.suffix == ".mei"`

---

### Large File Timeout Handling

Tests automatically skip MusicXML/MEI files larger than **500KB** to avoid timeouts:

- `PartituraLoader` can take **90+ seconds** on large (2MB+) MusicXML files due to Fraction processing
- Tests use `MAX_MUSICXML_SIZE_BYTES = 500_000` constant
- Skip message includes file size and explains the reason

**Affected tests:**
- `test_flow_control_parity.py`: `partitura_measures`, `music21_measures` fixtures
- `test_score_parsing_matrix.py`: `test_music21_musicxml_*`, `test_partitura_musicxml_*`

**To adjust the threshold:**
```python
# In test_flow_control_parity.py or test_score_parsing_matrix.py
MAX_MUSICXML_SIZE_BYTES = 1_000_000  # Increase to 1MB
```

## Profiling

Benchmarks on *Chopin Op. 10 No. 3*:

| Loader | Format | Time (avg) | Notes |
|--------|--------|------------|-------|
| TSVLoader | TSV (ms3) | ~150 ms | Fastest. Direct load. |
| Music21Loader | MusicXML | ~400 ms | Medium. Object overhead. |
| PartituraLoader | MusicXML | ~700 ms | Slowest. Detailed analysis. |

```bash
python tests/loader/score/profile.py
```

## Validation Policy

Per the **ZERO TOLERANCE VALIDATION POLICY** (AGENTS.md):

1. **EXACT COUNTS REQUIRED**: All assertions use exact expected values
2. **NO TOLERANCE WITHOUT ROOT CAUSE**: Any tolerance must be documented
3. **MISMATCHES MUST BE INVESTIGATED**: "Close enough" is never acceptable
4. **GOLD STANDARD IS AUTHORITATIVE**: TSV from ms3 defines correct values
5. **LOADER PARITY IS REQUIRED**: Same input must produce equivalent outputs

## Test Data

Located in `tests/data/`:

- `midi/score/`: Chopin Op. 10 No. 3 (MusicXML + TSV)
- `score/`: All specimens (see `.agent/skills/co-create-groundtruth/references/specimens.md`)
- `target_flows/`: Ground truth `.flow.csv` files

---

## TOP-MOST GOAL

**FlowController must reproduce ALL target flows in `.flow.csv` from ANY loader/format combination.**

**The major goal: PRODUCE ALL TARGET FLOWS CORRECTLY.**

### Test Logic

```python
def test_flowcontroller_reproduces_target_flows(specimen, loader, format):
    # 1. Load target flows from CSV, associating with FlowMode
    target_flows = load_valid_flows(specimen.flow_csv_path)  # {FlowMode: Flow}

    # 2. Load score with loader/format, build FlowController
    controller = FlowController.from_loader(loader.load(specimen.source_file))

    # 3. Test if FlowController can reproduce each target flow
    for mode, target in target_flows.items():
        computed = controller.compute_flow(mode=mode)  # mode=None = "default"
        if computed.is_equivalent(target):
            # SUCCESS: FlowController reproduced this target flow!
            pass
        else:
            # FAILURE: Document what information was lost
            pass
```

### Test Outcomes

| Outcome | Meaning | Action |
|---------|---------|--------|
| **Reproduces ALL** | FlowController computes default + all queried FlowModes | **HUGE WIN** - the goal |
| **Reproduces SOME** | FlowController computes a few FlowModes correctly | **WIN** - document which ones |
| **Cannot reproduce ANY** | Information lost in loader/format | **DOCUMENT** what was lost and why |

### Parser Behavior Summary

| Parser | Behavior | Recognizes | Information Loss |
|--------|----------|------------|------------------|
| **ms3/TSV** | Follows explicit `next[]` arrays | All flow control | None (gold standard) |
| **partitura** | Derives from structural markers | Repeat barlines, some D.S./D.C. | May lose conditional jumps |
| **music21** | `expandRepeats()` only | Repeat barlines ONLY | **Loses D.S./D.C./Fine entirely** |

### Why Multiple Target Flows?

Different parsers preserve different information. The `.flow.csv` convention:
- **Always include**: `partitura_minimal`, `default`, `single` (the three required modes)
- **Only include `music21` or `partitura_maximal` if they DIVERGE from `default`**
- This makes discrepancies immediately visible: presence of `music21` = known issue

**Example**: c05n05_musete has `music21` listed because music21 ignores D.S./Fine (116 vs 138 measures).
**Example**: op18_no4_mov4_flow does NOT list `music21` because it matches `default` (no D.S./D.C./Fine).

---

## Specimen Documentation

### Split Measure Notation

For human documentation, we use **lowercase Roman numerals** to denote split measures:

| Notation | Meaning |
|----------|---------|
| `4i` | First part of MN 4 |
| `4ii` | Second part of MN 4 |
| `14i` | First part of MN 14 |
| `14ii` | Second part of MN 14 |

Example: MN 4 is split into MC 5 (4i) and MC 6 (4ii).

---

### c05n05_musete (Couperin - Les Goûts-réunis, 5e Concert, V. Musete)

**Musicological Context:**
A **Musete** is a Baroque pastoral dance form named after the musette (bagpipe). The structure follows the typical **Rondeau-with-Couplets** pattern common in French Baroque suites.

**Structural Analysis:**

| Section | MN Range | MC Range | MC Interval | Description |
|---------|----------|----------|-------------|-------------|
| A (Intro) | 0--4i | 1--5 | [1, 6) | Anacrusis to Segno marker |
| B (Refrain) | 4ii--14i | 6--16 | [6, 17) | Segno at start, Fine at end |
| C (1er Couplet) | 14ii--28i | 17--31 | [17, 32) | First couplet with repeat |
| D (2e Couplet) | 28ii--54 | 32--58 | [32, 59) | Second couplet with repeat |

**Split Measures:**
- MN 0: MC 1 (anacrusis)
- MN 4: MC 5 (4i), MC 6 (4ii) - Segno at 4ii
- MN 14: MC 16 (14i), MC 17 (14ii) - Fine at 14i, 1er Couplet starts at 14ii
- MN 28: MC 31 (28i), MC 32 (28ii) - 2e Couplet starts at 28ii

**Flow Control at MC 16:**
`next = [1, 17, 32, -1]` with Fine marker - conditional branching based on visit count.

**Parser Outputs:**

| Parser | Sections | Measures | Behavior |
|--------|----------|----------|----------|
| **ms3 (default)** | 8 | 138 | Full D.S. al Segno/Fine execution |
| **music21** | 6 | 116 | Repeat barlines only, ignores D.S./Fine |
| **partitura_minimal** | 4 | 58 | Atomic segments (no unfolding) |

**Why music21 produces 116 measures (not 138):**

music21's `expandRepeats()` processes repeat barlines (`:||:`) but does NOT execute D.S. al Segno/Fine instructions. It sees:
- Segno marker at M4 (but ignores it for navigation)
- Fine marker at M14 (but ignores it for navigation)
- Repeat barlines (processes these)

Missing from music21:
- D.S. al Segno after 1er Couplet (would add MC 6-16 = 11 measures)
- D.S. al Fine after 2e Couplet (would add MC 6-16 = 11 measures)

138 - 116 = 22 = 11 × 2 ✓

**Performance Flow (ms3 gold standard):**

| Pass | MC Range | Section | Notes |
|------|----------|---------|-------|
| 1 | 1-16 | Intro + Refrain | First time |
| 2 | 1-16 | Intro + Refrain | Repeat |
| 3 | 17-31 | 1er Couplet | First time |
| 4 | 17-31 | 1er Couplet | Repeat |
| 5 | 6-16 | Refrain (D.S.) | After Couplet 1 |
| 6 | 32-58 | 2e Couplet | First time |
| 7 | 32-58 | 2e Couplet | Repeat |
| 8 | 6-16 | Refrain (D.S.) | Final, to Fine |

---

### c11n08_Rondeau (Couperin - Les Goûts-réunis, 11e Concert, VIII. Rondeau)

**Musicological Context:**
A **Rondeau** in French Baroque style with the form A-A-B-B-A-C-C-A-D-D where A is the refrain and B, C, D are couplets.

**Parser Outputs:**

| Parser | Sections | Measures | Behavior |
|--------|----------|----------|----------|
| **ms3 (default)** | 10 | 138 | Full Rondeau form execution |
| **music21** | 5 | 120 | Incorrect D.S. handling |
| **partitura_minimal** | 4 | 60 | Atomic segments |

---

### op18_no4_mov4_flow (Beethoven Op. 18 No. 4, Mov. 4 - Allegro)

**Musicological Context:**
The fourth movement of Beethoven's String Quartet Op. 18 No. 4 in C minor is a lively **Rondo** marked Allegro. The movement features extensive use of repeat barlines and first/second volta endings, but **no D.S./D.C./Fine markers**.

**Source Data:**

| File | Rows | Description |
|------|------|-------------|
| `op18_no4_mov4_flow.measures.tsv` | 227 MCs | Folded (printed) score |
| `op18_no4_mov4_flow_unfolded.measures.tsv` | 291 | Gold standard unfolding |

**Structural Analysis (13 Atomic Segments):**

| Segment | MC Range | Type | Description |
|---------|----------|------|-------------|
| **A** | [1, 10) | leap_end | Opening theme, repeat back to MC 1 |
| **B** | [10, 19) | leap_end | Second phrase, repeat back to MC 10 |
| **C** | [19, 28) | leap_end | Third phrase, repeat back to MC 19 |
| **D** | [28, 44) | leap_end | Development, branches to voltas |
| **D1** | [44, 45) | volta 1 | Volta 1 ending, jumps back to MC 28 |
| **E** | [45, 78) | default | Volta 2 + continuation |
| **F** | [78, 85) | leap_end | Trio opening, repeat back to MC 78 |
| **G** | [85, 93) | leap_end | Trio middle, branches to voltas |
| **G1** | [93, 94) | volta 1 | Volta 1 ending, jumps back to MC 85 |
| **H** | [94, 95) | default | Volta 2 bridge |
| **I** | [95, 102) | leap_end | Trio closing, branches to voltas |
| **I1** | [102, 103) | volta 1 | Volta 1 ending, jumps back to MC 95 |
| **J** | [103, 227) | terminal | Coda to end |

**Flow Control (from `next` column):**
- MC 9: `next = [1, 10]` - repeat barline
- MC 18: `next = [10, 19]` - repeat barline
- MC 27: `next = [19, 28]` - repeat barline
- MC 43: `next = [44, 45]` - volta branch (D1 vs E)
- MC 84: `next = [78, 85]` - repeat barline
- MC 92: `next = [93, 94]` - volta branch (G1 vs H)
- MC 101: `next = [102, 103]` - volta branch (I1 vs J)

**Volta 1 Measures (empty `quarterbeats` in folded TSV):**
- MC 44 (D1), MC 93 (G1), MC 102 (I1)

**Parser Outputs:**

| Parser | FlowMode | Sections | Measures | In CSV? | Notes |
|--------|----------|----------|----------|---------|-------|
| **ms3** | `default` | 16 | 291 | Yes | Gold standard |
| **partitura** | `partitura_minimal` | 13 | 227 | Yes | Atomic segments |
| **ms3 folded** | `single` | 10 | 223 | Yes | Single pass |
| **partitura** | `partitura_maximal` | 16 | 291 | **No** | Matches `default` |
| **music21** | `music21` | 16 | 291 | **No** | Matches `default` |

**Why `music21` and `partitura_maximal` are NOT in the CSV:**
This piece uses **only repeat barlines and voltas** - no D.S., D.C., Segno, Coda, or Fine markers. All three parsers handle these identically, so they match `default`. Per the implicit flow convention, we only list flows that **diverge** from `default`.

**Performance Flow (default, 16 sections):**

| Pass | MC Range | Section | Notes |
|------|----------|---------|-------|
| 1 | 1-9 | A | First time |
| 2 | 1-9 | A | Repeat |
| 3 | 10-18 | B | First time |
| 4 | 10-18 | B | Repeat |
| 5 | 19-27 | C | First time |
| 6 | 19-27 | C | Repeat |
| 7 | 28-44 | D+D1 | First time with volta 1 |
| 8 | 28-43 | D | Second time (to volta 2) |
| 9 | 45-77 | E | Volta 2 + continuation |
| 10 | 78-84 | F | First time |
| 11 | 78-84 | F | Repeat |
| 12 | 85-93 | G+G1 | First time with volta 1 |
| 13 | 85-92 | G | Second time (to volta 2) |
| 14 | 94-102 | H+I+I1 | Volta 2 bridge + I with volta 1 |
| 15 | 95-101 | I | Second time (to volta 2) |
| 16 | 103-226 | J | Coda to end |

**Single Flow (10 sections, 223 measures):**
Derived from folded TSV by excluding MCs with empty `quarterbeats` (volta 1 endings):
A → B → C → D → E → F → G → H → I → J

---

### flow_only (Out of the Flow Experience - Flow Control Edge Cases)

**Musicological Context:**
A synthetic edge-case specimen specifically designed to test complex flow control scenarios that most parsers cannot handle correctly. It combines:
- Repeats with missing start barlines (implied repeats)
- Nested repeats (a repeated bar within a repeated section)
- D.S. al Coda with multiple visits
- D.C. al Fine with "senza rep" (no repeat on return)
- Three volta endings

**Critical Encoding Issue: MC 8's Implied Repeat**

MC 8 has an end-repeat barline but no preceding start-repeat. In conventional notation, humans recognize the end-barline at MC 7 (which is also a section boundary) as the implicit start of the repeating section. However, in encoded scores:
- This would normally require a `section_break` marker
- Most parsers (music21, partitura) fail to recognize implied repeats
- MS3's TSV encodes `next = [9]` instead of canonical `next = [8, 9]`

**Structural Analysis:**

| Section | MC Range | Description |
|---------|----------|-------------|
| A | [1, 4) | Opening, repeated via D.C. |
| B | [4, 8) | Volta region (1, 2, 3 endings) |
| C | [8, 13) | Repeat section with D.S. al Coda |
| D | [13, 16) | Coda section with volta 1/2 |

**Parser Outputs:**

| Parser | FlowMode | Sections | MC Visits | Notes |
|--------|----------|----------|-----------|-------|
| **Canonical** | `default` | 15 | 31 | Intended musicological flow |
| **ms3** | `ms3` | 16 | 30 | Missing MC 8 self-repeat, different nested structure |
| **partitura** | `partitura_minimal` | 4 | N/A | Atomic segments only, ignores D.S./Coda/Fine |
| **music21** | N/A | FAILS | N/A | "badly formed repeats" error |

**Why MS3 Differs from Canonical (5 discrepancies):**

| MC | TSV `next[]` | Canonical `next[]` | Issue |
|----|--------------|-------------------|-------|
| 8 | `[9]` | `[8, 9]` | Missing implied self-repeat |
| 9 | `[9, 10, 13]` | `[10, 10, 13]` | First element wrong |
| 10 | `[10, 11]` | `[10, 11, 10, 11]` | Missing nested iterations |
| 11 | `[11, 12]` | `[9, 12]` | Should jump to 9 (outer repeat) |
| 14 | `[12]` | `[13]` | Should stay in coda section |

**Canonical Flow (31 MC visits):**
```
1, 2, 3, 1, 2, 3, 4, 5, 4, 6, 8, 8, 9, 10, 10, 11, 9, 10, 10, 11, 12, 9, 13, 14, 13, 15, 1, 2, 3, 4, 7
```

**MS3 Flow (30 MC visits):**
```
1, 2, 3, 1, 2, 3, 4, 5, 4, 6, 8, 9, 9, 10, 10, 11, 11, 12, 9, 13, 14, 12, 9, 13, 15, 1, 2, 3, 4, 7
```

---

### Additional Specimens (Pending Audit)

The following specimens require collaborative ground truth creation:

1. **WoO71** - Beethoven WoO71 12 Variations (Complex split bars)

See `.agent/skills/co-create-groundtruth/` for the audit workflow.
