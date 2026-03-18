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
# # How-To: Layered EventData Access
#
# Time To Align! loaders follow a two-phase pattern:
#
# 1. **Load** -- `loader.load(file)` reads the source into a faithful table.
# 2. **Access** -- `loader.get_events()` assembles an EventData with control
#    over which columns are included.
#
# EventData then provides three layers of data access:
#
# - **Layer 0** -- Raw table (`events.table`, `events.get_raw("col")`)
# - **Layer 1** -- Semantic fields (`events.get_field("start")`, blueprints)
# - **Layer 2** -- External library integration (FlexOHR, pitchtypes)
#
# **Key principle:** EventData is never mutated.  `get_field()` returns
# a cached view over existing columns -- the EventData itself is
# unchanged.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

from pathlib import Path

from timetoalign.fields.pitch import PitchField
from timetoalign.loader.score.tsv import TSVLoader

try:
    TTA_DIR = Path(__file__).resolve().parents[2]
except NameError:
    TTA_DIR = Path(".").resolve().parents[1]

NOTES_TSV = (
    TTA_DIR / "tests" / "data" / "vienna_1x22" / "ms3" / "chopin_op10_no3.notes.tsv"
)

# %% [markdown]
# ## Phase 1: Loading
#
# `TSVLoader.from_file()` reads a DCML-style notes TSV and builds
# an internal table.  After loading, the loader holds the data ready
# for assembly into EventData.

# %%
loader = TSVLoader.from_file(NOTES_TSV)
loader

# %% [markdown]
# ## Phase 2: get_events() -- Controlling Columns
#
# `get_events()` assembles an EventData from the loaded data.
# The `properties` parameter controls which non-field columns appear:
#
# - `True` (default): all columns
# - `False`: only field columns (start, end, duration) + core (id, name, event_type, temporal_type)
# - tuple of names: selected property columns

# %%
# All properties (default)
events = loader.get_events()
events

# %%
# The table schema reveals columns and their types -- much more readable
# than the raw table repr for wide data
events.table.schema

# %%
events.table.column_names

# %%
# Fields only -- no property columns like mc, mn, staff, voice
events_fields = loader.get_events(properties=False)
events_fields.table.column_names

# %%
# Selected properties
events_selected = loader.get_events(properties=("mc", "mn"))
events_selected.table.column_names

# %% [markdown]
# ## Layer 0 -- Raw Table Access
#
# Every EventData wraps a PyArrow table.  `get_raw()` wraps a column
# in a lightweight raw DataField without adding any semantic identity.
# The concrete type depends on the column's PyArrow type.

# %%
# Struct column -> StructField (e.g. "start" stores onset coordinates)
raw_start = events.get_raw("start")
raw_start

# %%
# Index 3 is G#3 -- an accidental-bearing note, more interesting than index 0
raw_start[3]

# %%
# Numeric column -> NumericField
raw_mc = events.get_raw("mc")
raw_mc[3]

# %%
# String column -> StringField (note names carry accidental information)
raw_name = events.get_raw("name")
raw_name[3], raw_name[8], raw_name[16]

# %% [markdown]
# ## Layer 1 -- Temporal Fields
#
# Every EventData has three core temporal columns: `start`, `end`,
# and `duration`.  `get_field()` with a column name returns the
# appropriate SemanticField: `CoordinateField` for start/end,
# `DurationField` for duration.

# %%
start = events.get_field("start")
start

# %%
# Indexing returns a Coordinate scalar with .value and .unit
# Index 8 is D#4 -- let's see where it starts
s8 = start[8]
s8.value, s8.unit

# %%
end = events.get_field("end")
repr(end[8])

# %%
dur = events.get_field("duration")
repr(dur[8])

# %% [markdown]
# A SemanticField always gives access to its underlying raw field
# via `get_raw()`:

# %%
start.get_raw()

# %% [markdown]
# ## Layer 1 -- PitchField (Blueprint Pattern)
#
# The Chopin data has **two** pitch columns: `midi_pitch` (EP -- enharmonic
# pitch via MIDI numbers) and `spelled_pitch` (SP -- fully spelled pitch
# with accidental identity).  This redundancy is the killer demonstration
# of the blueprint pattern.
#
# A **blueprint** PitchField names a column but carries no data.  Pass it
# to `get_field()` and EventData resolves the column, constructs the live
# field, and caches it.

# %% [markdown]
# ### EP blueprint (midi_pitch)

