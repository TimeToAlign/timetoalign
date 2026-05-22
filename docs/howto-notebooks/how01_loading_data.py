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
# # How to Load Data
#
# This tutorial introduces the Loader pattern and EventStores - the foundation
# for bringing music data into TimeToAlign!
#
# **Learning Objectives:**
# - Use Loaders to ingest music data from various formats
# - Navigate EventStores and access event data
# - Understand the harmonized schema that unifies different data sources
#
# **Prerequisites:**
# - Basic Python and pandas knowledge
# - TimeToAlign! installed (`pip install -e .` from repository root)

# %% [markdown]
# ## Why Loaders Matter
#
# Music data comes in many formats: MusicXML, MIDI, MEI, Humdrum, proprietary
# TSV exports, and more. Each format has its own structure, terminology,
# and quirks.
#
# **The problem:** Without a unified approach, you'd need format-specific code
# for every data source, making cross-format analysis difficult and error-prone.
#
# **The TimeToAlign! solution:** Loaders normalize heterogeneous formats into
# a consistent `EventStore`, enabling downstream processing without
# format-specific code.
#
# ```
# MusicXML ─┐
# MIDI ─────┼──> Loader ──> EventStore ──> DataFrame
# TSV ──────┘
# ```

# %% [markdown]
# ## Setup

# %%
import pandas as pd

from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.testdata import ensure_data

DATA_DIR = ensure_data("vienna_1x22")

# Our test piece: Chopin Etude Op.10 No.3
CHOPIN_XML = DATA_DIR / "Chopin_op10_no3.musicxml"
CHOPIN_TSV = DATA_DIR / "ms3" / "chopin_op10_no3.notes.tsv"

CHOPIN_XML.name, CHOPIN_TSV.name

# %% [markdown]
# ## The Loader Pattern
#
# All TimeToAlign! loaders follow the same three-step pattern:
#
# 1. **Create** a loader instance
# 2. **Load** a file using `.load(path)`
# 3. **Access** the store containing EventStores
#
# Let's see this in action with three different loaders, all loading the same Chopin piece:

# %%
# Load from three different sources
tsv_loader = TSVLoader()
tsv_loader.load(CHOPIN_TSV)

partitura_loader = PartituraLoader()
partitura_loader.load(CHOPIN_XML)

music21_loader = Music21Loader()
music21_loader.load(CHOPIN_XML)

# All produce ScoreStores
{
    "TSV": type(tsv_loader.store).__name__,
    "Partitura": type(partitura_loader.store).__name__,
    "Music21": type(music21_loader.store).__name__,
}

# %% [markdown]
# ## Cross-Loader Validation
#
# One of the key benefits of TimeToAlign! is that different loaders produce
# comparable output. Let's verify that all three loaders found the same
# number of notes:

# %%
# Convert to DataFrames
tsv_df = tsv_loader.store.notes.to_dataframe()
partitura_df = partitura_loader.store.notes.to_dataframe()
music21_df = music21_loader.store.notes.to_dataframe()

# Count only Note events (not rests or other event types)
counts = {
    "TSV": len(tsv_df[tsv_df["event_type"] == "Note"]),
    "Partitura": len(partitura_df[partitura_df["event_type"] == "Note"]),
    "Music21": len(music21_df[music21_df["event_type"] == "Note"]),
}

# Validate against gold standard
assert all(c == 498 for c in counts.values()), f"Note count mismatch: {counts}"

pd.Series(counts, name="note_count")

# %% [markdown]
# ## The EventStore
#
# Each ScoreStore contains **EventStores** - efficient, PyArrow-backed tables
# that hold musical events.
#
# Key characteristics:
# - **High Performance**: Built on Apache Arrow for fast columnar operations
# - **Type Safety**: Schema metadata preserves units and types
# - **Pandas Interop**: Easy conversion with `.to_dataframe()`

# %%
notes_store = tsv_loader.store.notes

{
    "type": type(notes_store).__name__,
    "n_events": len(notes_store),
    "storage": type(notes_store.table).__name__,
}

# %%
# Examine the schema with metadata
schema_info = []
for field in notes_store.table.schema:
    meta = field.metadata or {}
    meta_str = (
        ", ".join(f"{k.decode()}={v.decode()}" for k, v in meta.items()) if meta else ""
    )
    schema_info.append(
        {"name": field.name, "type": str(field.type)[:30], "metadata": meta_str}
    )

pd.DataFrame(schema_info)

# %% [markdown]
# ## The Harmonized Schema
#
# TimeToAlign! uses a harmonized schema to represent events consistently across formats:
#
# | Column | Description |
# |--------|-------------|
# | `id` | Unique identifier for the event |
# | `temporal_type` | "instant" or "interval" |
# | `event_type` | Type of event (Note, Rest, etc.) |
# | `start`, `end`, `duration` | Temporal coordinates (as structs) |
# | `duration_float` | Duration as a float for quick queries |
# | `mc`, `mn` | Measure count and measure number |
# | `midi_pitch` | MIDI pitch number (0-127) |
# | `specific_pitch` | Pitch spelling information |

