# Loader tests

This directory tests the loader package end-to-end, covering all formats
(``tabular/``, ``score/``, ``midi/``, ``graphical/``, ``format/``,
``physical/``, ``paths/``), the ``EventStore`` and ``EventData`` machinery,
and the shared loader infrastructure (base classes, matchfiles, schemas,
bundles, error handling).

## Categories

| File / Subdirectory | What it validates |
|---------------------|-------------------|
| `test_loader.py` | Generic loader smoke tests and contract checks |
| `test_base_loaders.py` | The `EventLoader` / `ManifestLoader` / `AlignmentLoader` ABCs |
| `test_bundle.py` | `AlignmentBundle` produced by alignment loaders |
| `test_error_handling.py` | Faulty-input behaviour across loaders |
| `test_interval_policy.py` | Half-open interval semantics on event ingestion |
| `test_matchfile_loader.py` | `MatchfileLoader` parity against gold standard |
| `test_performance_precision_loader.py` | `PerformancePrecisionLoader` against the CAAMP Chopin Nocturne specimen — composes `SoloLoader` for the `.solo` score (2494 notes), builds the score timeline by resolving every `"<measure>+<offset>"` label to absolute quarters via the `MetricMap`, and emits one physical timeline + three granularities of `MatchClaim` per performer. Zero-tolerance counts (see "Validation logic" below). |
| `test_parangonada_loader.py` | `ParangonadaLoader` against the parangonada CSV export of the `Beethoven_Eroica_op35-cpjku` dataset (5 performers). Builds one shared multimodal `AlignmentBundle` (1 score group + 5 performer groups) from `part.csv` / `ppart.csv` / `align.csv`. Zero-tolerance counts (see "Validation logic" below). |
| `test_parsing.py` | Format-agnostic parsing helpers |
| `test_schema.py` | `TableSchema` and field-spec resolution |
| `test_store.py` | `EventStore` low-level operations |
| `test_tilia_loader.py` | `TiliaJsonLoader` round-trip |
| `test_mixins.py` | `EventData` field-access mixins — three-strategy field discovery (metadata, default-column, shape-based `matches_pa_field`), `has_field`, `get_field`, `get_fields`, `get_raw`, and the convenience accessors (`get_pitch_field`, `get_harmony_field`). |
| `test_mixins_wp3.py` | Dispatch additions on `SemanticFieldAccessMixin` — `get_field(ScalarClass)` pydantic-scalar dispatch, `IdCoordinate` vs `Coordinate` discrimination via metadata (`matches_pa_field` rejection contracts), `MultipleFieldsError` on ambiguity + `name=` resolution, and `get_fields_satisfying(ProtocolClass)` Protocol-based grouping (covering `GenericPitchLike` and `TimeScalarLike`). |
| `test_field_parsers.py` | The :class:`FieldParser` hierarchy and `resolve_field_parser` universal-resolution dispatcher. Exercises the DataField blueprint mechanism: `IntField`, `FloatField`, `StringField`, `RationalField`, `DenominateNumberField`, and paired SemanticField subclasses all accept `name=` for blueprint construction and expose a uniform `emit(source, name=...)` materialisation. `CompositeFieldParser` (separator + regex strategies, dict + iterable parts) and `CallableFieldParser` (escape hatch) are exercised end-to-end. Resolution-table assertions: every entry (Python type, `pa.DataType`, raw / paired `DataField` subclass, blueprint instance, `FieldParser` instance, callable) routes to the correct producer. |
| `test_step2_field_specs.py` | Step 2 (`field_specs`) blueprint resolution. Builds a fixture `pa.Table` and a `TabularLoader` subclass with `field_specs = [...]`, verifies that each blueprint matches its declared `source_fields=` entry, that the resulting column receives `b"timetoalign"` metadata (`field_type` = paired class name), that atomic source columns are packed into single-field structs matching the target `pa_schema`, and that unresolvable references raise `KeyError`. Exercises the two currently-supported `source_fields=` shorthands (string for single-source promotion; explicit dict for multi-sub-field mapping) and the negative cases (list shorthand rejected by `resolve_source_fields` today; live-mode SemanticField instances rejected; multi-source dict spec raises `NotImplementedError` at loader-materialisation time). |
| `test_get_events_properties.py` | The four shapes accepted by `Loader.get_events(properties=...)` — `True`, `False`, a tuple of property names, and the single-string shorthand that normalises to a one-element tuple. |
| `tabular/` | CSV / TSV / Parquet loader specifics |
| `score/` | Music-notation loaders (Ms3, music21, Partitura) |
| `midi/` | Score and performance MIDI loaders |
| `graphical/` | PDF / image loaders |
| `format/` | Cross-format loaders (JSON, XML, TTL) |
| `physical/` | Audio loaders and time-coordinate ingestion |
| `paths/` | Path resolution helpers |

## Data conventions

Tests resolve corpus paths via ``timetoalign.testdata.ensure_data("<corpus>")``
(see ``tests/data/README.md``).  Hardcoded relative ``Path("tests/data/...")``
constants are forbidden — they break under ``jupytext --execute`` and in CI
container layouts.  See ``CLAUDE.md`` "Test Data Provisioning" for the
binding contract.

