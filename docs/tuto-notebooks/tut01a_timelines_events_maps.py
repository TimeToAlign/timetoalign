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
# # Timelines, Events, and Maps
#
# Load real musical data, explore it as an `EventStore`, create a
# `Timeline`, and attach a `ConversionMap` to translate between units.

# %%
from pathlib import Path

from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.maps import TicksToQuarters

# %% [markdown]
# ## Load Events from a Score

# %%
DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data" / "vienna_1x22"

loader = PartituraLoader()
loader.load(DATA_DIR / "Chopin_op10_no3.musicxml")
loader.store

# %% [markdown]
# ## Create a Timeline

# %%
tl = loader.create_timeline(uid="chopin_etude")
tl

# %% [markdown]
# ## Access Events
#
# The loader creates child timelines for each event category (notes,
# measures, controls). Access them via `get_child()`.

# %%
tl.get_child("notes").get_events(event_type="Note").to_dataframe().head()

# %% [markdown]
# ## Coordinates
#
# A `Coordinate` binds a number to a unit, ensuring type-safe arithmetic.

# %%
coord = tl.make_coordinate(8)
coord

# %% [markdown]
# ## Conversion Maps (C-Maps)
#
# Attach a map to translate the timeline's native `quarters` into MIDI
# `ticks` (at 480 pulses per quarter).

# %%
q2t = TicksToQuarters(ppq=480).inverse()
tl.add_conversion_map(q2t)

ticks_coord = tl.convert_to(coord, target_unit="ticks")
{
    "input": f"{coord.value} {coord.unit.name}",
    "output": f"{ticks_coord}",
}

# %% [markdown]
# **Next:** [Children, Regions & Timestamps](tut01b_children_regions_timestamps.ipynb)