# %%
# Show selected fields for the first few notes
display_cols = [
    "id",
    "name",
    "temporal_type",
    "event_type",
    "duration_float",
    "mc",
    "mn",
    "octave",
]
tsv_df[display_cols].head(10)

# %% [markdown]
# ## Pitch Information
#
# The `specific_pitch` field contains rich pitch information as a struct.
# This preserves the enharmonic spelling (e.g., G# vs Ab) which is lost
# when using only MIDI pitch numbers.

# %%
# Extract specific_pitch pitch information for the first note
first_note = tsv_df.iloc[0]

{
    "name": first_note["name"],
    "midi_pitch": first_note["midi_pitch"],
    "octave": first_note["octave"],
    "specific_pitch": first_note["specific_pitch"],
}

# %% [markdown]
# ## Duration Analysis
#
# TimeToAlign! stores durations in quarter notes. Let's analyze the rhythmic content of our piece:

# %%
# Duration distribution
tsv_df["duration_float"].value_counts().sort_index().to_frame("count")

# %%
# Summary statistics
tsv_df["duration_float"].describe()

# %% [markdown]
# ## Navigating by Measure
#
# The `mc` (measure count) and `mn` (measure number) fields allow easy
# navigation through the score. Note that `mn` is stored as a string
# (to support labels like "1a", "1b"), so we convert to int for proper sorting:

# %%
# Notes per measure, sorted numerically
notes_per_measure = tsv_df.groupby("mn").size()

# Convert index to int for proper sorting (works for simple numeric measure numbers)
notes_per_measure.index = notes_per_measure.index.astype(int)
notes_per_measure = notes_per_measure.sort_index()

notes_per_measure.to_frame("notes")

# %%
# Get all notes in a specific measure
measure_5 = tsv_df[tsv_df["mn"] == "5"]
measure_5[["name", "duration_float", "voice", "staff"]]

# %% [markdown]
# ## Comparing Loader Outputs
#
# While all loaders produce the same number of notes, there can be subtle
# differences in how they interpret the score. Let's compare the first
# few notes:

# %%
# Compare ID schemes across loaders
pd.DataFrame(
    {
        "TSV_id": tsv_df["id"].head(5).values,
        "TSV_name": tsv_df["name"].head(5).values,
        "Partitura_id": partitura_df["id"].head(5).values,
        "Music21_id": music21_df["id"].head(5).values,
    }
)

# %% [markdown]
# ## Unit Metadata
#
# TimeToAlign! stores unit information in the PyArrow schema metadata.
# This ensures coordinates are always interpreted correctly:

# %%
# Extract unit metadata for temporal fields
temporal_cols = ["start", "end", "duration"]
{
    field.name: field.metadata.get(b"unit", b"(unknown)").decode()
    for field in notes_store.table.schema
    if field.name in temporal_cols and field.metadata
}

# %% [markdown]
# ## Voice and Staff Information
#
# In scores with multiple staves or multiple voices per staff, notes are
# distributed accordingly:

# %%
# Notes by staff and voice
tsv_df.groupby(["staff", "voice"]).size().unstack(fill_value=0)

# %% [markdown]
# ## Summary
#
# In this tutorial, we learned:
#
# 1. **The Loader Pattern**: Create -> Load -> Access Bundle
# 2. **Three Score Loaders**: TSVLoader, PartituraLoader, Music21Loader
# 3. **EventStore**: PyArrow-backed, high-performance event storage
# 4. **Harmonized Schema**: Consistent fields across all loaders
# 5. **Cross-Validation**: Same piece from different sources yields same note count
#
# **Key Takeaway:**
# > Loaders normalize heterogeneous formats into a consistent EventStore,
# > enabling downstream processing without format-specific code.

# %% [markdown]
# ## Next Steps
#
# - **03_conversion_maps.ipynb**: Learn how to convert between coordinate systems
# - **04_building_timelines.ipynb**: Create Timeline objects from EventStores

# %% [markdown]
# ---
#
# ## Exercise: Load Another Score
#
# **Task:** Load the Beethoven String Quartet from `beethoven_op18.mid` and analyze its structure.
#
# **Hints:**
# 1. Use `PartituraLoader` for MIDI files
# 2. Check how many parts are in the score
# 3. Count notes per part
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Load the Beethoven quartet
# loader = PartituraLoader()
# loader.load(DATA_DIR / "beethoven_op18.mid")
#
# df = loader.store.notes.to_dataframe()
# {"total_notes": len(df), "notes_per_part": df.groupby("part_id").size().to_dict()}
# ```
#
# </details>

# %%
# Your solution here
