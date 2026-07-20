# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# ---
# ## 1. TSVLoader (ms3-style score TSV)
#
# Loads `.notes.tsv`, `.measures.tsv`, `.chords.tsv`, `.harmonies.tsv` files
# produced by the ms3 library.  The `auto_discover=True` flag picks up companion
# facets automatically.

# %% [markdown]
# # How to Load Anything
#
# This notebook demonstrates the unified Loader API in the Time To Align! library.
# Each section exercises a loader following the same pattern:
#
# 1. **Loading**: `loader.load(*paths)` or `Loader.from_file(path)`
# 2. **Inspection**: `loader`, `loader.store`, `loader.store.<type_property>`
# 3. **Timeline creation**: `create_timeline()`, `create_timelines()`
# 4. **Event access**: `get_events()`, `get_event(id)`, `get_events_at(coord)`
# 5. **Timestamps**: `get_timestamp()`, `get_timestamp_of(id)`, `get_timestamps_of(ids)`
# 6. **Groups** (where applicable): `create_group()`, group methods
# 7. **Bundles** (where applicable): `create_alignment_bundle()`, `create_match_claims()`

# %% [markdown]
# ## Setup

# %%
from timetoalign.testdata import DATA_DIR, ensure_data

ensure_data("score", "midi", "vienna_1x22", "supra", "tabular", "thoresen")

SCORE_DIR = DATA_DIR / "score"
MIDI_DIR = DATA_DIR / "midi"
VIENNA_DIR = DATA_DIR / "vienna_1x22"

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
tsv_loader.store["notes"].to_dataframe().head()

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
tsv_tl.get_events(event_type="Note", min_coord=0, max_coord=10)

# %%
first_event = next(iter(tsv_tl.get_events()))
first_event_id = first_event["id"]
first_event_id

# %%
tsv_tl.get_event(first_event_id)

# %%
tsv_tl.get_timestamp_of(first_event_id)

# %%
tsv_tl.get_timestamp_at(5)

# %%
tsv_events_at = tsv_tl.get_events_at(5)
tsv_events_at

# %%
tsv_tl.to_dataframe()

# %%
tsv_event_ids = [evt["id"] for evt in list(tsv_tl.get_events())[:5]]
tsv_tl.get_timestamps_of(tsv_event_ids)

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
partitura_loader.store["notes"].to_dataframe().head()

# %%
partitura_tl = partitura_loader.create_timeline()
partitura_tl

# %%
partitura_tl.get_events()

# %%
partitura_tl.get_events().schema

# %%
partitura_tl.get_events(temporal_type="interval", min_coord=0, max_coord=20)

# %%
part_first_event = next(iter(partitura_tl.get_events()))
part_first_event_id = part_first_event["id"]
partitura_tl.get_event(part_first_event_id)

# %%
partitura_tl.get_timestamp_of(part_first_event_id)

# %%
partitura_tl.get_timestamp_at(10)

# %%
partitura_tl.get_events_at(0)

# %%
partitura_tl.to_dataframe()

# %%
part_event_ids = [evt["id"] for evt in list(partitura_tl.get_events())[:5]]
partitura_tl.get_timestamps_of(part_event_ids)

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
music21_tl.get_events().schema

# %%
music21_tl.get_events(temporal_type="interval", min_coord=0, max_coord=20)

# %%
m21_first_event = next(iter(music21_tl.get_events()))
m21_first_event_id = m21_first_event["id"]
music21_tl.get_event(m21_first_event_id)

# %%
music21_tl.get_timestamp_of(m21_first_event_id)

# %%
music21_tl.get_timestamp_at(10)

# %%
music21_tl.get_events_at(0)

# %%
music21_tl.to_dataframe()

# %%
m21_event_ids = [evt["id"] for evt in list(music21_tl.get_events())[:5]]
music21_tl.get_timestamps_of(m21_event_ids)

