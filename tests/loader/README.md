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
| `test_parangonada_loader.py` | `ParangonadaLoader` against the parangonada CSV export of the `Beethoven_Eroica_op35-cpjku` dataset (5 performers). Builds one shared multimodal `AlignmentBundle` (1 score group + 5 performer groups) from `part.csv` / `ppart.csv` / `align.csv`, plus measured `Beat` / `Dynamics` feature events (`.beats` / `.dyn`) on each performance's seconds timeline. Zero-tolerance counts (see "Validation logic" below). |
| `test_parsing.py` | Format-agnostic parsing helpers |
| `test_schema.py` | `TableSchema` and field-spec resolution |
| `test_store.py` | `EventStore` low-level operations |
| `test_tilia_loader.py` | `TiliaJsonLoader` round-trip |
| `test_mixins.py` | `EventData` field-access mixins — three-strategy field discovery (metadata, default-column, shape-based `matches_pa_field`), `has_field`, `get_field`, `get_fields`, `get_raw`, and the convenience accessors (`get_pitch_field`, `get_harmony_field`). |
| `test_mixins_wp3.py` | Dispatch additions on `SemanticFieldAccessMixin` — `get_field(ScalarClass)` pydantic-scalar dispatch, `IdCoordinate` vs `Coordinate` discrimination via metadata (`matches_pa_field` rejection contracts), `MultipleFieldsError` on ambiguity + `name=` resolution, and `get_fields_satisfying(ProtocolClass)` Protocol-based grouping (covering `GenericPitchLike` and `TimeScalarLike`). |
| `test_field_parsers.py` | The :class:`FieldParser` hierarchy and `resolve_field_parser` universal-resolution dispatcher. Exercises the DataField blueprint mechanism: `IntField`, `FloatField`, `StringField`, `RationalField`, `DenominateNumberField`, and paired SemanticField subclasses all accept `name=` for blueprint construction and expose a uniform `emit(source, name=...)` materialisation. `CompositeFieldParser` (separator + regex strategies, dict + iterable parts) and `CallableFieldParser` (escape hatch) are exercised end-to-end. Resolution-table assertions: every entry (Python type, `pa.DataType`, raw / paired `DataField` subclass, blueprint instance, `FieldParser` instance, callable) routes to the correct producer. |
| `test_step2_field_specs.py` | Step 2 (`field_specs`) blueprint resolution. Builds a fixture `pa.Table` and a `TabularLoader` subclass with `field_specs = [...]`, verifies that each blueprint matches its declared `source_fields=` entry, that the resulting column receives `b"timetoalign"` metadata (`field_type` = paired class name), that atomic source columns are packed into single-field structs matching the target `pa_schema`, and that unresolvable references raise `KeyError`. Exercises the two currently-supported `source_fields=` shorthands (string for single-source promotion; explicit dict for multi-sub-field mapping) and the negative cases (list shorthand rejected by `resolve_source_fields` today; live-mode SemanticField instances rejected; multi-source dict spec raises `NotImplementedError` at loader-materialisation time). |
| `test_get_events_properties.py` | The four shapes accepted by `Loader.get_events(properties=...)` — `True`, `False`, a tuple of property names, and the single-string shorthand that normalises to a one-element tuple. |
| `test_represent_pitch_once.py` | The **represent-pitch-once** contract across every pitch-bearing EventData and loader. Verifies (1) the keystone `from_dicts` / `add_events` struct-preservation fix (carried struct-dict columns become real `pa.struct` columns with `field_type` metadata, never JSON strings); (2) the uniform `_afforded_fields` mechanism that promotes a raw atomic column to its semantic view on request; (3) the per-source default pitch type (`get_pitch_field()` → SP for spelled, EP for number-only, EP for MSM with SPC additionally afforded); (4) represent-once (no EventData carries a redundant *default* pitch struct — score notes no longer afford a default EnharmonicPitch); (5) the scalar↔EventData contract for MIDI EventData; (6) on-request EP from a SP field via both routes (conversion + raw column). See "Represent pitch once" below. |
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
``transcribed_midi/`` tree are deliberately **not** parsed.

The per-performer ``.beats`` / ``.dyn`` files under the dataset's
``features/`` directory **are** parsed (see "Feature events" below).

### Bundle structure

One shared **score group** ``"score"`` (the same 251 notes in two
logical units):