# %%
bp_ep = PitchField(ep="midi_pitch")
bp_ep  # blueprint -- no data yet

# %%
pf_ep = events.get_field(bp_ep)
pf_ep

# %%
# Indices with accidentals: 3=G#3, 8=D#4, 16=F#4, 29=G#4
pf_ep[3], pf_ep[8], pf_ep[16], pf_ep[29]

# %% [markdown]
# ### SP blueprint (spelled_pitch)

# %%
bp_sp = PitchField(sp="spelled_pitch")
bp_sp

# %%
pf_sp = events.get_field(bp_sp)
pf_sp

# %%
# The SAME indices -- now with full spelling preserved
pf_sp[3], pf_sp[8], pf_sp[16], pf_sp[29]

# %% [markdown]
# Compare the two representations of the same note -- EP loses
# the distinction between enharmonic equivalents, while SP preserves it:

# %%
{
    "index 3 (EP)": repr(pf_ep[3]),
    "index 3 (SP)": repr(pf_sp[3]),
    "index 83 (EP)": repr(pf_ep[83]),
    "index 83 (SP)": repr(pf_sp[83]),
}

# %% [markdown]
# ### Caching
#
# Repeated calls with the same blueprint return the **same** cached object:

# %%
events.get_field(PitchField(ep="midi_pitch")) is pf_ep

# %% [markdown]
# ### PitchField properties
#
# Each live PitchField exposes `pitch_type`, `space`, and `is_class`:

# %%
pf_ep.pitch_type, pf_ep.space, pf_ep.is_class

# %%
pf_sp.pitch_type, pf_sp.space, pf_sp.is_class

# %% [markdown]
# ## Layer 1 -- PitchField Conversions
#
# `.to()` converts between pitch types.  Only information-losing
# conversions are permitted (richer to coarser).  Starting from the
# SP field (the most informative), we can reach every coarser type.

# %%
# SP -> SPC: drop octave, keep spelling
pf_spc = pf_sp.to("spc")
pf_spc[3], pf_spc[8], pf_spc[29]

# %%
# SP -> EPC: lose spelling and octave (chromatic pitch class 0-11)
pf_epc = pf_sp.to("epc")
pf_epc[3], pf_epc[8], pf_epc[29]

# %%
# SP -> GPC: lose accidentals and octave (diatonic step 0-6)
pf_gpc = pf_sp.to("gpc")
pf_gpc[3], pf_gpc[8], pf_gpc[29]

# %% [markdown]
# The same note index through all representations -- from most
# informative (SP) to least (GPC):

# %%
{
    "SP": repr(pf_sp[29]),
    "SPC": repr(pf_spc[29]),
    "EPC": repr(pf_epc[29]),
    "GPC": repr(pf_gpc[29]),
}

# %% [markdown]
# ## Field Discovery
#
# EventData provides discovery methods for finding fields by type.

# %%
# has_field -- does this EventData have pitch columns?
events.has_field(PitchField)

# %%
# get_fields -- find ALL matching fields (returns both midi_pitch and spelled_pitch)
pitch_fields = events.get_fields(PitchField)
len(pitch_fields), [repr(pf) for pf in pitch_fields]

# %%
# get_field by class -- returns first match
pf_first = events.get_field(PitchField)
repr(pf_first[3])

# %%
# get_pitch_field -- returns the most informative (SP > EP)
pf_best = events.get_pitch_field()
repr(pf_best), repr(pf_best[3])

# %% [markdown]
# The Chopin notes have both `spelled_pitch` (SP) and `midi_pitch`
# (EP) columns.  `get_pitch_field()` returns the SP field because
# it is the most informative.

# %% [markdown]
# ## Caching Behaviour
#
# All `get_field()` calls are cached.  Repeated requests for the
# same field return the identical object.

# %%
f1 = events.get_field("start")
f2 = events.get_field("start")
f1 is f2

# %% [markdown]
# ## Layer 2 -- External Libraries
#
# The raw PyArrow columns backing Layer 1 fields are accessible
# to external libraries (FlexOHR, pitchtypes).  Extract a column
# from the table and pass it to the library's constructors.
#
# **Key takeaway.**  The loader-first pipeline gives you:
#
# 1. `loader.get_events()` -- an EventData with column control
# 2. Three layers of access: raw table, semantic fields, external libs
#
# EventData is never mutated.  Fields are cached views.