# %%
music21_tl.get_timestamp_table()


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
    / "beethoven_op18-4iv_multimodal"
    / "ABC"
    / "n04op18-4_04.measures.mm.json"
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
mm_loader.store["measures"].to_dataframe().head()

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
perf_midi_loader.store["notes"].to_dataframe().head()

# %%
perf_midi_tl = perf_midi_loader.create_timeline()
perf_midi_tl

# %%
perf_midi_tl.get_events()

# %%
perf_midi_tl.get_events().schema

# %%
perf_midi_tl.get_events(temporal_type="interval")

# %%
perf_midi_first_event = next(iter(perf_midi_tl.get_events()))
perf_midi_first_event_id = perf_midi_first_event["id"]
perf_midi_tl.get_event(perf_midi_first_event_id)

# %%
perf_midi_tl.get_timestamp_of(perf_midi_first_event_id)

# %%
perf_midi_tl.get_timestamp_at(0.5)

# %%
perf_midi_tl.get_events_at(0)

# %%
perf_midi_tl.to_dataframe()

# %%
perf_midi_event_ids = [evt["id"] for evt in list(perf_midi_tl.get_events())[:5]]
perf_midi_tl.get_timestamps_of(perf_midi_event_ids)

# %%
perf_midi_tl.get_timestamp_table()


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
score_midi_loader.store["notes"].to_dataframe().head()

# %%
score_midi_tl = score_midi_loader.create_timeline()
score_midi_tl

# %%
score_midi_tl.get_events()

# %%
score_midi_tl.get_events().schema

# %%
score_midi_tl.get_events(temporal_type="interval", min_coord=0, max_coord=10)

# %%
score_midi_first_event = next(iter(score_midi_tl.get_events()))
score_midi_first_event_id = score_midi_first_event["id"]
score_midi_tl.get_event(score_midi_first_event_id)

# %%
score_midi_tl.get_timestamp_of(score_midi_first_event_id)

# %%
score_midi_tl.get_timestamp_at(0)

# %%
score_midi_tl.get_events_at(0)

# %%
score_midi_tl.to_dataframe()

# %%
score_midi_event_ids = [evt["id"] for evt in list(score_midi_tl.get_events())[:5]]
score_midi_tl.get_timestamps_of(score_midi_event_ids)

# %%
score_midi_tl.get_timestamp_table()


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
ms3_loader.events.to_dataframe().head()

# %%
ms3_tl = ms3_loader.create_timeline()
ms3_tl

# %%
ms3_tl.get_events()

# %%
ms3_tl.get_events().schema

# %%
ms3_first_event = next(iter(ms3_tl.get_events()))
ms3_first_event_id = ms3_first_event["id"]
ms3_tl.get_event(ms3_first_event_id)

# %%
ms3_tl.get_timestamp_of(ms3_first_event_id)

# %%
ms3_tl.get_timestamp_at(0)

# %%
ms3_tl.to_dataframe()

# %%
ms3_event_ids = [evt["id"] for evt in list(ms3_tl.get_events())[:5]]
ms3_tl.get_timestamps_of(ms3_event_ids)

# %%
ms3_tl.get_timestamp_table()

# %% [markdown]
# ### 7b. CsvLoader

# %%
from timetoalign.loader.tabular.csv import CsvLoader

csv_file = DATA_DIR / "tabular" / "test_events.csv"
csv_file.name

# %%
csv_loader = CsvLoader()
csv_loader.load(csv_file)
csv_loader

# %%
csv_loader.events.to_dataframe()

# %%
csv_loader.events.table.to_pandas()

# %%
csv_loader.events.schema

# %%
csv_loader.events.to_dataframe().head()

# %%
csv_tl = csv_loader.create_timeline()
csv_tl

# %%
csv_tl.get_events()

# %%
csv_tl.get_events().schema

# %%
csv_first_event = next(iter(csv_tl.get_events()))
csv_first_event_id = csv_first_event["id"]
csv_tl.get_event(csv_first_event_id)

# %%
csv_tl.get_timestamp_of(csv_first_event_id)

