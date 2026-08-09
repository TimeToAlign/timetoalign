# Symbolic score loader tests

These tests validate the symbolic score loaders against exact source-derived values. TSV data
loaded by `Ms3Loader` is authoritative whenever loaders are compared.

## Test files

| File | Remaining coverage |
|---|---|
| `conftest.py` | Seven specimen definitions, source lookup, size guards, and `.flow.csv` parsing. |
| `test_score_parsing_matrix.py` | CSV modes, folded and unfolded counts, loader/format combinations, exact flow-control profiles, target-flow reproduction, cross-loader counts, and pinned parser differences. |
| `test_loaders.py` | MS3 coordinate and duration semantics, pitch schema, Partitura measure/MIDI regressions, shared `mc_onset`, anacrusis offsets, and parquet round trips. |
| `test_cross_validation.py` | Exact Chopin note-count and MIDI-pitch agreement across MS3, Partitura, and Music21. |
| `test_measuremap_loader.py` | MeasureMap expansion, validation, traversal, schema, and comparison with MS3. |
| `test_flow_csv_validation.py` | Right-open ranges, exact atomic boundaries, live Partitura boundaries, and CSV serialization. |
| `test_partitura_exactness.py` | Exact Partitura coordinate pairs, instant nulls, flattened timelines, and agreement with Partitura's float map. |

## Parsing matrix

The matrix covers these specimens and exact folded/unfolded measure counts:

| Specimen | Folded | Unfolded | Atomic sections |
|---|---:|---:|---:|
| `rachmaninoff` | 374 | 374 | 1 |
| `polyrhythm_only` | 14 | 14 | 1 |
| `c05n05_musete` | 58 | 138 | 4 |
| `c11n08_Rondeau` | 60 | 138 | 4 |
| `op18_no4_mov4_flow` | 226 | 291 | 13 |
| `flow_only` | 15 | 30 for MS3 | 13 |
| `WoO71` | 397 | 505 | 26 |

For every available source, the matrix checks TSV and MeasureMap folded counts, MeasureMap
default traversal length, Music21 MusicXML and MEI folded counts, Partitura MusicXML and MEI
folded counts, and same-loader MEI/MusicXML equivalence where both formats exist. Files larger
than 500,000 bytes use the documented size skip because third-party parsing is too slow for
this integration suite.

Every `.flow.csv` must exist and contain `atomic` and `default` modes. Its number of atomic rows
must equal the specimen value above. MS3 must reproduce one documented valid default flow and
the exact atomic boundaries. TSV and MeasureMap must have identical folded counts.

## Exact flow-control profiles

`TestFlowControlProfiles` contains the former standalone parity assertions. It derives repeat
counts from either `start_repeat`/`end_repeat` booleans or MS3's `repeats` values, counting
`startend` as both a start and an end.

| Specimen and loader | Measures | Starts | Ends | Other exact values |
|---|---:|---:|---:|---|
| WoO71 TSV | 397 | 11 | 11 | 12 section breaks; 4 double barlines |
| WoO71 MeasureMap | matrix count | 11 | 11 | flow control present |
| WoO71 Music21 | matrix count | 11 | 11 | flow control present |
| WoO71 Partitura | matrix count | region model | region model | flow control present |
| `flow_only` TSV | 15 | 3 | 6 | flow control present |
| `flow_only` MeasureMap | matrix count | 3 | 6 | flow control present |
| `flow_only` Music21 | 15 | 3 | 6 | flow control present |
| `flow_only` Partitura | 15 | 7 | 7 | inferred region boundaries; flow control present |

The marker-based loaders therefore agree exactly on repeat counts. Partitura is intentionally
different on `flow_only`: it completes repeat regions by inferring boundaries.

## Pinned parser differences

`TestDocumentedDeviations` requires intentional updates when third-party parser behavior changes:

- Music21 produces 116 visits for `c05n05_musete`, with sections
  `[(1, 17), (1, 32), (17, 59), (32, 59)]`.
- Music21 produces 120 visits for `c11n08_Rondeau`, with sections
  `[(1, 10), (1, 19), (10, 28), (19, 61), (28, 61)]`.
- Music21's exact `flow_only` MC sequence and nine right-open sections are asserted directly.
- Partitura's `flow_only` source rows have starts at MCs `[1, 4, 6, 9, 10, 11, 12]`, ends at
  `[3, 5, 8, 9, 10, 11, 14]`, and voltas
  `[(5, 1), (6, 2), (7, 3), (14, 1), (15, 2)]`.
- The `flow_only` CSV must retain both `default` and `ms3` interpretations.

## Loader-specific assertions

`test_loaders.py` keeps behavior that is not part of the parsing matrix:

- WoO71 MS3 measures begin with exact `(start, duration, end)` Fractions `(0, 1, 1)`,
  `(1, 2, 3)`, and `(3, 2, 5)`.
- Symbolic triplet duration is exactly `1/3`; native `0.5` is exactly `1/2`; a derived
  `0.3333333333333333` without a symbolic source keeps its double, mirrored by that
  double's exact dyadic `6004799503160661/18014398509481984`. No cell is ever
  pair-less — the assertion checks the mirror is the dyadic and **not** `1/3`, since
  tidying it to `1/3` is the fabrication the exactness rules exist to forbid.
