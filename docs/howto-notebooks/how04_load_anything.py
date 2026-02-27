# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # How to Load Anything
#
# This notebook is both a **demonstration** and a **conformance test** for every Loader
# in the TimeToAlign! library.  Each section follows the same sequence of calls
# against the *target* API described in this notebook's header.  Where the current
# implementation already supports a call, the cell runs live; where it does not,
# the cell is commented out and annotated with `# TARGET API` so that it serves
# as a specification for the harmonisation effort.
#
# ## Target API (the contract every Loader must satisfy)
#
# ```
# loader = SomeLoader()                       # or SomeLoader.from_file(path)
# loader.load(*paths)                         # Phase 1: ingest
# loader                                      # _repr_html_: metadata + store summary
# loader.store                                # _repr_html_: table IDs, coord ranges, counts
# loader.store.<type_property>                # typed access (e.g. .notes, .measures)
# loader["table_id"]                          # shorthand for loader.store["table_id"]
# loader.create_timeline("id_or_regex")       # single timeline (partial match with warning)
# loader.create_timelines()                   # all timelines
# loader.create_timelines("regex")            # filtered subset
# loader.create_group()                       # full group (if applicable)
# loader.create_group(domain="physical")      # filtered group
# loader.create_bundle()                      # AlignmentBundle (if applicable)
# ```
#
# **Ordering:**  Tested loaders with rich test data come first; niche or
# data-less loaders follow with stubs.

# %% [markdown]
# ## Setup

# %%
from pathlib import Path

from timetoalign import Coordinate

_notebook_dir = Path(".").resolve()
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data"
assert DATA_DIR.is_dir(), f"Data directory not found: {DATA_DIR}"

SCORE_DIR = DATA_DIR / "score"
MIDI_DIR = DATA_DIR / "midi"
VIENNA_DIR = DATA_DIR / "vienna_1x22"

# %% [markdown]
# ---
# ## 1. TSVLoader (ms3-style score TSV)
#
# Loads `.notes.tsv`, `.measures.tsv`, `.chords.tsv`, `.harmonies.tsv` files
# produced by the ms3 library.  The `auto_discover=True` flag picks up companion
# facets automatically.

# %%
from timetoalign.loader.score.tsv import TSVLoader

tsv_dir = SCORE_DIR / "flow_control" / "polyrythm_only"
tsv_notes = sorted(tsv_dir.glob("*polyrhythm_only.notes.tsv"))[0]
tsv_notes.name

# %%
tsv_loader = TSVLoader(auto_discover=True)
tsv_loader.load(tsv_notes)
tsv_loader

# %%
tsv_loader.store

# %%
tsv_loader.store.notes  # ScoreStore typed property -> NoteEventData

# %%
tsv_loader.store.notes.schema  # PyArrow schema

# %%
tsv_loader.store.measures  # MeasureData

# %%
# TARGET API: loader["notes"].to_pandas().head()
# CURRENT: tables live in the store and are accessed by name via __getitem__
tsv_loader.store["notes"].to_pandas().head()

# %%
tsv_tl = tsv_loader.create_timeline()
tsv_tl

# %%
tsv_tl.get_events()

# %%
tsv_tl.get_events().schema

# %%
tsv_tl.get_events(temporal_type="interval", min_coord=0, max_coord=10)

# %%
# TARGET API: tsv_tl.get_events(event_type="Note", min_coord=Coordinate(5, "ticks"),
#     max_coord=Coordinate(20, "ticks"))
# CURRENT: min_coord/max_coord only accept raw floats in the timeline's own unit
tsv_tl.get_events(event_type="Note", min_coord=0, max_coord=10)

# %%
# TARGET API: tsv_tl.get_events(pitch="C4", voice=[1, 2])
# CURRENT: get_events() does not accept arbitrary column filters
# This needs harmonisation.

# %%
# Get first event dynamically - IDs are auto-generated as {timeline_id}:{event_type}:{counter}
first_event_id = tsv_tl.get_events().to_pandas().index[0]
tsv_tl.get_event(first_event_id)