## `PerformancePrecisionLoader` validation logic

Corpus: ``performance_precision`` (CAAMP export of Chopin Nocturne Op. 9
No. 2 — one ``.solo`` score, one Verovio timemap ``.json``, and an
``Alignments/`` directory with three CSVs for each of 7 recordings).

The loader's correctness rests on a single coordinate resolver that turns
a ``"<measure>+<offset_in_whole_notes>"`` label into an absolute
quarter-note position:

```
abs_quarters(M, offset_wn) = measure_start_q[M] + offset_wn * 4
```

``measure_start_q[M]`` is taken from the ``MetricMap`` built from the
Verovio timemap for LABEL measure ``M >= 1``.  LABEL measure ``0`` is the
anacrusis, whose offsets are measured from a *virtual full-bar downbeat*
preceding the first sounding note: ``measure_start_q[0] = starts[1] −
first_meter_quarters``, where ``first_meter_quarters`` is the nominal
length of the first bar (``12/8`` → ``6`` quarters) read from the
timemap's first ``meterSig``.  On this specimen ``measure_start_q[0] ==
Fraction(-11, 2)`` (−5.5).

**Validated resolver anchors** (exact ``Fraction``):

| LABEL | abs quarters |
|-------|--------------|
| `0+11/8` | `0` |
| `1+0/1` | `1/2` |
| `2+0/1` | `13/2` |
| `3+0/1` | `25/2` |
| `32+3/4` | `379/2` |
| `37+3/2` | `425/2` |

**Composed `SoloLoader`:** 2494 events.

**Score timeline:** 2494 events, unit quarters, length `Fraction(425, 2)`
(212.5).  The pickup note (`note_id == "n1b8xktz"`) resolves to start
quarter `0`; a `1+0/1` note resolves to `1/2`.

**Per performer (identical for all 7):** the note-level file has 559 data
rows splitting 480 *aligned* (synchronous claims) + 79 *dangling*
(`TIME == "N"`, NOMATCH claims); the bar file has 32 rows (all
synchronous); the beat file has 376 rows (all synchronous).  These are the
true data-row counts — earlier `wc -l` figures (560/33/377) included the
``LABEL,TIME,FRAME`` header.

**Totals across 7 performers:** 6769 MatchClaims = 6216 synchronous + 553
NOMATCH.  The bundle holds 8 timelines (1 score group + 7 standalone
performers).

**Coordinate spot-check:** Ashkenazy's bar-level claim for LABEL `1+0/1`
has source coordinate `Fraction(1, 2)` (0.5 quarters) and target
coordinate `10.272` seconds.

The 6 of 1247 note onsets that do not resolve exactly are inherent tuplet
rounding in the ``.solo``'s quantised representation; the
``.solo``/``MetricMap`` arithmetic is the faithful score representation
and the tests assert exact values only on the validated anchors above.

## `ParangonadaLoader` validation logic

Corpus: ``parangonar`` (the parangonada CSV export of the
``Beethoven_Eroica_op35-cpjku`` dataset — Beethoven Eroica Variations
op. 35, Var. XIV, 5 performers). The loader ingests the *existing*
alignments; it never runs an aligner.

### Dataset shape

The 5 performers live as subdirectories of
``match/match_transkun/``. Their directory names carry a *non-uniform*
suffix — only two end in ``_parangonada``:

| Performer key | Subdirectory name |
|---------------|-------------------|
| `1966_Szegedi` | `1966_Szegedi_parangonada` |
| `1970_Gould`   | `1970_Gould_parangonada` |
| `1971_Curzon`  | `1971_Curzon` |
| `1985_Brendel` | `1985_Brendel` |
| `2023_Hewitt`  | `2023_Hewitt` |

Performers are discovered by globbing the immediate subdirectories of
``match/match_transkun/`` (not the sibling ``.csv`` / ``.match`` files
that also live there) and requiring each to contain ``part.csv``,
``ppart.csv``, and ``align.csv``. The key is the directory name with a
trailing ``_parangonada`` stripped. They are sorted by key, which is
chronological: Szegedi, Gould, Curzon, Brendel, Hewitt.

Three CSV families:

* ``part.csv`` — the shared score. **Byte-identical across all 5**
  performers (same md5), so it is parsed once. Header
  ``onset_beat,duration_beat,onset_quarter,duration_quarter,onset_div,
  duration_div,pitch,voice,id``; **251** data rows; ``id`` unique;
  ``pitch`` is a MIDI integer; ``onset_quarter`` a value parsed as an
  exact ``Fraction`` (the score has an anacrusis at ``-1/2``);
  ``onset_div`` an int. Two arithmetic invariants hold for all 251 rows
  (0 exceptions): ``onset_div == 32 * onset_quarter + 16`` and
  ``duration_div == 32 * duration_quarter``.
* ``ppart.csv`` — per-performer performance notes in seconds. Header
  ``onset_sec,duration_sec,pitch,velocity,track,channel,id``; ``id``
  like ``n0``; ``onset_sec`` a float. Data-row counts: Szegedi 232,
  Gould 253, Curzon 246, Brendel 249, Hewitt 244.