* ``score:clt1`` — `ContinuousLogicalTimeline`, quarters, 251 note
  events with ``start = onset_quarter`` (exact `Fraction`), carrying
  ``pitch`` (MIDI int) and ``voice`` (int).
* ``score:dlt1`` — `DiscreteLogicalTimeline`, ticks (``divs``), the
  same 251 notes with ``start = onset_div`` (int). A divs→quarters
  C-Map ``LinearMap(scalar=Fraction(1,32), offset=Fraction(-1,2))`` is
  attached (``scalar`` / ``offset`` are the constructor's real
  parameter names); it reproduces every ``onset_quarter`` from
  ``onset_div`` exactly (asserted for all 251 rows, exact `Fraction`
  equality).

Per performer, a **performance group** ``perf:<key>`` (the same
performed notes in two physical units):

* ``perf:<key>:cpt1`` — `ContinuousPhysicalTimeline`, seconds, one note
  event per ``ppart.csv`` row with ``start = onset_sec`` (float),
  carrying ``pitch`` and ``velocity``; **plus** the measured beat
  features (see "Feature events" below) as ``Beat`` and ``Dynamics``
  events on the same timeline.
* ``perf:<key>:dpt1`` — `DiscretePhysicalTimeline`, samples, the same
  notes with ``start = round(onset_sec * sample_rate)``. A
  ``SamplesToSeconds(sample_rate=44100)`` C-Map is attached
  (``sample_rate`` read from the performer's 44100 Hz stereo ``.wav``
  via `AudioLoader`).

### Feature events

Each performance carries a pair of measured beat-feature files under
the dataset's ``features/`` directory, tab-separated. They are
discovered by **globbing** ``<key>_measure*.{beats,dyn}`` — the stems
are non-uniform: Szegedi's are ``1966_Szegedi_measure_fix.{beats,dyn}``,
the other four are ``<key>_measure.{beats,dyn}``. All ten files have
**63 data rows**.

* ``.beats`` (7 columns) — header
  ``measure_number  beat  onset_beat  onset_sec  BPM  interp  swap``.
  Each row becomes a ``Beat`` event on ``perf:<key>:cpt1`` at
  ``start = onset_sec``, carrying ``measure_number`` / ``beat`` /
  ``bpm`` (from ``BPM``) / ``interp`` / ``swap``. Event id
  ``<key>:beat:<i>``.
* ``.dyn`` (6 columns) — header
  ``measure_number  beat  onset_beat  velocity_mean  velocity_max
  interp`` (**no** ``onset_sec``, **no** ``swap``). Each row becomes a
  ``Dynamics`` event on ``perf:<key>:cpt1`` carrying ``measure_number``
  / ``beat`` / ``velocity_mean`` / ``velocity_max`` / ``interp``. Event
  id ``<key>:dyn:<i>``.

Because the ``.dyn`` rows have no onset, each is joined to the
``.beats`` row sharing its ``(measure_number, beat)`` key to recover
its ``onset_sec``. The two files are **1:1 on ``(measure_number,
beat)``**: the keys are unique within each file and the two key sets
are identical, so the join yields exactly 63 matches (asserted). These
are *measured* per-beat features (variable tempo + dynamics from the
recording); no tempo curve is synthesised (no ``BeatGrid.from_tempo``).

The events are added to the **existing** seconds timeline (not a new
timeline, not on ``dpt1``) via ``add_events(rows,
allow_expansion=True)``. The ``cpt1`` schema already holds ``Note``
columns (``pitch`` / ``velocity``); the ``Beat`` / ``Dynamics`` rows
introduce new columns (``bpm`` / ``measure_number`` / ``beat`` /
``velocity_mean`` / …). Successive ``add_events`` calls grow the schema
via ``pyarrow.concat_tables(promote_options="default")``, so the
heterogeneous ``Note`` / ``Beat`` / ``Dynamics`` table round-trips with
absent columns null-filled. After ingestion each ``perf:<key>:cpt1``
holds its ppart ``Note`` events (the per-performer count above) **plus
63 ``Beat`` and 63 ``Dynamics``** events.

The feature events do **not** change the bundle totals — the claim
counts, timeline count (12), and group count (6) are derived from
``part.csv`` / ``ppart.csv`` / ``align.csv`` only and are unchanged.

**Feature spot-checks (Szegedi):**

* ``.beats`` row 0 (``1  1  0.000000  0.796354  83.660126  0  0``) → a
  ``Beat`` event at ``start == 0.796354`` with ``measure_number == 1``,
  ``beat == 1``, ``bpm == 83.660126``.
