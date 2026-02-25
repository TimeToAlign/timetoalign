# Vienna 4×22 Dataset: Chopin Op. 10 No. 3

## Overview

This directory contains the **Vienna 4×22 Subset** for Chopin's Étude in E major, Op. 10 No. 3.
The dataset pairs a single score (MusicXML) with 22 human piano performances (MIDI + `.match`
alignment files). It is the canonical specimen for testing the `MatchfileLoader` and the
"many performances against one score" alignment workflow.

The dataset originates from the **Vienna International Piano Competition (VIPC)** dataset
published by Sebastian Flossmann, Maarten Grachten, and Gerhard Widmer. The `.match` file
format and tooling were developed alongside the [partitura](https://github.com/CPJKU/partitura)
library by the CP-JKU Linz group.

---

## File Inventory

| File pattern | Count | Description |
|---|---|---|
| `Chopin_op10_no3.musicxml` | 1 | Score in MusicXML format |
| `Chopin_op10_no3.pdf` / `.png` | 1+1 | Rendered score image |
| `Chopin_op10_no3_p01.match` … `_p22.match` | 22 | Alignment files (Vienna Match v1.0.0) |
| `Chopin_op10_no3_p01.mid` … `_p22.mid` | 22 | Performance MIDI files |
| `ms3/` | — | DCML ground-truth TSV, MeasureMap JSON, MuseScore source |

### ms3/ sub-directory

| File | Description |
|---|---|
| `chopin_op10_no3.notes.tsv` | Note-level annotation (ms3 DCML schema) |
| `chopin_op10_no3.measures.tsv` | Measure-level annotation with flow control |
| `chopin_op10_no3.chords.tsv` | Chord-level annotation |
| `chopin_op10_no3.mm.json` | MeasureMap JSON |
| `chopin_op10_no3.mscx` | MuseScore 3 source |
| `metadata.tsv` | Dataset metadata |

---

## Match File Format (Vienna Match v1.0.0)

Each `.match` file encodes the alignment between one performance and the shared score.
It is a **Prolog-style structured text format** with three record types:

### Header Records

```prolog
info(matchFileVersion,1.0.0).
info(piece,Chopin_op10_no3).
info(scoreFileName,Chopin_op10_no3.musicxml).
info(midiFileName,Chopin_op10_no3_p01.mid).
info(composer,Frèdéryk Chopin).
info(performer,Pianist 01).
info(midiClockUnits,480).          % ticks per quarter note
info(midiClockRate,500000).        % microseconds per quarter (default 120 BPM)
scoreprop(keySignature,E,0:1,0,-0.5000).
scoreprop(timeSignature,2/4,0:1,0,-0.5000).
```

### Alignment Records: `snote(...)-note(...)`

Each matched note pair:

```
snote(n1,[B,n],3,0:1,0,1/8,-0.5000,0.0000,[v1,staff1])
      └─ score note id
              └─ [pitch class, accidental]  (n=natural, #=sharp, b=flat)
                       └─ octave
                                └─ measure:beat  (e.g. 0:1 = anacrusis)
                                     └─ beat offset (fraction)
                                          └─ nominal duration (fraction of a quarter)
                                                  └─ score onset (quarter beats, global)
                                                          └─ score offset (quarter beats, global)
                                                                  └─ [voice, staff, articulations]
  -note(n0,59,0,261,44,0,0)
         └─ performance note id
              └─ MIDI pitch
                    └─ MIDI onset (ticks from start)
                         └─ MIDI offset (ticks)
                              └─ velocity (0–127)
                                   └─ channel
                                       └─ track
```

### Deletion Records: `snote(...)-deletion`

A score note with **no matching performance note** (pianist omitted the note):

```
snote(n356,[A,#],4,16:2,1/16,1/16,31.2500,31.5000,[v2,staff1])-deletion.
```

These are **NOMATCH sentinels** in TTA terminology. They appear when the alignment
algorithm explicitly asserts that a score event has no performance counterpart.

### Pedal/Control Records

Lines beginning with `sustain(tick,value)` and `soft(tick,value)` encode continuous pedal
data. These are NOT note alignments and must be filtered out during parsing.

```
sustain(80529,28).
soft(82986,0).
```

### Grace Note Encoding

Grace notes are indicated by a duration of `0` in the snote:

```
snote(n140,[A,#],4,7:2,1/8,0,13.5000,13.5000,[v1,staff1,grace])-note(n140,70,26367,26619,63,0,0).
```

The `duration=0` corresponds to `gracenote` tag in the NoteEventData schema. Score
onset and offset are identical, giving a zero-duration interval.

---

## Exact Counts (Gold Standard)

These counts are authoritative. All tests MUST use exact values per the Zero Tolerance
Validation Policy (see `AGENTS.md §3.6`).

### Score (from MusicXML via PartituraLoader / from ms3 TSV)

| Metric | Value | Source |
|---|---|---|
| Notes (non-rest, non-grace) | 498 | `test_loaders.py::test_chopin_note_count` |
| Rests | 0 | confirmed via PartituraLoader |
| Grace notes | 12 | score notes with duration=0 |
| Measures | 22 | confirmed via PartituraLoader |
| Quarter-beat duration (total) | varies | see notes below |
| Divisions per quarter (XML) | 480 | from `midiClockUnits` |

> **Note:** The 498 note count is cross-validated across TSVLoader, PartituraLoader,
> and Music21Loader in `tests/loader/score/test_cross_validation.py`.

### Per-Match File (Performance)

Each `.match` file encodes alignment of the same 454 score notes (snotes). The remaining
44 score notes (the 12 grace notes + 32 additional notes not in this subset) are
present but behave consistently. Each file contains:

| Metric | Value |
|---|---|
| Total snote records | 454 per file |
| Deletion records (p01) | 3 |
| Pedal (sustain/soft) records (p01) | 3,422 |
| Total lines (p01) | 3,886 |

> **Exact per-file snote counts** (all 22 files have 454 snote records — identical score
> coverage). Any future test asserting this count MUST use `454`, not an approximation.

> **Deletion counts vary by performer.** The `3` deletions in `p01` is specific to that
> performer. Tests validating deletion counts MUST obtain expected values empirically per
> file and document them here.

### Coordinate Domains

| Domain | Unit | Stored As | Notes |
|---|---|---|---|
| Score (internal) | Quarter beats (raw) | `start`, `end` on score TL | May include negative values for anacrusis notes |
| Score (normalised view) | Quarter beats (shifted) | via `raw_to_normalised` ShiftMap | Offset = −min(raw onsets); computed dynamically |
| Score (divisions view) | MIDI divisions (480/qn) | via `quarters_to_divs` ScalarMap | Forward: quarters×480; inverse: ÷480 |
| Score position | Measure:beat string | `measure_beat` field | Not a coordinate; metadata only |
| Performance (internal) | MIDI ticks | `start`, `end` on perf TL | Always non-negative |
| Performance (seconds view) | Seconds | via `ticks_to_seconds` ScalarMap | Factor = midiClockRate/(midiClockUnits×10⁶) |

The C-Maps attached to each timeline convert *from* that timeline's primary unit *to*
the named alternative unit. To go in the reverse direction, call `.inverse()` on the map.

---

## Validation Strategy

### What We Test

Testing this specimen exercises the following TTA concepts and components:

1. **Match file parsing** (`MatchfileLoader`): Prolog grammar, header extraction, deletion handling, pedal line filtering, grace note detection.
2. **Score timeline construction**: raw quarter-beat coordinates; `raw_to_normalised` ShiftMap (offset computed dynamically, never hardcoded); `quarters_to_divs` ScalarMap.
3. **Performance timeline construction**: tick coordinates; `ticks_to_seconds` ScalarMap derived from `midiClockRate`/`midiClockUnits`.
4. **MatchClaim generation**: One `MatchClaim.from_events()` per `snote-note` line (using raw score coordinates); one `MatchClaim.nomatch()` per `snote-deletion` line.
5. **MatchMetadata provenance**: `agent="vienna_match_v1.0.0"`, `decision_criteria="automatic"`.
6. **External timeline binding (Pattern 1)**: `loader.load(*files)` then `loader.create_alignment_bundle(score_timeline=pre_loaded_tl)`; events looked up by ID, added if absent, coordinate-verified if present.
7. **Loader-managed shared score (Pattern 2)**: `loader.load(*files)` then `loader.create_alignment_bundle()` (no file arguments); the loader automatically builds and caches the shared score TL during `load()`.
8. **AlignmentBundle construction**: Adding 22 performance timelines with cross-group MatchClaims.

### Test Classes (PLANNED — `tests/loader/test_matchfile_loader.py` does not yet exist)

#### `TestMatchfileFormat`
Unit tests for the raw parser, independent of TTA objects.

| Test | Assertion | Exact Value |
|---|---|---|
| `test_header_parsing` | Header fields parsed correctly | version=1.0.0, midiClockUnits=480 |
| `test_snote_count` | All 454 snote records parsed | 454 |
| `test_deletion_count_p01` | Deletions in p01 | 3 |
| `test_pedal_lines_excluded` | Pedal lines not in note output | 0 sustain/soft in notes |
| `test_grace_note_detection` | Grace notes identified | duration=0 and `grace` tag in voice list |

#### `TestMatchfileLoaderSingle` (single-file load)
Tests `MatchfileLoader.load("Chopin_op10_no3_p01.match")`.

| Test | Assertion | Exact Value |
|---|---|---|
| `test_score_timeline_quarters` | Score TL uses `TimeUnit.quarters` by default | — |
| `test_score_timeline_note_count` | Notes on score TL | 454 (matched subset) |
| `test_score_cmap_normalisation` | `raw_to_normalised` ShiftMap attached; offset computed from file | `ShiftMap.offset == -min(raw_onsets)` |
| `test_score_cmap_normalisation_value` | Normalised onset of first note = 0.0 | `score_tl.cmap(-0.5) == 0.0` |
| `test_score_cmap_divs` | `quarters_to_divs` ScalarMap attached; forward direction quarters → divs | `cmap(1.0) == 480` |
| `test_perf_timeline_ticks` | Performance TL uses `TimeUnit.ticks` | — |
| `test_perf_timeline_note_count` | Notes on performance TL | 451 (454 snotes − 3 deletions) |
| `test_perf_cmap_seconds` | `ticks_to_seconds` ScalarMap attached; value from `midiClockRate`/`midiClockUnits` | `cmap(480) ≈ 0.5` at 120 BPM |
| `test_match_claims_count` | Total MatchClaims = snote count | 454 |
| `test_nomatch_claims_count` | Non-synchronous (deletion) claims | 3 |
| `test_match_metadata` | Provenance on every claim | `agent="vienna_match_v1.0.0"` |
| `test_match_claim_raw_coordinates` | First claim uses raw (negative) score coord | `start_anchor.coordinate_a == -0.5` |

#### `TestMatchfileLoaderCreateBundle` (`load()` then `create_alignment_bundle()`)
Tests the standard two-phase pattern: `loader.load(file)` then `loader.create_alignment_bundle()`.

| Test | Assertion |
|---|---|
| `test_bundle_returns_result` | Returns `AlignmentBundleResult` |
| `test_bundle_score_id` | Score TL `id` matches caller-supplied uid |
| `test_bundle_perf_id` | Performance TL `id` is derived from filename |
| `test_bundle_claim_connect_both` | Every claim `.connects_both(score_id, perf_id)` |

#### `TestMatchfileLoaderExternalScore` (Pattern 1 — user-supplied score TL)
Tests `loader.load(*files)` then `create_alignment_bundle(score_timeline=pre_loaded_score_tl)`.

| Test | Assertion |
|---|---|
| `test_bind_external_score_timeline` | `result.source_timeline` is the same object that was passed in |
| `test_claims_use_external_tl_uid` | All claims use the external TL's uid as `timeline_a_id` |
| `test_event_id_lookup_succeeds` | Each snote ID found on the external TL; coordinate verified |
| `test_event_added_if_absent` | An event present in `.match` but absent from external TL is added |
| `test_coord_mismatch_raises` | If same ID has different coordinate, `ValueError` is raised |

#### `TestMatchfileLoaderSharedScore` (Pattern 2 — loader-managed)
Tests `loader.load(*all_22_files)` then `create_alignment_bundle()` without `source_timeline=`.

| Test | Assertion |
|---|---|
| `test_22_performances_same_score_tl` | All 22 `result.source_timeline` are the same object |
| `test_22_performances_distinct_perf_tls` | 22 distinct `result.target_timeline.uid` values |
| `test_22_performances_same_score_id` | All claims share same `timeline_a_id` |
| `test_claim_count_all_22` | Total claims = 454 × 22 = 9,988 |

### Validation Against Gold Standard

The `ms3/` TSV files serve as the score ground truth.

- `chopin_op10_no3.notes.tsv` → 498 notes (full score); only 454 appear in `.match` files
  (the 44-note discrepancy must be documented in the loader's docstring once confirmed).
- Cross-check: score onset values from the `.match` file (`scoreOnset` float field)
  must match `quarterbeats_float` from `PartituraLoader` for the same note IDs.

### What We Do NOT Test Here

- Full `AlignmentBundle` construction (tested in `tests/alignment/test_bundle.py`).
- `WarpMap` generation (tested in `tests/alignment/test_warpmap.py`).
- Audio-level alignment (no audio files provided).

---

## Performance Benchmark

Profiling baseline for `MatchfileLoader` on this dataset (to be updated after implementation):

| Operation | Target Time | Notes |
|---|---|---|
| Parse single `.match` file | < 50 ms | Pure Python regex + parsing |
| Load all 22 `.match` files | < 1 s | Vectorized path |
| Build MatchClaims (single file) | < 10 ms | Dataclass construction |
| Build 22-performance AlignmentBundle | < 2 s | Including shared score TL |

```bash
# PLANNED — profiling script not yet implemented
# python tests/loader/profile_matchfile.py
```

---

## Known Issues and Discrepancies

1. **Score note subset:** The `.match` files align 454 of the 510 score notes
   (498 regular + 12 grace notes). The remaining notes are presumably not present
   in the match format's coverage (possibly cross-validation artifacts). This must
   be investigated and documented with exact counts once the loader is implemented.

2. **Negative score onsets:** Score onset `−0.5` for the anacrusis note (n1, measure 0,
   beat 1). The `MatchfileLoader` stores raw coordinates as-is (preserving the negative
   value) and attaches a `ShiftMap` named `"raw_to_normalised"` to the score timeline.
   The offset is computed dynamically from the file (`−min(raw_onsets)`), never
   hardcoded. `PartituraLoader` also shifts these coordinates; a follow-up task (Phase B
   step 8b in `matchfile_loader_plan.md`) adds the same ShiftMap to its output timeline
   so that downstream code can inspect the offset and align coordinate spaces.

3. **Deletion semantics:** The Vienna format uses `snote(...)-deletion` (not the
   reverse — it is the *score* note that has no *performance* counterpart, i.e. the
   pianist omitted it). This maps to `MatchClaim.nomatch(source_tl_id=score_tl_id,
   target_tl_id=perf_tl_id)`, not the other way around.

4. **Grace note duration:** Grace notes have `duration=1/8` in the score field but
   `score_onset == score_offset` (zero duration as notated). The distinction is between
   *nominal* duration (encoded) and *performed* duration (zero). Store both.

---

## Running Tests

```bash
# All vienna_1x22-related tests (PLANNED — test file not yet implemented)
# pytest tests/loader/test_matchfile_loader.py -v

# Cross-validation with score loader tests
pytest tests/loader/score/test_cross_validation.py -v -k "chopin"

# Run with profile output (PLANNED — profiling script not yet implemented)
# pytest tests/loader/test_matchfile_loader.py -v -s --tb=short
```