- **Every facet reads the symbolic duration column, not just notes and measures.** An
  ms3 TSV states a duration twice — exactly, as a whole-note fraction in `duration`,
  and derived, as a float in `duration_qb` — and which one a facet reads is not a
  matter of taste. Reading the float discards a representation the source actually
  carries, and the loss is not confined to the last decimal: the exact dyadic of
  `0.0833333333333333` has denominator `2**56`, so adding it to a position of any
  musical size needs a numerator wider than the int64 the coordinate struct stores,
  and the load fails outright. The chords and harmonies facets read the float and
  broke on ordinary triplet durations; both now resolve the same way notes do.

  Pinned on a chord row whose source cells are `quarterbeats = 695/4` and
  `duration = 1/48` (whole notes), beside a `duration_qb` of `0.0833333333333333`:

  | Coordinate | Exact value | Read from |
  |---|---|---|
  | start | `695/4` | `quarterbeats` |
  | duration | `1/12` | `duration` × 4 — *not* the float column |
  | end | `1043/6` | exact sum |

  Taken from the float instead, the same duration is `6004799503160659/2**56` and the
  end is `12526011763593139539/2**56`, whose numerator does not fit. The test asserts
  the exact triple, so a facet quietly falling back to `duration_qb` fails on the
  value rather than only on corpora large enough to overflow.
- **A harmony label's span is stated by the label after it.** A DCML `harmonies`
  facet has no symbolic duration column at all, so the rule above has nothing to
  read. It does carry `duration_qb` — but that column *is* the label-to-label
  subtraction already, carried out in float, and it keeps the residue: the label at
  `1003/2` records `0.16666666666668561`, which is not even the nearest double to
  `1/6`. Redoing the subtraction on the exact `quarterbeats` cells recovers what the
  source encodes (`1505/3 − 1003/2 = 1/6`), so this is the source's own derivation
  minus its rounding, not a semantics the loader invented. Snapping a float residue
  to a tidy ratio stays forbidden — the value here is *read*, never guessed.

  The final label has no successor, so its span runs to the end of the piece, taken
  from the companion `measures` facet as the furthest measure position plus that
  measure's `act_dur` × 4. Pinned on the Meistersinger prelude: the last label starts
  at `1759/2` and the measures facet ends at `884 + 4 = 888`, giving `17/2` — the same
  `8.5` ms3 derived, now exact. Where either end of a span is missing, out of order or
  inexact, the loader says nothing and falls back to the derived column rather than
  asserting a span the source does not support.

- **The whole score corpus is loaded, not a chosen file.** All 46 `.chords.tsv` and
  `.harmonies.tsv` files in the `score` corpus, and all 4 in `supra`, are loaded in
  one slow-marked sweep. This is deliberately a sweep rather than a specimen: the
  defect above sat behind a green suite because the affected files were in no test's
  load set, and a hand-picked replacement specimen would reproduce exactly that gap.
  `supra` is included because its Meistersinger harmonies are the only corpus files
  exercising the label-span derivation at a magnitude where the float column
  overflows. Marked slow; runs under `--runslow`.
- All 4,753 populated WoO71 note coordinates carry exact numerator/denominator pairs; instant
  rows keep null ends and durations.
- MS3 exposes spelled pitch once through `specific_pitch`, retains raw MIDI 59 for the first B3,
  and affords the same number through `EnharmonicPitch`.
- Partitura extracts 22 Chopin measures and loads the Beethoven MIDI regression as 4,186 notes.
- MS3, Partitura, and Music21 populate `mc_onset`.
- Chopin's raw Partitura onset is exactly `-0.5` quarter beats and its normalization offset is
  exactly `0.5`; Music21's offset is exactly `0.0`. Metadata and store properties carry those
  exact values.
- `ScoreStore` and loader parquet tests pin files, note/measure counts, metadata, units, empty
  facets, missing paths, and event-property round trips.

The 498-note Chopin gold value is asserted once per loader in
`TestNoteCountConsistency.test_note_counts_exact_match`. The same module requires exact MIDI
pitch equality and checks both `EnharmonicPitch` and `MidiPitch` views for all 498 events.

## Coordinate exactness

Temporal coordinates use structs with `value`, `numerator`, and `denominator`. Populated
coordinates must retain their pair; instant events must keep null `end` and `duration` values.
The flattened Chopin timeline contains exactly 547 rows: 31 instants and 516 intervals. Known
Partitura divisions include start `11/2` with duration `3/4` and start `3/4` with duration `1/4`.

There are no `pytest.approx` calls in the score-loader tests. Exact integers, Fractions, binary
halves, zero offsets, metadata values, and coordinate extents use equality. The only tolerance is
the explicit `< 1e-6` comparison in `test_partitura_exactness.py`; it compares exact rational
coordinates with values returned by Partitura's genuinely floating-point `quarter_map`.

## MeasureMap and flow CSV contracts

MeasureMap tests require unique MC values, monotonic `qstamp`, valid `next` references, exact
linear/repeat traversals, 397 folded and 505 unfolded WoO71 measures, and matching MS3 MCs and
repeat presence. Its schema must include flow-control and identity fields. The synthetic summary
contains three measures, one repeat start, and one repeat end.

Flow CSV tests enforce right-open contiguous atomic ranges. Exact samples are
`c05n05_musete`: `A=(1, 6)`, `B=(6, 17)`, `C=(17, 32)`, `D=(32, 59)`;
`polyrhythm_only`: `A=(1, 15)`; and `rachmaninoff`: `A=(1, 375)`. Live Partitura segments are
compared against the corresponding CSV rows, and `Flow.from_csv` must survive a records round trip.

## Running the tests

From the repository root:

```bash
/home/laser/miniconda3/envs/timetoalign/bin/python -m pytest --runslow tests/loader/score
```
