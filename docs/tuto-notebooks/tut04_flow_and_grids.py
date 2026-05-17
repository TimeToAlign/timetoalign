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
# # Flow Control and Grids
#
# Musical timelines are not always linear --- repeat signs, *Da Capo*,
# and multiple endings introduce jumps. This tutorial shows `BeatGrid`
# for rapid measure/beat querying and how loaders handle flow structures.

# %%
from fractions import Fraction

from timetoalign import BeatGrid

# %% [markdown]
# ## BeatGrid from Tempo
#
# Given a constant tempo and duration, `BeatGrid.from_tempo()` builds
# a metrical timeline with vectorised beat/measure accessors.

# %%
grid = BeatGrid.from_tempo(
    tempo_bpm=120.0,
    beats_per_measure=4,
    length_seconds=30.0,
    uid="demo_grid",
)
grid

# %% [markdown]
# ## Querying Measure and Beat

# %%
# At quarter-note position 6.0 --- which measure and beat?
{
    "quarters": 6.0,
    "measure": grid.measure_at(6.0),
    "beat": grid.beat_at(6.0),
}

# %%
# Reverse: measure 3, beat 1 --- what quarter-note position?
grid.quarter_at(measure=3, beat=Fraction(1))

# %% [markdown]
# ## Vectorised Accessors
#
# Beat and measure times as numpy arrays, useful for exporting to
# Sonic Visualiser or Audacity.

# %%
grid.beat_seconds()[:12]

# %%
grid.measure_seconds()

# %% [markdown]
# ## Export to CSV

# %%
# grid.export_to_csv("beats.csv", format="sonic_visualiser")

# %% [markdown]
# ## Loading Scores with Flow
#
# Loaders such as `Music21Loader` parse repeat signs and jumps from
# MusicXML or MEI. The resulting timeline includes `FlowControlElement`
# events. See the How-To notebooks for worked examples with real scores
# containing repeats and *D.S.* markings.

# %% [markdown]
# **Congratulations!** With these four tutorials you have met the core
# abstractions: Timelines, Events, ConversionMaps, TimelineGroups,
# AlignmentBundles, and BeatGrids. The **How-To Guides** explore
# real-world workflows in depth.
