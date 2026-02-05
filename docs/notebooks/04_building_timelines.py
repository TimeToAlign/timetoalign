# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Building Timelines: Events and Hierarchies
#
# This tutorial shows how to create **Timeline** objects, populate them with
# events, and build hierarchical structures with child timelines.
#
# **Learning Objectives:**
# - Create Timeline objects of various types
# - Add events (instants and intervals) to timelines
# - Build hierarchical structures with parent/child relationships
# - Attach ConversionMaps for unit conversion
#
# **Prerequisites:**
# - 01_core_concepts.ipynb (Domains, Units, Coordinates)
# - 02_loading_data.ipynb (Loaders, EventStores)
# - 03_conversion_maps.ipynb (C-Maps)

# %% [markdown]
# ## Why Timelines Matter
#
# In previous tutorials, we worked with:
# - **EventStores**: Raw event data in tables
# - **Coordinates**: Individual time points
# - **C-Maps**: Functions to convert between units
#
# **Timelines** bring these together into a coherent structure:
#
# ```
#                     Timeline
#                  ┌─────────────┐
#                  │  EventStore │  <- events stored here
#                  │  C-Maps     │  <- conversion maps attached
#                  │  Children   │  <- nested timelines
#                  └─────────────┘
# ```
#
# Timelines enable:
# 1. **Organized event storage** with coordinate validation
# 2. **Hierarchical nesting** (measures containing notes, systems containing bars)
# 3. **Coordinate conversion** via attached C-Maps
# 4. **Timestamp generation** showing events across the hierarchy

# %% [markdown]
# ## Setup

# %%
from fractions import Fraction
from pathlib import Path
from pprint import pprint

import pandas as pd

from timetoalign import TimeUnit
from timetoalign.maps import TicksToQuarters
from timetoalign.timelines import Timeline

# %% [markdown]
# ---
#
# ## Creating Timelines
#
# A Timeline is created with:
# - **length**: The end coordinate (start is always 0)
# - **unit**: The time unit for coordinates
# - **uid** (optional): A unique identifier

# %%
# Create a simple timeline: 10 seconds long
audio_tl = Timeline(length=10.0, unit=TimeUnit.seconds, uid="audio")

print(f"Timeline: {audio_tl}")
print(f"  ID:     {audio_tl.id}")
print(f"  Unit:   {audio_tl.unit}")
print(f"  Domain: {audio_tl.domain}")
print(f"  Length: {audio_tl.length}")
print(f"  Events: {audio_tl.n_events}")

# %%
# A logical timeline in quarters (for score data)
score_tl = Timeline(length=16, unit=TimeUnit.quarters, uid="score")

# Supports fractional values
score_tl_frac = Timeline(
    length=Fraction(33, 2), unit=TimeUnit.quarters, uid="score_frac"
)

{"integer length": score_tl.length, "fraction length": score_tl_frac.length}

# %%
# A discrete timeline in ticks (MIDI resolution)
midi_tl = Timeline(length=1920, unit=TimeUnit.ticks, uid="midi")

{"unit": midi_tl.unit, "domain": midi_tl.domain, "length": midi_tl.length}

# %% [markdown]
# ### Timeline Properties

# %%
# Get a comprehensive summary
pprint(audio_tl.summary())

# %% [markdown]
# ---
#
# ## Adding Events
#
# Events are added as dictionaries with standardized fields:
#
# | Field | Required | Description |
# |-------|----------|-------------|
# | `id` | Yes | Unique identifier |
# | `temporal_type` | Yes | "instant" or "interval" |
# | `event_type` | Yes | Type name (e.g., "Note", "Beat") |
# | `instant` | For instant | Coordinate for instant events |
# | `start`, `end` | For interval | Coordinates for interval events |