# %%
# TARGET API:
# evt = tsv_tl.get_event("e000001")
# evt_ts = evt.timestamp()
# evt_ts is tsv_tl.get_timestamp_of(evt["id"])  # True
# CURRENT: events are plain dicts, no .timestamp() method;
#          get_timestamp_of() does not exist on Timeline

# %%
tsv_tl.get_timestamp(5)  # coordinate 5 quarters

# %%
# TARGET API: tsv_tl.get_timestamp_at(5)
# CURRENT: method is called get_timestamp(), not get_timestamp_at()
# The _at suffix exists on TimelineGroup but not on Timeline -- inconsistent.

# %%
tsv_events_at = tsv_tl.get_events_at(5)
tsv_events_at

# %%
tsv_tl.get_timestamps()

# %%
# TARGET API: tsv_tl.get_timestamps_of(events)
# CURRENT: get_timestamps_of() does not exist

# %%
tsv_tl.get_timestamp_table()


# %% [markdown]
# ---
# ## 2. PartituraLoader (MusicXML via partitura)
#
# Parses MusicXML (and MIDI) files using the `partitura` library.

# %%
from timetoalign.loader.score.partitura import PartituraLoader

partitura_file = (
    SCORE_DIR / "flow_control" / "out_of_the_flow_experience-flow_only.musicxml"
)
partitura_file.name

# %%
partitura_loader = PartituraLoader(silence_warnings=True)
partitura_loader.load(partitura_file)
partitura_loader

# %%
partitura_loader.store

# %%
partitura_loader.store.notes

# %%
partitura_loader.store.notes.schema

# %%
partitura_loader.store.measures

# %%
partitura_loader.store["notes"].to_pandas().head()

# %%
partitura_tl = partitura_loader.create_timeline()
partitura_tl

# %%
partitura_tl.get_events()

# %%
partitura_tl.get_events(temporal_type="interval", min_coord=0, max_coord=20)

# %%
partitura_tl.get_timestamp(10)

# %%
partitura_tl.get_events_at(0)

# %%
partitura_tl.get_timestamps()

# %%
partitura_tl.get_timestamp_table()


# %% [markdown]
# ---
# ## 3. Music21Loader (MusicXML/MEI via music21)
#
# Parses MusicXML and MEI files using the `music21` library.

# %%
from timetoalign.loader.score.music21 import Music21Loader

# Use a small MEI file
music21_file = (
    SCORE_DIR
    / "beethoven_op18-4iv_multimodal"
    / "op18_no4_mov4_flow"
    / "op18_no4_mov4_flow.mei"
)
music21_file.name

# %%
music21_loader = Music21Loader()
music21_loader.load(music21_file)
music21_loader

# %%
music21_loader.store

# %%
music21_loader.store.notes

# %%
music21_loader.store.notes.schema

# %%
music21_loader.store.measures

# %%
music21_tl = music21_loader.create_timeline()
music21_tl

# %%
music21_tl.get_events()

# %%
music21_tl.get_events(temporal_type="interval", min_coord=0, max_coord=20)

# %%
music21_tl.get_timestamp(10)

# %%
music21_tl.get_timestamps()


# %% [markdown]
# ---
# ## 4. MeasureMapLoader (.mm.json)
#
# Parses MeasureMap JSON files describing measure boundaries, time signatures,
# and flow control.

# %%
from timetoalign.loader.score.measuremap import MeasureMapLoader

mm_file = (
    SCORE_DIR
    / "bruckner5_scherzo"
    / "hauptstimme"
    / "Bruckner_WAB.105_3a_Scherzo.mm.json"
)
mm_file.name

# %%
mm_loader = MeasureMapLoader()
mm_loader.load(mm_file)
mm_loader

# %%
mm_loader.store

# %%
mm_loader.store.measures

# %%
mm_loader.store["measures"].to_pandas().head()

# %%
mm_tl = mm_loader.create_timeline()
mm_tl

# %%
mm_tl.get_events()

# %%
mm_loader.compute_default_traversal()[:20]  # first 20 measures of the traversal

# %%
mm_loader.get_traversal_summary()


