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
# # Loading Real Data
#
# *What you will build*
#
# You will load Chopin's Étude Op. 10 No. 3 from MusicXML and an ms3 TSV,
# producing the same kind of {{< glossary Timeline >}} you previously built by
# hand. You will finish with a score timeline whose {{< glossary Child >}}
# timelines, measure data, and {{< glossary Coordinate >}} conversion came
# directly from the file.
#
# *Before you start*
#
# Complete the tutorial on {{< glossary Event >}}s,
# [Events on a Timeline](tut03_events.ipynb), first.

# %%
from fractions import Fraction

from IPython.display import display

from timetoalign import (
    CsvLoader,
    EventStore,
    Loader,
    Ms3Loader,
    Music21Loader,
    PartituraLoader,
    PerformanceMidiLoader,
    ScoreMidiLoader,
    TimeUnit,
    TsvLoader,
)
from timetoalign.testdata import ensure_data

VIENNA_DATA = ensure_data("vienna_1x22")
MIDI_DATA = ensure_data("midi")

# %% [markdown]
# ## From hand-built to real
#
# The first three tutorials taught the model by constructing timelines by hand;
# here, files replace those construction steps. Nothing new appears in the
# result—only in how it is produced.

# %%
musicxml_path = VIENNA_DATA / "Chopin_op10_no3.musicxml"
ms3_path = VIENNA_DATA / "ms3" / "chopin_op10_no3.notes.tsv"
score_midi_path = MIDI_DATA / "score" / "rachmaninoff_piano.mid"
performance_midi_path = MIDI_DATA / "performance" / "rachmaninoff_perf.mid"
source_files = {
    "MusicXML": musicxml_path,
    "ms3 TSV": ms3_path,
    "score MIDI": score_midi_path,
    "performance MIDI": performance_midi_path,
}
source_files

# %% [markdown]
# These are real corpus files resolved by `ensure_data()`. They are inputs to
# loaders, not a new kind of timeline result.

# %% [markdown]
# ## The two-phase contract
#
# `loader.load(*sources)` ingests files and returns the loader; only
# `loader.create_timeline()` builds objects in the musical
# {{< glossary Domain >}}, and it never takes a file path. `from_file()` is the
# shorthand for creating a loader and performing the first phase.

# %%
two_phase_loader = PartituraLoader()
two_phase_loader.load(musicxml_path)
display(two_phase_loader)

preview_timeline = two_phase_loader.create_timeline()
partitura_loader = PartituraLoader.from_file(musicxml_path)
phase_objects = {
    "phase-two result": preview_timeline,
    "from_file result": partitura_loader,
    "follows Loader contract": isinstance(partitura_loader, Loader),
}
phase_objects

# %% [markdown]
# The rendered loader between the two phases has one source but is not a
# timeline. The final mapping shows the timeline made in phase two and a freshly
# loaded shorthand instance; the remaining sections use that shorthand loader.

# %% [markdown]
# ## The EventStore
#
# `loader.store` is what the loader parsed before any timeline exists. Rendering
# the store as a table, followed by `store.summary()`, makes that intermediate
# state inspectable.

# %%
score_store = partitura_loader.store
display(score_store)

store_summary = score_store.summary()
store_inspection = {
    "follows EventStore contract": isinstance(score_store, EventStore),
    "summary": store_summary,
}
store_inspection

# %% [markdown]
# The rows summarize format-specific tables for notes, measures, controls, and
# annotations. A store is format-shaped, whereas a timeline is domain-shaped;
# that difference is why loading and timeline creation are separate phases. The
# current summary view projects its coordinate ranges as decimals; exact typed
# coordinates remain rational and appear below.

# %% [markdown]
# ## Making the timeline
#
# `create_timeline(uid=...)` turns the loaded store into the domain object. The
# optional `uid` supplies identity; a separate name can remain readable to a
# human.

# %%
score_timeline = partitura_loader.create_timeline(uid="score:clt1")
score_timeline.name = "Chopin, Étude Op. 10 No. 3"
timeline_identity = {
    "automatic id": preview_timeline.id,
    "role-prefixed id": score_timeline.id,
    "human-readable name": score_timeline.name,
}
timeline_identity

# %% [markdown]
# `clt1` means the first continuous logical timeline created by that loader;
# `score:clt1` adds an optional role prefix. The descriptive title is metadata,
# not identity, so changing it would not change the timeline's `id`.

# %% [markdown]
# ## What you got for free
#
# The loader has already separated each event category into a child timeline and
# attached a quarters-to-ticks {{< glossary ConversionMap >}}. We can also ask
# the familiar region API which {{< glossary Region >}} annotations were
# created.

# %%
child_ids = score_timeline.list_children()
measure_region_ids = score_timeline.list_regions()
quarters_to_ticks = score_timeline.get_conversion_map(TimeUnit.ticks)

quarter_position = score_timeline.make_coordinate(Fraction(6))
tick_position = score_timeline.convert_to(quarter_position, TimeUnit.ticks)
loader_payoff = {
    "children": child_ids,
    "measure regions": measure_region_ids,
    "quarters-to-ticks map": quarters_to_ticks,
    "quarter position": quarter_position,
    "tick position": tick_position,
}
loader_payoff

# %% [markdown]
# The children correspond to the store's populated categories, and the map
# turns an exact rational quarter position into an integer tick position. Both
# positions remain coordinate objects, so their units stay visible. In this
# release the measures are present as the `measures` child, but `list_regions()`
# is empty: the score loader does not also materialize them as regions. The
# children and conversion map are still the payoff of learning those structures
# by hand first.