# %%
# Add beat markers (instant events)
beats = [
    {"id": "beat1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
    {"id": "beat2", "temporal_type": "instant", "event_type": "Beat", "instant": 0.5},
    {"id": "beat3", "temporal_type": "instant", "event_type": "Beat", "instant": 1.0},
    {"id": "beat4", "temporal_type": "instant", "event_type": "Beat", "instant": 1.5},
    {"id": "beat5", "temporal_type": "instant", "event_type": "Beat", "instant": 2.0},
]

audio_tl.add_events(beats)
print(f"Events after adding beats: {audio_tl.n_events}")

# %%
# Add notes (interval events)
notes = [
    {
        "id": "n1",
        "temporal_type": "interval",
        "event_type": "Note",
        "start": 0.0,
        "end": 0.4,
    },
    {
        "id": "n2",
        "temporal_type": "interval",
        "event_type": "Note",
        "start": 0.5,
        "end": 0.9,
    },
    {
        "id": "n3",
        "temporal_type": "interval",
        "event_type": "Note",
        "start": 1.0,
        "end": 1.9,
    },
]

audio_tl.add_events(notes)
print(f"Events after adding notes: {audio_tl.n_events}")

# %%
# View events as DataFrame
df = audio_tl.events.to_dataframe()
df[["id", "temporal_type", "event_type"]].head(10)

# %% [markdown]
# ### Event Validation
#
# Timelines validate that events fit within their bounds:

# %%
# Try to add an event beyond the timeline length
out_of_bounds = [
    {"id": "oob", "temporal_type": "instant", "event_type": "Beat", "instant": 15.0},
]

try:
    audio_tl.add_events(out_of_bounds)
except ValueError as e:
    print(f"ValueError: {e}")

# %%
# Allow expansion if needed
print(f"Length before: {audio_tl.length}")
audio_tl.add_events(out_of_bounds, allow_expansion=True)
print(f"Length after:  {audio_tl.length}")
print(f"Events: {audio_tl.n_events}")

# %% [markdown]
# ### Filtering Events

# %%
# Get only Beat events
beat_store = audio_tl.get_events(event_type="Beat")
print(f"Beat events: {len(beat_store)}")

# Get only interval events
interval_store = audio_tl.get_events(temporal_type="interval")
print(f"Interval events: {len(interval_store)}")

# %% [markdown]
# ---
#
# ## Child Timelines (Hierarchies)
#
# Timelines can contain other timelines as **children**. This models hierarchical structures like:
# - A score containing measures
# - A measure containing beats
# - A graphical layout with multiple systems
#
# **Key concepts:**
# - Children share the same unit as their parent
# - Children are placed at an **offset** on the parent
# - Children are **locked** after being added (cannot expand)

# %%
# Create a parent timeline: 100 seconds
parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent")

# Create child timelines
child1 = Timeline(length=20, unit=TimeUnit.seconds, uid="verse1")
child1.add_events(
    [
        {
            "id": "v1_start",
            "temporal_type": "instant",
            "event_type": "Marker",
            "instant": 0.0,
        },
        {
            "id": "v1_mid",
            "temporal_type": "instant",
            "event_type": "Marker",
            "instant": 10.0,
        },
    ]
)

child2 = Timeline(length=15, unit=TimeUnit.seconds, uid="chorus")
child2.add_events(
    [
        {
            "id": "ch_start",
            "temporal_type": "instant",
            "event_type": "Marker",
            "instant": 0.0,
        },
        {
            "id": "ch_peak",
            "temporal_type": "instant",
            "event_type": "Marker",
            "instant": 7.5,
        },
    ]
)

# Add children at specific offsets
parent.add_child(child1, offset=10)  # verse1: [10, 30] on parent
parent.add_child(child2, offset=50)  # chorus: [50, 65] on parent

print(f"Parent has {parent.n_children} children")
pprint(parent.summary())

# %%
# Access children
retrieved_child = parent.get_child("verse1")
offset = parent.get_child_offset("verse1")

print(f"Child: {retrieved_child}")
print(f"Offset: {offset}")

# Child is now locked
print(f"Child locked: {retrieved_child.is_locked}")

# %%
# Iterate over children (sorted by offset)
for offset, child in parent.iter_children():
    print(f"  {child.id}: offset={offset.value}, length={child.length.value}")

# %% [markdown]
# ### Nested Hierarchies
#
# Children can have their own children, creating deep hierarchies:

# %%
# Create a 3-level hierarchy: piece -> movement -> section
piece = Timeline(length=600, unit=TimeUnit.seconds, uid="symphony")

movement1 = Timeline(length=300, unit=TimeUnit.seconds, uid="mov1")
section1a = Timeline(length=60, unit=TimeUnit.seconds, uid="exposition")
section1b = Timeline(length=90, unit=TimeUnit.seconds, uid="development")
section1c = Timeline(length=60, unit=TimeUnit.seconds, uid="recapitulation")

# Add events to sections
section1a.add_events(
    [
        {
            "id": "theme1",
            "temporal_type": "instant",
            "event_type": "Theme",
            "instant": 10.0,
        }
    ]
)
section1b.add_events(
    [
        {
            "id": "climax",
            "temporal_type": "instant",
            "event_type": "Climax",
            "instant": 45.0,
        }
    ]
)

# Build hierarchy: sections -> movement -> piece
movement1.add_child(section1a, offset=0)
movement1.add_child(section1b, offset=60)
movement1.add_child(section1c, offset=150)

piece.add_child(movement1, offset=0)

print(f"Piece: {piece}")
print(f"  Movement1: {movement1.n_children} sections")

# Iterate with recursion
print("\nFull hierarchy (depth-first):")
for offset, child in piece.iter_children(order="depth_first"):
    print(f"  {child.id}: parent-offset={offset.value}")

# %% [markdown]
# ---
#
# ## Attaching ConversionMaps
#
# C-Maps can be attached to timelines for coordinate conversion:

# %%
# Create a timeline in MIDI ticks
midi_tl = Timeline(length=1920, unit=TimeUnit.ticks, uid="midi_track")

# Add some note events
midi_tl.add_events(
    [
        {
            "id": "n1",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 0,
            "end": 480,
        },
        {
            "id": "n2",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 480,
            "end": 960,
        },
        {
            "id": "n3",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 960,
            "end": 1440,
        },
        {
            "id": "n4",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 1440,
            "end": 1920,
        },
    ]
)

# Attach a tick-to-quarters map (PPQ=480)
t2q = TicksToQuarters(ppq=480)
midi_tl.add_conversion_map(t2q)

print(f"C-Maps attached: {list(midi_tl._conversion_maps.keys())}")

# %%
# Convert coordinates using the timeline
tick_values = [0, 480, 960, 1440, 1920]
quarter_values = [midi_tl.convert_to(t, "quarters") for t in tick_values]

pd.DataFrame(
    {
        "ticks": tick_values,
        "quarters": quarter_values,
    }
)

# %% [markdown]
# ---
#
# ## Creating Timelines from EventStores
#
# Timelines can be created directly from EventStores loaded via Loaders:

# %%
from timetoalign.loader.score.tsv import TSVLoader  # noqa: E402

# Load some real score data
DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data" / "midi" / "score"
TSV_PATH = DATA_DIR / "ms3" / "chopin_op10_no3.notes.tsv"

if TSV_PATH.exists():
    loader = TSVLoader()
    loader.load(TSV_PATH)
    notes_store = loader.bundle.notes

    # Create timeline from store
    chopin_tl = Timeline.from_event_store(notes_store, uid="chopin_op10_no3")

    print(f"Timeline: {chopin_tl}")
    print(f"Events: {chopin_tl.n_events}")
    print(f"Length: {chopin_tl.length}")
else:
    print(f"Test data not found at {TSV_PATH}")

# %% [markdown]
# ---
#
# ## Serialization
#
# Timelines can be serialized to dictionaries (for JSON/YAML export):

# %%
# Create a simple timeline with events
tl = Timeline(length=10, unit=TimeUnit.seconds, uid="test")
tl.add_events(
    [
        {"id": "e1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
        {"id": "e2", "temporal_type": "instant", "event_type": "Beat", "instant": 5.0},
    ]
)

# Serialize
data = tl.to_dict()
print("Serialized (keys):")
print(f"  {list(data.keys())}")
print(f"  events: {len(data['events'])}")

# %%
# Deserialize
restored_tl = Timeline.from_dict(data)

print(f"Restored: {restored_tl}")
print(f"Events: {restored_tl.n_events}")

# %% [markdown]
# ---
#
# ## Summary
#
# In this tutorial, we learned:
#
# 1. **Creating Timelines**: `Timeline(length, unit, uid)`
# 2. **Adding Events**: `timeline.add_events([{...}])`
# 3. **Event Types**: Instant (single point) and Interval (start/end)
# 4. **Hierarchies**: `parent.add_child(child, offset)`
# 5. **C-Map Integration**: `timeline.add_conversion_map(cmap)` and `timeline.convert_to()`
# 6. **From EventStore**: `Timeline.from_event_store(store)`
# 7. **Serialization**: `timeline.to_dict()` and `Timeline.from_dict()`
#
# **Key Takeaway:**
# > Timelines organize events and their relationships across time. They support
# > hierarchical nesting (children) and coordinate conversion via attached
# > C-Maps.

# %% [markdown]
# ## Next Steps
#
# - **05_timestamps.ipynb**: Generate cross-section timestamps showing events
# across timeline hierarchies

# %% [markdown]
# ---
#
# ## Exercise 1: Model a Simple Song Structure
#
# **Task:** Create a timeline hierarchy for a song with:
# - Total length: 180 seconds
# - Intro: 0-15 seconds
# - Verse 1: 15-45 seconds
# - Chorus: 45-75 seconds
# - Verse 2: 75-105 seconds
# - Chorus: 105-135 seconds
# - Outro: 135-180 seconds
#
# **Hints:**
# 1. Create a parent timeline of 180 seconds
# 2. Create child timelines for each section
# 3. Add children at appropriate offsets
#
# <details>
# <summary>Solution</summary>
#
# ```python
# song = Timeline(length=180, unit=TimeUnit.seconds, uid="song")
#
# # Create sections
# intro = Timeline(length=15, unit=TimeUnit.seconds, uid="intro")
# verse1 = Timeline(length=30, unit=TimeUnit.seconds, uid="verse1")
# chorus1 = Timeline(length=30, unit=TimeUnit.seconds, uid="chorus1")
# verse2 = Timeline(length=30, unit=TimeUnit.seconds, uid="verse2")
# chorus2 = Timeline(length=30, unit=TimeUnit.seconds, uid="chorus2")
# outro = Timeline(length=45, unit=TimeUnit.seconds, uid="outro")
#
# # Add sections as children
# song.add_child(intro, offset=0)
# song.add_child(verse1, offset=15)
# song.add_child(chorus1, offset=45)
# song.add_child(verse2, offset=75)
# song.add_child(chorus2, offset=105)
# song.add_child(outro, offset=135)
#
# # Verify
# print(f"Song: {song.n_children} sections")
# for offset, child in song.iter_children():
#     end = offset.value + child.length.value
#     print(f"  {child.id}: [{offset.value}, {end}]")
# ```
#
# </details>

# %%
# Your solution here


# %% [markdown]
# ---
#
# ## Exercise 2: MIDI Timeline with Tempo Conversion
#
# **Task:** Create a MIDI timeline with:
# - Length: 3840 ticks (8 quarter notes at PPQ=480)
# - 8 quarter note events starting at ticks 0, 480, 960, etc.
# - A TicksToQuarters C-Map for conversion
#
# Then convert the start times to quarters.
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Create timeline
# ppq = 480
# midi = Timeline(length=3840, unit=TimeUnit.ticks, uid="midi")
#
# # Add quarter note events
# events = [
#     {"id": f"q{i+1}", "temporal_type": "interval", "event_type": "Note",
#      "start": i * ppq, "end": (i + 1) * ppq}
#     for i in range(8)
# ]
# midi.add_events(events)
#
# # Attach C-Map
# midi.add_conversion_map(TicksToQuarters(ppq=ppq))
#
# # Convert to quarters
# df = midi.events.to_dataframe()
# starts = df["start"].apply(lambda x: x["value"])
# quarters = [midi.convert_to(t, "quarters") for t in starts]
#
# pd.DataFrame({
#     "note": df["id"],
#     "start_ticks": starts,
#     "start_quarters": quarters,
# })
# ```
#
# </details>

# %%
# Your solution here