# %%
csv_tl.get_timestamp_at(0)

# %%
csv_tl.to_dataframe()

# %%
csv_event_ids = [evt["id"] for evt in list(csv_tl.get_events())[:5]]
csv_tl.get_timestamps_of(csv_event_ids)

# %%
csv_tl.get_timestamp_table()

# %% [markdown]
# ### 7c. LabLoader
#
# Parses headerless tab-separated files in Audacity/Praat label format.
# **No `.lab` test data currently exists in the test suite -- this is a gap.**

# %%
from timetoalign.loader.physical.audio import AudioLoader

# %%
# LabLoader example (test data in tests/data/fixtures/lab/)
# from timetoalign.loader.tabular.csv import LabLoader
# lab_loader = LabLoader()
# lab_loader.load("regions.lab")
# lab_loader

# %% [markdown]
# ---
# ## 8. AudioLoader
#
# Reads audio file metadata (sample rate, channels, duration) without loading
# the full waveform.  Produces a `DiscretePhysicalTimeline`.

# %%
audio_file = DATA_DIR / "supra" / "midi" / "fd660zf8362.mp3"
audio_file.name

# %%
audio_loader = AudioLoader()
audio_loader.load(audio_file)
audio_loader

# %%
audio_loader.audio_info

# %%
print(f"Sample rate: {audio_loader.sample_rate}")
print(f"Channels: {audio_loader.channels}")
print(f"Duration: {audio_loader.duration_seconds:.2f}s")
print(f"Samples: {audio_loader.n_samples}")

# %%
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
eep_loader.events.to_dataframe().head()

# %%
eep_tl = eep_loader.create_timeline()
eep_tl

# %%
eep_tl.get_events()

# %%
eep_tl.get_events().schema

# %%
eep_tl.get_events(temporal_type="interval")

# %%
eep_first_event = next(iter(eep_tl.get_events()))
eep_first_event_id = eep_first_event["id"]
eep_tl.get_event(eep_first_event_id)

# %%
eep_tl.get_timestamp_of(eep_first_event_id)

# %%
eep_tl.get_timestamp_at(1.0)

# %%
eep_tl.get_events_at(1.0)

# %%
eep_tl.to_dataframe()

# %%
eep_event_ids = [evt["id"] for evt in list(eep_tl.get_events())[:5]]
eep_tl.get_timestamps_of(eep_event_ids)

# %%
eep_tl.get_timestamp_table()


# %% [markdown]
# ---
# ## 10. RepoVizzLoader (RepoVizz sensor CSV)
#
# A `ManifestLoader` for 2-line CSV files from the RepoVizz platform
# (MoCap/sensor data).  Returns metadata (frame rate, samples), not events.
#
# **Note:** `RepoVizzLoader` is a `ManifestLoader`, not a `Loader`.
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
if repovizz_files:
    repovizz_tl = repovizz_loader.create_timeline()
    repovizz_tl


# %% [markdown]
# ---
# ## 11. GraphicalLoader (images / PDF pages)
#
# Factory class for building graphical timelines from image sources and
# path segments. Uses a builder pattern: `.add_image()`, `.add_horizontal_segment()`,
# then `.store` to produce a `GraphicalStore`.

# %%
from timetoalign.loader.graphical.loader import GraphicalLoader

thoresen_dir = DATA_DIR / "thoresen"
thoresen_images = sorted(thoresen_dir.glob("*.jpeg"))[:2]
[img.name for img in thoresen_images] if thoresen_images else "NO IMAGES FOUND"

# %%
if thoresen_images:
    graphical_loader = GraphicalLoader()
    src_idx = graphical_loader.add_image(thoresen_images[0])
    graphical_loader.add_horizontal_segment(src_idx, x0=0, x1=500, y=100)
    graphical_loader

# %%
if thoresen_images:
    graphical_store = graphical_loader.store
    graphical_store


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


# %% [markdown]
# ---
# ## 13. ATONLoader (piano roll analysis)
#
# Parses ATON format files describing piano roll hole positions.