# %% [markdown]
# ---
# ## 5. PerformanceMidiLoader (performance MIDI via mido)
#
# Low-level MIDI parsing using `mido`.  Pairs note_on/note_off events,
# handles running status, and extracts control changes.

# %%
from timetoalign.loader.midi.performance import PerformanceMidiLoader

perf_midi_file = MIDI_DIR / "performance" / "rachmaninoff_perf.mid"
perf_midi_file.name

# %%
perf_midi_loader = PerformanceMidiLoader()
perf_midi_loader.load(perf_midi_file)
perf_midi_loader

# %%
perf_midi_loader.store

# %%
perf_midi_loader.store.notes  # MidiStore typed property -> MidiEventData

# %%
perf_midi_loader.store.notes.schema

# %%
perf_midi_loader.store["notes"].to_pandas().head()

# %%
perf_midi_tl = perf_midi_loader.create_timeline()
perf_midi_tl

# %%
perf_midi_tl.get_events()

# %%
perf_midi_tl.get_events(temporal_type="interval")

# %%
perf_midi_tl.get_timestamp(0.5)

# %%
perf_midi_tl.get_timestamps()


# %% [markdown]
# ---
# ## 6. ScoreMidiLoader (score MIDI via partitura)
#
# Parses score-like MIDI files using `partitura` for structural information
# (parts, voices, time signatures).

# %%
from timetoalign.loader.midi.score import ScoreMidiLoader

score_midi_file = MIDI_DIR / "score" / "beethoven_mtd.mid"
score_midi_file.name

# %%
score_midi_loader = ScoreMidiLoader()
score_midi_loader.load(score_midi_file)
score_midi_loader

# %%
score_midi_loader.store

# %%
score_midi_loader.store.notes

# %%
score_midi_loader.store.notes.schema

# %%
score_midi_loader.store["notes"].to_pandas().head()

# %%
score_midi_tl = score_midi_loader.create_timeline()
score_midi_tl

# %%
score_midi_tl.get_events()

# %%
score_midi_tl.get_timestamp(0)

# %%
score_midi_tl.get_timestamps()


# %% [markdown]
# ---
# ## 7. TabularLoaders (CsvLoader, TsvLoader, Ms3Loader, LabLoader)
#
# Generic tabular loaders with configurable column mapping.
# `Ms3Loader` is pre-configured for ms3-style annotation TSVs.

# %% [markdown]
# ### 7a. Ms3Loader

# %%
from timetoalign.loader.tabular.csv import Ms3Loader

# Use an ms3-style annotation TSV (unfolded notes)
ms3_file = (
    SCORE_DIR
    / "flow_control"
    / "polyrythm_only"
    / "out_of_the_flow_experience-polyrhythm_only.notes.tsv"
)
ms3_file.name

# %%
ms3_loader = Ms3Loader()
ms3_loader.load(ms3_file)
ms3_loader

# %%
ms3_loader.store

# %%
ms3_loader.events  # EventData (generic, not ScoreEventData)

# %%
ms3_loader.events.schema

# %%
ms3_loader.events.to_pandas().head()

# %%
ms3_tl = ms3_loader.create_timeline()
ms3_tl

# %%
ms3_tl.get_events()

# %%
ms3_tl.get_timestamps()

# %% [markdown]
# ### 7b. CsvLoader

# %%
from timetoalign.loader.tabular.csv import CsvLoader

# MTD alignment CSV
csv_file = (
    DATA_DIR
    / "beethoven_Op106-01"
    / "MTD"
    / "data_ALIGNMENT"
    / "MTD0951_Beethoven_Op106-01.csv"
)
csv_file.name

# %%
csv_loader = CsvLoader()
csv_loader.load(csv_file)
csv_loader

# %%
csv_loader.events

# %%
csv_loader.events.schema

# %%
csv_loader.events.to_pandas().head()

# %%
csv_tl = csv_loader.create_timeline()
csv_tl

# %% [markdown]
# ### 7c. LabLoader
#
# Parses headerless tab-separated files in Audacity/Praat label format.
# **No `.lab` test data currently exists in the test suite -- this is a gap.**

# %%
from timetoalign.loader.physical.audio import AudioLoader