* ``.dyn`` row 0 (``1  1  0.000000  48.500000  58.000000  0``) → a
  ``Dynamics`` event at ``start == 0.796354`` (onset joined from the
  ``.beats`` row with the same ``(1, 1)`` key) with
  ``velocity_mean == 48.5``, ``velocity_max == 58.0``.

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

## `MpmLoader` validation logic

Corpus: ``mpm_toolbox`` (two MPM-Toolbox projects, each a sibling
``.msm`` / ``.mpm`` / ``.mpr`` triple in its own subdirectory). Tests are
parametrized over both specimens:

- **Beethoven** — directory ``MPRproject_1971Curzon_VariationXIV/``, stem
  ``Beethoven_op35_1971Curzon_Var14only``. Recording: a 44100 Hz ``.wav``.
- **Reger** — directory ``Max Reger - Moment Musical (MPM Toolbox
  Tutorial)/``, stem ``Reger - Moment Musical op 13 no 4``. Recording: a
  48000 Hz ``.wav``.

### What the loader builds

``MpmLoader.from_file(mpr_path).create_bundle()`` produces one
``AlignmentBundle`` with **5 timelines** in **2 groups** (both specimens
carry a spectrogram, so the graphical axis is always present here):

- a shared ``"score"`` group:
  - ``score:dlt1`` — a ``DiscreteLogicalTimeline`` in ticks holding the
    MSM ``Note`` events *and* every MPM markup event (``Tempo`` /
    ``Dynamics`` / ``Articulation`` / ``Asynchrony`` / any other map
    type), carrying a ticks→quarters ``TicksToQuarters(ppq)`` map;
  - ``score:clt1`` — a ``ContinuousLogicalTimeline`` in quarters holding
    the same ``Note`` events (onset ``date / ppq`` as an exact
    ``Fraction``), carrying a modelled quarters→seconds ``TableMap``;
- a ``"perf"`` group (3 timelines):
  - ``perf:cpt1`` — a ``ContinuousPhysicalTimeline`` in seconds, one
    ``Note`` event per observed onset (``milliseconds.date / 1000``);
  - ``perf:dpt1`` — a ``DiscretePhysicalTimeline`` in samples, the same
    onsets scaled by the sample rate, carrying ``SamplesToSeconds``;
  - ``perf:dgt1`` — a ``DiscreteGraphicalTimeline`` in pixels: the
    spectrogram's frame-column x-axis (see *Spectrogram graphical axis*
    below). It carries **no events** — it is a graphical axis, not an
    event timeline — and a px→seconds ``ScalarMap``;
- one synchronous cross-group ``MatchClaim`` per score note, projecting
  ``score:clt1`` (quarters) onto ``perf:cpt1`` (seconds).

The bundle therefore spans all **three domains**: logical (quarters /
ticks), physical (seconds / samples), and graphical (pixels). A test
collects the units across every timeline (via ``bundle.get_timeline(uid)``
and ``timeline.unit.domain``) and asserts that all three ``Domain``
members are present.

### Parsing notes

The three files are parsed with ``lxml`` using
``etree.XMLParser(recover=True, collect_ids=False)``. ``collect_ids`` is
**off** because the MSM / MPM / MPR reuse ``xml:id`` values across files;
a default id-collecting parser raises ``XMLSyntaxError: ID … already
defined``. The ``.mpm`` uses the CEMFI MPM default namespace, so its
elements are matched by local name; the ``.msm`` and ``.mpr`` are plain
XML. All numeric attributes are float-strings, parsed ``int(float(x))``
for integers (ticks / pitch / octave) and ``float(x)`` for reals.

The MSM ``midi.pitch`` integer is stored verbatim as the pitch; the
spelling attributes (``pitchname`` / ``accidentals`` / ``octave``) are
carried as-is. No ``SpecificPitch`` is constructed — the MSM octave
numbering is inconsistent with ``midi.pitch`` under scientific notation,
so interpreting it would be inference rather than faithful
representation.

The ``.mpr`` carries two ``<note ref …>`` blocks: a ``<score><page>``
block of score-image 2-D coordinates (**not** parsed here — a later
concern) and an ``<alignment>`` block (under ``<audios>/<audio>``) of
observed onsets (``ref`` / ``midi.pitch`` / ``milliseconds.date`` /
``velocity``). Only the alignment block is read for the onset events.

