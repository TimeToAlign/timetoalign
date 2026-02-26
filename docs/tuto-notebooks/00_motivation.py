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
# # Why TimeToAlign! Matters
#
# Music exists simultaneously as audio, notation, and images --- each with
# its own coordinate system. The same melodic entrance might be at pixel
# (245, 380), second 2.3, MIDI tick 960, or beat 2. **TimeToAlign!**
# provides a single framework for connecting these representations.
#
# This notebook previews the core capabilities; the tutorials that follow
# unpack them one by one.

# %% [markdown]
# ## The Three Temporal Domains
#
# | Domain | Description | Examples |
# |--------|-------------|---------|
# | **Physical** | Wall-clock time | Seconds, samples, frames |
# | **Logical** | Symbolic/musical time | Beats, quarters, ticks |
# | **Graphical** | Visual coordinates | Pixels, centimetres |

# %% [markdown]
# ## Quick Demo: Two Formats, Same Content
#
# We load Chopin's Etude Op. 10 No. 3 from both MusicXML and TSV, and
# verify that both loaders produce identical note counts.

# %%
from pathlib import Path

from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.tsv import TSVLoader

DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data" / "vienna_1x22"

# %%
pt_loader = PartituraLoader.from_file(DATA_DIR / "Chopin_op10_no3.musicxml")
tsv_loader = TSVLoader.from_file(DATA_DIR / "ms3" / "chopin_op10_no3.notes.tsv")

{
    "Partitura (MusicXML)": f"{len(pt_loader.store.notes)} notes",
    "TSV (MS3 export)": f"{len(tsv_loader.store.notes)} notes",
}

# %% [markdown]
# Both loaders found **exactly 498 notes** --- different formats, same
# musical content, identical event counts.

# %% [markdown]
# ## Tutorial Roadmap
#
# | Notebook | Topic |
# |----------|-------|
# | **01a** Timelines, Events & Maps | Loading, EventStore, Coordinate, ConversionMap |
# | **01b** Children, Regions & Timestamps | Hierarchy, cross-section queries |
# | **02** Timeline Groups | Commensurability, coordinate transfer |
# | **03** Alignment Bundles | Multi-timeline datasets, MatchfileLoader |
# | **04** Flow & Grids | BeatGrid, repeats, metrical structure |
#
# For deeper dives, see the **How-To Guides**.