# %%
from timetoalign.loader.tabular.csv import LabLoader

# TARGET: LabLoader needs test data (.lab files) added to tests/data/
# lab_loader = LabLoader()
# lab_loader.load("some_file.lab")
# lab_loader

# %% [markdown]
# ---
# ## 8. AudioLoader
#
# Reads audio file metadata (sample rate, channels, duration) without loading
# the full waveform.  Produces a `DiscretePhysicalTimeline`.
#
# **Note:** `AudioLoader` is a standalone class, not a subclass of `Loader`.
# As of H2, it exposes the universal API surface (`create_timeline()`,
# `create_timelines()`, `from_file()`, `_repr_html_()`).  Formal subclassing
# of `ManifestLoader` is deferred (H2.2b).

# %%
audio_file = DATA_DIR / "supra" / "midi" / "fd660zf8362.mp3"
audio_file.name

# %%
audio_loader = AudioLoader()
audio_loader.load(audio_file)
audio_loader

# %%
# INCONSISTENCY: AudioLoader has no .store property
# It uses .audio_info instead
audio_loader.audio_info

# %%
print(f"Sample rate: {audio_loader.sample_rate}")
print(f"Channels: {audio_loader.channels}")
print(f"Duration: {audio_loader.duration_seconds:.2f}s")
print(f"Samples: {audio_loader.n_samples}")

# %%
# RESOLVED: AudioLoader now uses .create_timeline() like other loaders
audio_tl = audio_loader.create_timeline()
audio_tl


# %% [markdown]
# ---
# ## 9. EepNotesLoader (EEP .notes alignment files)
#
# Subclass of `CsvLoader` for whitespace-separated EEP `.notes` files
# containing note-level performance alignments.

# %%
from timetoalign.loader.physical.eep_notes import EepNotesLoader

eep_file = (
    SCORE_DIR
    / "beethoven_op18-4iv_multimodal"
    / "StringQuartetEEP_I_Exaggerated"
    / "StringQuartetEEP_I_Exaggerated_align_cello.notes"
)
eep_file.name

# %%
eep_loader = EepNotesLoader()
eep_loader.load(eep_file)
eep_loader

# %%
eep_loader.store

# %%
eep_loader.events

# %%
eep_loader.events.schema

# %%
eep_loader.events.to_pandas().head()

# %%
eep_tl = eep_loader.create_timeline()
eep_tl

# %%
eep_tl.get_events()

# %%
eep_tl.get_events(temporal_type="interval")

# %%
eep_tl.get_timestamp(1.0)

# %%
eep_tl.get_timestamps()


# %% [markdown]
# ---
# ## 10. RepoVizzLoader (RepoVizz sensor CSV)
#
# A `ManifestLoader` for 2-line CSV files from the RepoVizz platform
# (MoCap/sensor data).  Returns metadata (frame rate, samples), not events.
#
# **Note:** `RepoVizzLoader` is a `ManifestLoader`, not an `EventLoader`.
# It has no `.store` or `.events` -- only `.create_timeline()`.

# %%
from timetoalign.loader.physical.repovizz import RepoVizzLoader

repovizz_dir = (
    SCORE_DIR / "beethoven_op18-4iv_multimodal" / "StringQuartetEEP_I_Mechanical"
)
repovizz_files = sorted(repovizz_dir.glob("*.csv"))[:1]  # just one sensor file
repovizz_files[0].name if repovizz_files else "NO CSV FILES FOUND"

# %%
if repovizz_files:
    repovizz_loader = RepoVizzLoader()
    repovizz_loader.load(repovizz_files[0])
    repovizz_loader

# %%
if repovizz_files:
    print(f"Frame rate: {repovizz_loader.frame_rate}")
    print(f"Samples: {repovizz_loader.n_samples}")
    print(f"Duration: {repovizz_loader.duration_seconds:.2f}s")

# %%
# RESOLVED: RepoVizzLoader now uses .create_timeline() like other loaders
if repovizz_files:
    repovizz_tl = repovizz_loader.create_timeline()
    repovizz_tl