### Spectrogram graphical axis

The ``.mpr`` also carries a ``<spectrogram windowFunction hopSize
minFrequency maxFrequency binsPerSemitone normalize file>`` element under
``<audios>/<audio>``. Its x-axis is time in *frame columns*: each column
advances by ``hopSize`` audio samples. The XML has **no width/height**, so
the number of frame columns equals the **pixel width of the referenced
``.png``** (``file``, resolved relative to the ``.mpr``'s parent
directory). The width is read directly from the PNG IHDR header (bytes
16:20 are the big-endian ``uint32`` width) — no image-decoding dependency
is added. The pinned widths are **Beethoven 26469** and **Reger 1587**
frame columns.

``perf:dgt1`` is built as ``DiscreteGraphicalTimeline(length=<png width>,
unit=TimeUnit.pixels)`` and carries **0 events** (the columns are an axis,
not events). Its only attachment is a px→seconds ``ScalarMap`` with scalar
``hopSize / sample_rate`` (so ``seconds = px * hopSize / sample_rate``,
``map(0) == 0``):

- **Beethoven**: ``hopSize`` 128, sample rate 44100, scalar
  ``128 / 44100``; ``map(1) == 128 / 44100`` and ``map(26469) ==
  26469 * 128 / 44100`` (the audio duration in seconds).
- **Reger**: ``hopSize`` 512, sample rate 48000, scalar ``512 / 48000``;
  ``map(1) == 512 / 48000``.

The map is pulled off the timeline via
``timeline.get_conversion_map(TimeUnit.seconds)`` and asserted to be a
``ScalarMap`` with the expected scalar. The per-note score-image
``<score><page><note ref x y>`` 2-D coordinates remain unparsed (a later
concern — per-event 2-D graphical storage does not exist yet).

When a project carries no ``<spectrogram>`` (or its ``.png`` is missing),
``perf:dgt1`` is simply absent and the bundle holds 4 timelines; the
loader does not crash. Both specimens here have one.

### Performance selection and style resolution

The MPM holds several ``<performance>`` blocks; the **first** is the
default. ``load(mpr_path, performance=<name>)`` selects another.

Within the chosen performance, maps appear under both
``performance>global>dated`` and every ``performance>part>dated``
(``tempoMap`` / ``asynchronyMap`` are global, ``articulationMap`` is
per-part, ``dynamicsMap`` is either). Each map's leading ``<style
name.ref="…">`` child is *not* an entry; it names the active styleDef.
One markup event is emitted per remaining entry, ``event_type`` =
capitalised element local-name.

Tempo / dynamics values are inline numbers (audio performances) *or*
style names resolved against the performance's ``tempoDef`` / ``dynamicsDef``
(``value``). Articulation ``name.ref`` resolves against an
``articulationDef`` whose snake-cased numeric attributes
(``relative_duration`` / ``absolute_duration_ms`` / ``absolute_velocity``
/ ``absolute_velocity_change`` …) become event columns; a ``name.ref``
with no matching def carries the name only (no crash). Any unrecognised
map type is emitted generically (raw attributes carried verbatim), so
nothing is dropped.

### The central join

The alignment ``ref`` → MSM ``xml:id`` is a **perfect bijection** in both
specimens (zero orphan refs, zero unaligned MSM ids). Every score note
has exactly one observed onset, so every claim is **synchronous** (no
NOMATCH). Tests assert the bijection (0 orphans, 0 unaligned) and that
the claim count equals the MSM note count.

### Modelled quarters→seconds TableMap

Constant tempo per segment (``transition.to`` accelerando / ritardando
ramps are **ignored** for integration — stored only as a Tempo-event
attribute). For each ``tempoMap`` entry (sorted by date) with resolved
bpm ``B`` and beat-length ``L``, the segment's seconds-per-quarter is
``(0.25 / L) * (60 / B)``. Entry dates (ticks) become quarters
(``date / ppq``); the first entry sits at ``q = 0, s = 0``. Segments are
cumulatively integrated (``s_{i+1} = s_i + (q_{i+1} − q_i) · spq_i``); a
final anchor at the score's last quarter extends the last segment. The
result is a ``TableMap(x_values=[q…], y_values=[s…], kind="linear",
source_unit=quarters, target_unit=seconds)``.