* ``align.csv`` — per-performer correspondences. Header
  ``idx,matchtype,partid,ppartid``. The "no counterpart" sentinel is
  the literal string ``undefined``. ``matchtype`` ``0`` = match (both
  ids present), ``1`` = score-only / insertion (``ppartid ==
  "undefined"``), ``2`` = performance-only / deletion (``partid ==
  "undefined"``).

The ``score.mei`` (partitura raises ``KeyError: 'dur'`` on it),
``feature.csv`` (all-zero placeholder), ``zalign.csv`` (byte-duplicate
of ``align.csv``), ``majority_match/*.match``, and the
``transcribed_midi/`` tree are deliberately **not** parsed. The
``.beats`` / ``.dyn`` feature files are a separate concern.

### Bundle structure

One shared **score group** ``"score"`` (the same 251 notes in two
logical units):

* ``score:clt1`` — `ContinuousLogicalTimeline`, quarters, 251 note
  events with ``start = onset_quarter`` (exact `Fraction`), carrying
  ``pitch`` (MIDI int) and ``voice`` (int).
* ``score:dlt1`` — `DiscreteLogicalTimeline`, ticks (``divs``), the
  same 251 notes with ``start = onset_div`` (int). A divs→quarters
  C-Map ``LinearMap(slope = 1/32, intercept = -1/2)`` is attached; it
  reproduces every ``onset_quarter`` from ``onset_div`` exactly
  (asserted for all 251 rows, exact `Fraction` equality).

Per performer, a **performance group** ``perf:<key>`` (the same
performed notes in two physical units):

* ``perf:<key>:cpt1`` — `ContinuousPhysicalTimeline`, seconds, one note
  event per ``ppart.csv`` row with ``start = onset_sec`` (float),
  carrying ``pitch`` and ``velocity``.
* ``perf:<key>:dpt1`` — `DiscretePhysicalTimeline`, samples, the same
  notes with ``start = round(onset_sec * sample_rate)``. A
  ``SamplesToSeconds(sample_rate=44100)`` C-Map is attached
  (``sample_rate`` read from the performer's 44100 Hz stereo ``.wav``
  via `AudioLoader`).

### Cross-group MatchClaims

One claim per ``align.csv`` row, per performer, faithfully (no
deduplication):

* **matchtype 0** → `MatchClaim.from_projection` from ``score:clt1`` to
  ``perf:<key>:cpt1``: source coordinate = the part note's
  ``onset_quarter``, target coordinate = the ppart note's
  ``onset_sec``.
* **matchtype 1** (score-only) → `MatchClaim.nomatch` with source
  ``score:clt1`` and target ``perf:<key>:cpt1`` (source coordinate =
  the part note's ``onset_quarter``).
* **matchtype 2** (performance-only) → `MatchClaim.nomatch` with source
  ``perf:<key>:cpt1`` and target ``score:clt1`` (source coordinate =
  the ppart note's ``onset_sec``).

Each performer's claims share a
``MatchMetadata(agent="parangonada",
decision_criteria="parangonada_export", certainty=1.0,
algorithm_params={"performer": key})``.

### Zero-tolerance counts

| Performer | ppart events | align total | mt0 (sync) | mt1+mt2 (NOMATCH) |
|-----------|--------------|-------------|------------|--------------------|
| Szegedi   | 232 | 256 | 227 | 29 |
| Gould     | 253 | 257 | 247 | 10 |
| Curzon    | 246 | 255 | 242 | 13 |
| Brendel   | 249 | 253 | 249 | 4 |
| Hewitt    | 244 | 254 | 243 | 11 |
| **Total** |     | **1275** | **1208** | **67** |

The bundle holds **12** timelines and **6** groups (1 ``score`` + 5
``perf:<key>``). ``score:clt1`` and ``score:dlt1`` each carry 251
events.

**Coordinate spot-check:** Szegedi's ``align.csv`` row at ``idx 0`` is
``0,0,ngx1f26,n149``. It produces a synchronous claim from
``score:clt1`` to ``perf:1966_Szegedi:cpt1`` whose source coordinate is
``40.0`` (``score_q_by_id["ngx1f26"]``, an exact quarter) and whose
target coordinate is ``38.183334`` seconds (``perf_sec_by_id["n149"]``).

**Known data quirk (faithfully preserved, NOT a bug):** Brendel and
Hewitt each contain exactly one *duplicated* matchtype-0 row — Brendel
``n1qocvw7 ↔ n65`` at ``idx`` 74 and 75; Hewitt ``n1qocvw7 ↔ n64`` at
``idx`` 71 and 72. The loader emits one claim per row, so the duplicate
survives (Brendel's 253 and Hewitt's 254 totals include it). One test
asserts the duplicate is present in the raw ``align.csv`` so a future
reader knows it is data, not a loader fault. The loader does **not**
deduplicate.

**C-Map round-trip:** ``SamplesToSeconds(44100)`` on a ``dpt1`` timeline
converts ``44100`` samples to ``1.0`` seconds (and ``sample / 44100``
generally).