# %% [markdown]
# ---
# ## 11. GraphicalLoader (images / PDF pages)
#
# Factory class for building graphical timelines from image sources and
# path segments.
#
# **Note:** `GraphicalLoader` is a standalone factory, not a subclass of
# `Loader`.  It uses `.build()` instead of `.create_timeline()`.
# As of H2, it is API-conformant but retains the builder pattern (H2.2b).

# %%
from timetoalign.loader.graphical.loader import GraphicalLoader

thoresen_dir = DATA_DIR.parent / "tests" / "alignment" / "data" / "thoresen"
# Fall back to the regular test data path
if not thoresen_dir.is_dir():
    thoresen_dir = (
        Path(_notebook_dir).parent.parent / "tests" / "alignment" / "data" / "thoresen"
    )

thoresen_images = (
    sorted(thoresen_dir.glob("*.jpeg"))[:2] if thoresen_dir.is_dir() else []
)
[img.name for img in thoresen_images] if thoresen_images else "NO IMAGES FOUND"

# %%
if thoresen_images:
    graphical_loader = GraphicalLoader()
    src_idx = graphical_loader.add_image(thoresen_images[0])
    graphical_loader.add_horizontal_segment(src_idx, x0=0, x1=500, y=100)
    graphical_loader

# %%
if thoresen_images:
    graphical_store = graphical_loader.build()
    graphical_store

# %%
# INCONSISTENCY: GraphicalLoader has no .create_timeline() method
# It uses .build() -> GraphicalStore, which is not a Timeline
# TARGET API: graphical_loader.create_timeline()  # returns a CGT


# %% [markdown]
# ---
# ## 12. IIIFManifestLoader (IIIF JSON manifests)
#
# Parses IIIF Presentation API manifests to extract image dimensions
# and metadata for graphical timeline construction.
#
# **Note:** Standalone class, not a `Loader` subclass.

# %%
from timetoalign.loader.graphical.iiif import IIIFManifestLoader

iiif_file = DATA_DIR / "supra" / "image" / "ifff_manifest.json"
iiif_file.name

# %%
iiif_loader = IIIFManifestLoader()
iiif_loader.load(iiif_file)
iiif_loader

# %%
print(f"Label: {iiif_loader.label}")
print(f"Canvases: {iiif_loader.n_canvases}")
print(f"Dimensions: {iiif_loader.dimensions}")

# %%
iiif_tl = iiif_loader.create_timeline()
iiif_tl

# %%
# INCONSISTENCY: IIIFManifestLoader has create_timeline() but no .store
# TARGET API: iiif_loader.store  # should exist


# %% [markdown]
# ---
# ## 13. ATONLoader (piano roll analysis)
#
# Parses ATON format files describing piano roll hole positions.
#
# **No ATON test data currently exists in the test suite.**

# %%
from timetoalign.loader.format.json import JsonLoader

# %%
from timetoalign.loader.graphical.aton import ATONLoader

# TARGET: ATONLoader needs test data (.aton files) added to tests/data/
# aton_loader = ATONLoader()
# aton_loader.load("some_file.aton")
# aton_loader

# %%
# INCONSISTENCY: ATONLoader is standalone, not a Loader subclass
# TARGET API: aton_loader.store  # should exist
# TARGET API: aton_loader.create_timeline()  # exists, good


# %% [markdown]
# ---
# ## 14. JsonLoader (generic JSON normaliser)
#
# Configurable JSON loader that flattens nested structures into PyArrow tables.
# Base class for format-specific loaders like `TiliaJsonLoader`.

# %%
# Use the TiLiA JSON as a generic JSON example
json_file = SCORE_DIR / "bruckner5_scherzo" / "harnoncourt" / "Bruckner5_Scherzo.json"
json_file.name if json_file.exists() else "NOT FOUND"

# %%
if json_file.exists():
    json_loader = JsonLoader()
    json_loader.load(json_file)
    json_loader

# %%
if json_file.exists():
    json_loader.store

# %%
if json_file.exists():
    json_loader.keys()

# %%
# JsonLoader has .get_table() -- good, this should be on all loaders
if json_file.exists() and json_loader.keys():
    first_key = json_loader.keys()[0]
    json_loader.get_table(first_key)