Tests assert ``map(0) == 0.0`` and strict monotonic increase. For
**Reger** (single tempo entry, ``beatLength`` 0.0625, bpm 80) the spq is
``(0.25 / 0.0625) · (60 / 80) = 4 · 0.75 = 3.0``, so the map is
``s = 3·q`` and ``map(1) == 3.0`` (2 anchors). For **Beethoven** (7 tempo
entries → 8 anchors) the first segment (bpm 100, beatLength 0.25) has
``spq = 0.6``, so ``map(39.5) == 23.7``; the second entry (bpm 25, same
beat-length, spq 2.4) advances 0.5 quarter to ``map(40.0) == 24.9``.

### Zero-tolerance counts

| Quantity | Beethoven | Reger |
|----------|-----------|-------|
| PPQ | 720 | 720 |
| MSM notes | 251 | 92 |
| ``score:clt1`` events (notes) | 251 | 92 |
| Tempo events (default perf) | 7 | 1 |
| Dynamics events (default perf) | 34 | 11 |
| Articulation events (default perf) | 207 | 80 |
| Asynchrony events (default perf) | 0 | 0 |
| Other markup (default perf) | 0 | 1 (Ornament) |
| ``score:dlt1`` events (notes + markup) | 499 | 185 |
| Alignment notes | 251 | 92 |
| ``perf:cpt1`` / ``perf:dpt1`` events | 251 | 92 |
| Synchronous claims | 251 | 92 |
| NOMATCH claims | 0 | 0 |
| Tempo-map anchors | 8 | 2 |
| Sample rate (Hz) | 44100 | 48000 |
| ``perf:dgt1`` length (frame columns / pixels) | 26469 | 1587 |
| ``perf:dgt1`` events | 0 | 0 |
| Spectrogram ``hopSize`` | 128 | 512 |
| px→seconds ``ScalarMap`` scalar | 128 / 44100 | 512 / 48000 |

The bundle holds **5 timelines** (``score:clt1`` / ``score:dlt1`` /
``perf:cpt1`` / ``perf:dpt1`` / ``perf:dgt1``) and **2 groups**
(``score`` / ``perf``) for both specimens; the ``perf`` group holds 3
timelines. The timeline units across the bundle span all three
``Domain``s: logical, physical, and graphical.

**C-Map spot-check (``TicksToQuarters``):** on ``score:dlt1``, tick
``360`` resolves to ``0.5`` quarters and ``720`` to ``1.0`` (queried via
``timeline.get_timestamp(tick).get_unit(TimeUnit.quarters)``).

**Onset spot-check:** Beethoven note ``nbwxzb1`` has
``milliseconds.date == 828.0190259247195``, so its ``perf:cpt1`` onset
and its claim target coordinate are ``828.0190259247195 / 1000.0``
seconds (the loader divides by 1000; the test pins the same Python
expression, so the IEEE-754 double matches exactly). Its source
coordinate is ``360 / 720 == 0.5`` quarters.

**Note pitch spot-check:** Beethoven ``nbwxzb1`` → pitch ``75``,
pitchname ``"e"``, accidentals ``-1``, octave ``4``, date ``360`` ticks.