# %%
from timetoalign.loader.format.json import JsonLoader

# %%
# ATONLoader example (test data in tests/data/fixtures/aton/)
# from timetoalign.loader.graphical.aton import ATONLoader
# aton_loader = ATONLoader()
# aton_loader.load("minimal.aton")
# aton_loader


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

tilia_file = SCORE_DIR / "bruckner5_scherzo" / "harnoncourt" / "Bruckner5_Scherzo.json"
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
tilia_tl0 = tilia_loader.create_timeline(uid=tilia_loader.timeline_ids[0])
tilia_tl0

# %%
tilia_tl0.get_events()

# %%
tilia_tl0.get_events().schema

# %%
tilia_first_event = next(iter(tilia_tl0.get_events()))
tilia_first_event_id = tilia_first_event["id"]
tilia_tl0.get_event(tilia_first_event_id)

# %%
tilia_tl0.get_timestamp_of(tilia_first_event_id)

# %%
tilia_tl0.get_timestamp_at(10)

# %%
tilia_tl0.get_events_at(10)

# %%
tilia_event_ids = [evt["id"] for evt in list(tilia_tl0.get_events())[:5]]
tilia_tl0.get_timestamps_of(tilia_event_ids)

# %%
tilia_tl0.get_timestamp_table()

# %% [markdown]
# ### TiliaJsonLoader: TimelineGroup

# %%
tilia_group = tilia_loader.create_group()
tilia_group

# %%
len(tilia_group)  # number of timelines

# %%
tilia_group[tilia_group.timeline_ids[0]]

# %%
tilia_group.get_timeline(tilia_group.timeline_ids[0])

# %%
tilia_group.get_timestamp_at(10, tilia_group.timeline_ids[0])

# %%
tilia_group.get_events()

# %%
tilia_group.get_timestamp_of(tilia_first_event_id)

# %%
tilia_group.get_timestamps_of(tilia_event_ids)

# %%
tilia_group.get_timestamp_table()

# %% [markdown]
# ### TiliaJsonLoader: AlignmentBundle with MatchClaim Creation

# %%
tilia_bundle = tilia_loader.create_alignment_bundle()
tilia_bundle

# %%
tilia_existing_claims = tilia_bundle.get_match_claims()
len(tilia_existing_claims)

# %%
if len(tilia_bundle.timeline_ids) >= 2:
    tilia_tl_a, tilia_tl_b = tilia_bundle.get_timelines(tilia_bundle.timeline_ids[:2])
    print(f"Timeline A: {tilia_tl_a.id}, Timeline B: {tilia_tl_b.id}")

# %%
# Create MatchClaims by pairing events from two timelines
if len(tilia_bundle.timeline_ids) >= 2:
    tilia_timeline_id_a, tilia_timeline_id_b = tilia_bundle.timeline_ids[:2]
    tilia_evts_a = list(tilia_tl_a.get_events())[:2]
    tilia_evts_b = list(tilia_tl_b.get_events())[:2]
    tilia_pairs = [
        (
            tilia_evts_a[0],
            tilia_timeline_id_a,
            tilia_evts_b[0],
            tilia_timeline_id_b,
        ),
    ]
    tilia_new_claims = tilia_bundle.create_match_claims(
        tilia_pairs, synchronous=True, agent="notebook_test"
    )
    print(f"Created {len(tilia_new_claims)} new MatchClaim(s)")
    tilia_new_claims[0] if tilia_new_claims else "No claims created"

# %%
# get_matchstamp() on a MatchClaim
if len(tilia_bundle.timeline_ids) >= 2 and tilia_new_claims:
    tilia_new_claims[0].get_matchstamp()

# %%
# get_matchstamps() - batch retrieval
if tilia_bundle.cross_group_claims:
    tilia_bundle.get_matchstamps(tilia_bundle.cross_group_claims[:3])

# %%
# get_matchstamp_table()
tilia_bundle.get_matchstamp_table()