# %% [markdown]
# ---
# ## 15. TiliaJsonLoader (TiLiA .tla/.json analysis)
#
# Subclass of `JsonLoader` specialised for TiLiA timeline analysis exports.
# Produces timelines, groups, and alignment bundles.
#
# **This is the most feature-complete loader in terms of the target API.**

# %%
from timetoalign.loader.alignment.tilia import TiliaJsonLoader

tilia_file = SCORE_DIR / "bruckner5_scherzo" / "harnoncourt" / "Bruckner5_Scherzo.tla"
tilia_file.name

# %%
tilia_loader = TiliaJsonLoader()
tilia_loader.load(tilia_file)
tilia_loader

# %%
tilia_loader.store

# %%
tilia_loader.store.keys()  # TiliaDictStore

# %%
tilia_loader.timeline_ids

# %%
tilia_loader.timeline_specs

# %%
# TiliaJsonLoader has create_timeline, create_timelines, create_group -- good!
tilia_tls = tilia_loader.create_timelines()
{i: tl for i, tl in enumerate(tilia_tls)}

# %%
tilia_tl0 = tilia_loader.create_timeline(tilia_loader.timeline_ids[0])
tilia_tl0

# %%
tilia_tl0.get_events()

# %%
tilia_tl0.get_timestamp(10)

# %%
tilia_group = tilia_loader.create_group()
tilia_group

# %%
# TARGET API: tilia_group["tl_id"]
# CURRENT: TimelineGroup has no __getitem__
tilia_group.get_timeline(tilia_group.timeline_ids[0])

# %%
tilia_group.get_timestamp_at(10, tilia_group.timeline_ids[0])

# %%
tilia_group.get_timestamp_table()

# %%
# TiliaJsonLoader also has create_alignment_bundle()
tilia_bundle = tilia_loader.create_alignment_bundle()
tilia_bundle

# %%
tilia_bundle.get_match_claims()

# %%
# TARGET API: tilia_bundle.get_matchstamp_table()
# CURRENT: does not exist


# %% [markdown]
# ---
# ## 16. MatchfileLoader (Vienna .match files)
#
# Parses Vienna 4x22 corpus `.match` files via `partitura`.
# Builds a shared score timeline, per-performance timelines, and `MatchClaim`s.
#
# **Note:** Standalone class, not a subclass of `AlignmentLoader`.
# As of H2, it exposes the universal API surface.  Formal subclassing deferred (H2.2b).

# %%
from timetoalign.loader.alignment.matchfile import MatchfileLoader

match_file = VIENNA_DIR / "Chopin_op10_no3_p22.match"
match_file.name

# %%
match_loader = MatchfileLoader()
match_loader.load(match_file)
match_loader

# %%
# INCONSISTENCY: MatchfileLoader has no .store property
# TARGET API: match_loader.store  # should exist with DictStore

# %%
match_tls = match_loader.create_timelines()
{tl.id: (tl.n_children, tl.n_events) for tl in match_tls}

# %%
match_tl_score = match_loader.create_timeline("score")
match_tl_score

# %%
match_tl_score.get_events()

# %%
match_tl_score.get_timestamp(10)

# %%
# TARGET API: match_loader.create_group()
# CURRENT: MatchfileLoader has no create_group()

# %%
match_bundle = match_loader.create_alignment_bundle()
match_bundle

# %%
match_claims = match_bundle.get_match_claims()
len(match_claims)

# %%
match_claims[0] if match_claims else "No claims"

# %%
match_claims[0].get_matchstamp() if match_claims else "No claims"

# %%
# TARGET API: match_bundle.get_matchstamp_table()
# CURRENT: does not exist

# %%
# TARGET API: match_bundle.get_timelines(["score", perf_id])
# CURRENT: does not exist; use get_timeline() one at a time

# %%
# TARGET API:
# tl_a, tl_b = match_bundle.get_timelines(["score", perf_id])
# evts_a, evts_b = tl_a.get_events(), tl_b.get_events()
# new_claims = match_bundle.create_match_claims(evts_a.slice(0, 1), evts_b.slice(0, 1))
# CURRENT: create_match_claims() does not exist on AlignmentBundle