**Style-resolution spot-checks:** Beethoven Dynamics ``volume="p"`` →
``48.0``, Tempo ``bpm="Meno mosso."`` → ``100.0``, Articulation
``name.ref="staccato"`` → ``absolute_duration_ms == 160.0`` (and
``noteid`` stripped of its leading ``#``). Reger Dynamics
``volume="dolciss."`` → ``74.0``, Tempo ``bpm="Andantino"`` → ``80.0``.

**Performance selector:** Beethoven
``load(mpr, performance="Curzon_1971_DECCA-SXL6523_audio")`` reaches a
different performance whose inline-numeric bpm values resolve directly —
its ``score:dlt1`` then carries **25** Asynchrony events (vs 0 in the
default) and **123** Tempo events.

## Represent pitch once — validation logic

`test_represent_pitch_once.py` pins the rule that **pitch is represented
exactly once** — by the single most-expressive semantic pitch type the
source *faithfully* supports — and that poorer / derived views are
reached on request, never stored a second time.  The only deterministic
derivations are downhill from SpecificPitch (`GP ← SP → EP`,
`GPC ← SPC → EPC`, and `Pitch → PitchClass`); every other step (above
all `EP → SP`) is inference and is forbidden as a faithful
representation.

**The keystone (struct-preservation in `from_dicts` / `add_events`).**
A carried struct-dict column (e.g. `pitch={"midi_number": 60}`) must
survive ingestion as a real `pa.struct` column — not be JSON-stringified.
The tests assert, on a plain `EventData.from_dicts` and on a
`Timeline.add_events` round-trip:

- a `pitch` dict becomes `struct<midi_number: int64>` (exact type), not a
  `string` column;
- the column carries `b"timetoalign"` metadata with `field_type ==
  "EnharmonicPitchField"` (so the affordance round-trips without relying
  on shape discovery);
- the sub-field order is the paired class's canonical order even when the
  carried dict keys were in another order (`{"alter": -1, "step": "E"}` →
  stored `struct<step, alter>`), because `pa.array` infers struct fields
  alphabetically and the loader reorders to canonical;
- `events.get_field(EnharmonicPitch)[i]` reconstructs the exact scalar.

A heterogeneous sequence of `add_events` calls (a `Note` batch carrying
the `pitch` struct, then a markup/feature batch without it) preserves the
struct column and null-fills the absent rows — the affordance is intact
after the concat.

**The uniform affordance mechanism (`_afforded_fields`).** An EventData
subclass declares `{raw_column: PairedField}`.  `get_fields` promotes the
raw atomic column to a live field via the paired class's `emit()` only
when asked (4th discovery strategy, after metadata / default-name /
shape), and caches it.  Tested invariants:

- `MidiEventData` / `ScoreMidiEventData` declare `{"pitch":
  EnharmonicPitchField}`; their raw `pitch` column is `int64` (uniform
  with the `{midi_number: int64}` view it materialises into);
- `NoteEventData` declares `{"midi": EnharmonicPitchField}` — a
  *non-default* affordance over the raw MIDI number, alongside the
  default `specific_pitch` struct;
- a declared affordance is surfaced by `get_field(<ScalarClass>)`,
  `has_field`, `get_fields_satisfying(PitchLike)`, and `get_pitch_field`;
- the raw column is left untouched (still queryable as a plain int).

**Per-source default pitch type (zero-tolerance affordance pins).**
`get_pitch_field()` returns the single most-expressive default:

| Producer | `get_pitch_field()` type | Also afforded on request | NOT afforded |
|----------|--------------------------|--------------------------|--------------|
| `NoteEventData` (ms3 / music21 / partitura) | `SpecificPitchField` | `EnharmonicPitch` from raw `midi` | a *default* `EnharmonicPitch` struct (represent-once) |
| `MidiEventData` / `ScoreMidiEventData` | `EnharmonicPitchField` | `MidiPitch` display view; `EnharmonicPitchClass` | `SpecificPitch` (inference) |
| Parangonada score / perf timelines | `EnharmonicPitchField` | `MidiPitch` | `SpecificPitch` |
| `PerformancePrecisionLoader` score timeline | `EnharmonicPitchField` | `MidiPitch` | `SpecificPitch` |
| MSM (`MpmLoader`) score timelines | `EnharmonicPitchField` | `SpecificPitchClass` from `pitchname`+`accidentals` | `SpecificPitch` (octave inconsistent with `midi.pitch`) |

**Represent-once assertion.** For `NoteEventData`, exactly one default
semantic pitch field exists (`specific_pitch`, a `SpecificPitchField`);
`get_field(SpecificPitchField)` resolves it, and there is **no**
`midi_pitch` struct column.  The MIDI number lives only as the raw `midi`
int (no `field_type` metadata).

**Scalar↔EventData contract (MIDI).** `MidiEvent.pitch` is annotated
`EnharmonicPitch | None`; the produced `MidiEventData` affords exactly
that field over its `pitch` column, so `get_field(EnharmonicPitch)[i] ==
EnharmonicPitch(midi_number=<pitch[i]>)` for note rows (and the field is
absent / null for Control-Change rows whose `pitch` is null).

**On-request EP from a SP field (both routes).** On `NoteEventData`:

- *conversion route* — `sp_field.convert_to(MidiPitch)[i].midi_number`
  equals the note's MIDI number computed from `(octave+1)*12 + step_semi
  + alter` (the scalar's own `midi_number`); `SpecificPitch.to` does not
  support `EnharmonicPitch` directly, so the test uses the `MidiPitch`
  thin alias as the documented path;
- *raw-column route* — `get_field(EnharmonicPitch)[i].midi_number` equals
  the raw `midi` value, and (zero-tolerance) the two routes agree
  element-wise on the spelled-source fixture.
