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
# EventData provides three layers of data access.  Layer 0 (raw table)
# always works on any EventData instance -- no special setup needed.
# Layers 1 and 2 add typed field views and external library integration.
#
# **Key principle:** EventData is never mutated.  `get_field()` returns
# a cached view over existing columns -- the EventData itself is
# unchanged.

# %% [markdown]
# ## Setup

# %%
from __future__ import annotations

from timetoalign.core import TimeUnit
from timetoalign.fields.pitch import EnharmonicPitchField, PitchField
from timetoalign.loader.score.stores.notes import NoteEventData

# %% [markdown]
# ## Layer 0 -- Raw Table Access
#
# Every EventData instance wraps a PyArrow table.  You can always
# access the underlying table and its columns directly, regardless
# of whether any semantic fields are available.

# %%
notes = NoteEventData.from_dicts(
    [
        {
            "event_type": "Note",
            "start": 0.0,
            "duration": 1.0,
            "midi_pitch": {"ep": 60, "epc": 0},
        },
        {
            "event_type": "Note",
            "start": 1.0,
            "duration": 1.0,
            "midi_pitch": {"ep": 64, "epc": 4},
        },
        {
            "event_type": "Note",
            "start": 2.0,
            "duration": 1.0,
            "midi_pitch": {"ep": 67, "epc": 7},
        },
    ],
    unit=TimeUnit.quarters,
)
notes.table

# %%
# Column-level access -- returns a PyArrow ChunkedArray
notes.table.column("midi_pitch")

# %% [markdown]
# ## Layer 1 -- SemanticField Views
#
# `get_field()` inspects the table's columns, constructs the matching
# SemanticField, and caches it.  The EventData is never modified --
# the field is a lightweight view over the existing column data.

# %%
notes.has_field(EnharmonicPitchField)

# %%
field = notes.get_field(EnharmonicPitchField)
field

# %%
# Element access returns a typed scalar (MidiPitch)
field[0]

# %%
field[0].midi_number

# %% [markdown]
# ### Parent-type queries
#
# Requesting an abstract parent type (e.g. `PitchField`) discovers
# the most specific available subclass:

# %%
notes.has_field(PitchField)

# %% [markdown]
# ## Caching is Transparent
#
# Repeated `get_field()` calls return the **same** object -- the field
# is constructed once, then cached.  No user action is needed.

# %%
a = notes.get_field(EnharmonicPitchField)
b = notes.get_field(EnharmonicPitchField)
a is b

# %% [markdown]
# ## Layer 2 -- External Libraries
#
# The raw PyArrow columns that back Layer 1 fields are also accessible
# to external libraries such as FlexOHR and pitchtypes.  Because these
# are optional dependencies, no code example is shown here -- but the
# principle is the same: extract a column from the table and pass it
# to the library's own constructors.
#
# **Key takeaway.**  The three layers form a progressive-disclosure
# stack: Layer 0 always works, Layer 1 adds typed field views via
# `get_field()`, and Layer 2 lets external packages operate on the
# same underlying data.  EventData is never mutated at any layer.