# %% [markdown]
# ## Querying it
#
# A loaded timeline uses the same `get_events()` query introduced in the
# previous tutorial. Start with every category, then apply one familiar filter.

# %%
loaded_events = score_timeline.get_events()
display(loaded_events)

loaded_notes = score_timeline.get_events(event_type="Note")
loaded_notes

# %% [markdown]
# The first table includes events gathered from every child. The second keeps
# only `Note` events, using exactly the same `event_type` filter as a hand-built
# timeline.

# %% [markdown]
# ## The same music, a second way
#
# `PartituraLoader.from_file()` read the MusicXML above; now
# `Ms3Loader.from_file()` reads the neighboring note TSV. Comparing note counts
# tests whether the two provenances describe the same musical content.

# %%
ms3_loader = Ms3Loader.from_file(ms3_path)
ms3_timeline = ms3_loader.create_timeline(uid="ms3:clt1")
ms3_events = ms3_timeline.get_events()
ms3_notes = ms3_timeline.get_events(event_type="Note")

partitura_note_count = store_summary["tables"]["notes"]["count"]
note_counts = {
    "MusicXML via PartituraLoader": partitura_note_count,
    "TSV via Ms3Loader": len(ms3_notes),
}
timeline_classes = (score_timeline.class_name, ms3_timeline.class_name)
assert len(loaded_notes) == partitura_note_count
assert len(loaded_events) >= partitura_note_count
assert len(ms3_events) == len(ms3_notes)
assert len(set(note_counts.values())) == 1
assert len(set(timeline_classes)) == 1
format_comparison = {
    "timeline class": timeline_classes[0],
    "note counts": note_counts,
}
format_comparison

# %% [markdown]
# Both routes produce a `ContinuousLogicalTimeline` and find 498 notes:
# different provenance, same musical content. File formats do not always
# preserve the same amount of information, however; the later
# pitch-and-harmony tutorial shows where their knowledge differs.

# %% [markdown]
# ## The loader families
#
# Choose a loader family according to what the source represents, then choose a
# concrete loader for its file format.
#
# | Family | Public loaders | What it is for |
# |---|---|---|
# | Score | `Ms3Loader`, `Music21Loader`, `PartituraLoader` | Symbolic notation |
# | MIDI | `ScoreMidiLoader`, `PerformanceMidiLoader` | Quantized scores or performed timing |
# | Tabular | `TsvLoader`, `CsvLoader` | Custom delimited research tables |
# | Alignment | Alignment loaders | Existing correspondences between representations |
# | Graphical | Graphical loaders | Pages, images, and horizontal layout |
# | Format | Format loaders | Structured JSON or XML needing a specialised reading |
#
# Each family has a how-to guide of its own:
# [loading data](../howto/how01_loading_data.ipynb) ·
# [tabular loaders](../howto/how01_tabular_loaders.ipynb) ·
# [graphical timelines](../howto/how01_graphical_timelines.ipynb) ·
# [the Vienna corpus](../howto/how03_loading_vienna_corpus.ipynb) ·
# [load anything](../howto/how04_load_anything.ipynb)

# %%
loader_families = {
    "score": {
        "loaders": (Ms3Loader, Music21Loader, PartituraLoader),
        "example": source_files["MusicXML"],
    },
    "MIDI": {
        "loaders": (ScoreMidiLoader, PerformanceMidiLoader),
        "examples": (source_files["score MIDI"], source_files["performance MIDI"]),
    },
    "tabular": {
        "loaders": (TsvLoader, CsvLoader),
        "example": source_files["ms3 TSV"],
    },
}
loader_families

# %% [markdown]
# The class objects show that these are importable public loaders, while the
# example paths distinguish score MIDI from performance MIDI. Alignment,
# graphical, and format families use specialized loaders covered by their
# linked guides.

# %% [markdown]
# ## Beyond one timeline
#
# `create_timelines()` opens the door to loaders that yield several timelines;
# this leads to the next tutorial on {{< glossary TimelineGroup >}}s,
# [Timeline Groups](tut05_timeline_groups.ipynb).
# Alignment-capable loaders also provide `create_bundle()`, which produces an
# {{< glossary AlignmentBundle >}} in [Alignment Bundles and
# MatchClaims](tut06_alignment_bundles.ipynb).

# %%
timeline_list = ms3_loader.create_timelines()
future_doors = {
    "timelines returned": timeline_list,
    "loader families sampled above": len(loader_families),
}
future_doors

# %% [markdown]
# This score loader returns a one-item list; multi-source loaders can return
# more. The list-shaped interface is the bridge from loading one timeline here
# to organizing several timelines in the next tutorial.

# %% [markdown]
# ## What you learned
#
# - You can replace hand construction with real files without changing the kind of timeline produced.
# - You can separate `load()` from `create_timeline()` and use `from_file()` as their common shorthand.
# - You can inspect `loader.store` and its `summary()` before creating a timeline.
# - You can assign a type-based timeline id, optionally prefixed by a role, while keeping a readable name separate.
# - You can inspect loader-created children and conversion maps, and check whether regions were materialized.
# - You can query all loaded events before narrowing them with the familiar event filter.
# - You can compare MusicXML and ms3 TSV note content through the same timeline API.
# - You can choose among score, MIDI, tabular, alignment, graphical, and format loader families.
# - You can use `create_timelines()` and recognize `create_bundle()` as entry points to multi-timeline work.
#
# *Next*
#
# [Timeline Groups](tut05_timeline_groups.ipynb)
#
# *Go deeper*
#
# - [How to load data](../howto/how01_loading_data.ipynb)
# - [How to use tabular loaders](../howto/how01_tabular_loaders.ipynb)
# - [How to load many formats](../howto/how04_load_anything.ipynb)