# %% [markdown]
# ---
# ---
# ## Summary of API Inconsistencies
#
# The following table summarises the inconsistencies found across all loaders.
# Each row represents a gap between the target API and the current implementation.
#
# | # | Issue | Affected Loaders | Severity |
# |---|-------|------------------|----------|
# | 1 | ~~**No common base class**~~ | ~~AudioLoader, GraphicalLoader, IIIFManifestLoader, ATONLoader, MatchfileLoader~~ | ~~HIGH~~ RESOLVED (H2) |
# | 2 | ~~`to_timeline()` vs `create_timeline()`~~ | ~~AudioLoader, RepoVizzLoader~~ | RESOLVED (H2) |
# | 3 | ~~**No `.store` property**~~ | ~~AudioLoader, GraphicalLoader, IIIFManifestLoader, ATONLoader, MatchfileLoader~~ | ~~HIGH~~ RESOLVED (H2) |
# | 4 | ~~**No `__getitem__` on Loader**~~ | ~~All Loader subclasses~~ | ~~HIGH~~ RESOLVED (H2) |
# | 5 | ~~**No `create_timelines()` on base**~~ | ~~All except TiliaJsonLoader, MatchfileLoader~~ | ~~HIGH~~ RESOLVED (H2) |
# | 6 | ~~**No `create_group()` on base**~~ | ~~All except TiliaJsonLoader~~ | ~~HIGH~~ RESOLVED (H2) |
# | 7 | ~~**No `create_bundle()` on base**~~ | ~~All loaders~~ | ~~HIGH~~ RESOLVED (H2) |
# | 8 | **`get_timestamp()` vs `get_timestamp_at()`** | Timeline vs TimelineGroup naming | MEDIUM |
# | 9 | **No `get_timestamp_of(event_id)` on Timeline** | All timelines | HIGH |
# | 10 | **No `get_timestamps_of(events)` on Timeline** | All timelines | HIGH |
# | 11 | **Events are plain dicts, no `.timestamp()` method** | All timelines | HIGH |
# | 12 | **No Coordinate-unit conversion in `get_events()`** | All timelines | MEDIUM |
# | 13 | **No arbitrary column filters in `get_events()`** | All timelines | MEDIUM |
# | 14 | **No `__getitem__` on TimelineGroup** | All groups | MEDIUM |
# | 15 | **No `get_events()` on TimelineGroup** | All groups | MEDIUM |
# | 16 | **No `get_timestamp_of()` on TimelineGroup** | All groups | HIGH |
# | 17 | **No `get_timestamps_of()` on TimelineGroup** | All groups | HIGH |
# | 18 | **No `get_matchstamp_table()` on AlignmentBundle** | All bundles | HIGH |
# | 19 | **No `get_timelines()` (plural) on AlignmentBundle** | All bundles | MEDIUM |
# | 20 | **No `create_match_claims()` factory on AlignmentBundle** | All bundles | HIGH |
# | 21 | **`bundle` module name deprecated** | loader/bundle.py, loader/score/bundle.py, loader/midi/bundle.py | MEDIUM |
# | 22 | **"filtered" and "unified_timestamps" methods** | Timeline, TimelineGroup | HIGH |
# | 23 | **No `summary()` on base EventStore** | EventStore base class | MEDIUM |
# | 24 | **No partial/regex ID matching in `create_timeline()`** | All loaders | HIGH |
# | 25 | ~~**No `_repr_html_` on Loader**~~ | ~~Most loaders (except those with diagrams)~~ | ~~MEDIUM~~ RESOLVED (H2) |
# | 26 | **LabLoader has no test data** | LabLoader | LOW |
# | 27 | **ATONLoader has no test data** | ATONLoader | LOW |
# | 28 | **Stores not in `store` module** | ScoreStore in bundle.py, MidiStore in bundle.py | MEDIUM |
# | 29 | **EventData subclasses not in `events` module** | ScoreEventData in store.py, MidiEventData in store.py | MEDIUM |
# | 30 | **No `id_map` parameter on `load()` or `from_file()`** | All loaders | MEDIUM |