# %% [markdown]
# ---
# ## 16. MatchfileLoader (Vienna .match files)
#
# Parses Vienna 4x22 corpus `.match` files via `partitura`.
# Builds a shared score timeline, per-performance timelines, and `MatchClaim`s.

# %%
from timetoalign.loader.alignment.matchfile import MatchfileLoader

match_file = VIENNA_DIR / "Chopin_op10_no3_p22.match"
match_file.name

# %%
match_loader = MatchfileLoader()
match_loader.load(match_file)
match_loader

# %%
match_tls = match_loader.create_timelines()
{tl.id: (tl.n_children, tl.n_events) for tl in match_tls}

# %%
match_tl_score = match_loader.create_timeline(uid="score")
match_tl_score

# %%
match_tl_score.get_events()

# %%
match_tl_score.get_events().schema

# %%
match_first_event = next(iter(match_tl_score.get_events()))
match_first_event_id = match_first_event["id"]
match_tl_score.get_event(match_first_event_id)

# %%
match_tl_score.get_timestamp_of(match_first_event_id)

# %%
match_tl_score.get_timestamp_at(10)

# %%
match_tl_score.get_events_at(0)

# %%
match_event_ids = [evt["id"] for evt in list(match_tl_score.get_events())[:5]]
match_tl_score.get_timestamps_of(match_event_ids)

# %%
match_tl_score.get_timestamp_table()

# %% [markdown]
# ### MatchfileLoader: TimelineGroup
#
# MatchfileLoader produces score and performance timelines that are organized
# into groups by the AlignmentBundle.

# %%
match_bundle = match_loader.create_alignment_bundle()
match_bundle

# %%
match_bundle.n_groups

# %%
if match_bundle.groups:
    match_group_id = list(match_bundle.groups.keys())[0]
    match_group = match_bundle.groups[match_group_id]
    match_group

# %% [markdown]
# ### MatchfileLoader: AlignmentBundle with MatchClaim Creation

# %%
match_claims = match_bundle.get_match_claims()
len(match_claims)

# %%
match_claims[0] if match_claims else "No claims"

# %%
match_claims[0].get_matchstamp() if match_claims else "No claims"

# %%
match_tl_ids = list(match_bundle.timeline_ids)[:2]
match_tl_a, match_tl_b = match_bundle.get_timelines(match_tl_ids)
print(f"Timeline A: {match_tl_a.id}, Timeline B: {match_tl_b.id}")

# %%
# Create additional MatchClaims by pairing events
match_evts_a = list(match_tl_a.get_events())[:2]
match_evts_b = list(match_tl_b.get_events())[:2]
if match_evts_a and match_evts_b:
    match_pairs = [
        (match_evts_a[0], match_tl_ids[0], match_evts_b[0], match_tl_ids[1]),
    ]
    match_new_claims = match_bundle.create_match_claims(
        match_pairs, synchronous=True, agent="notebook_test"
    )
    print(f"Created {len(match_new_claims)} new MatchClaim(s)")
    match_new_claims[0] if match_new_claims else "No claims created"

# %%
# get_matchstamps() - batch retrieval
match_bundle.get_matchstamps(match_claims[:5])

# %%
# get_matchstamp_table()
match_bundle.get_matchstamp_table()


# %% [markdown]
# ---
# ## Summary
#
# This notebook demonstrates the unified API across all Time To Align! loaders:
#
# | API Layer | Key Methods |
# |-----------|-------------|
# | **Loader** | `load()`, `from_file()`, `store`, `create_timeline()`, `create_timelines()` |
# | **Timeline** | `get_events()`, `get_event()`, `get_timestamp()`, `get_timestamp_of()`, `get_timestamps_of()` |
# | **TimelineGroup** | `get_timeline()`, `get_events()`, `get_timestamp_at()`, `get_timestamp_of()` |
# | **AlignmentBundle** | `get_timelines()`, `get_match_claims()`, `create_match_claims()`, `get_matchstamp_table()` |
