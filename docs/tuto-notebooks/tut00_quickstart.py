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
# # Quickstart
#
# Music exists simultaneously as audio, notation, and images --- each with
# its own coordinate system. **Time To Align!** provides a single framework
# for connecting them.
#
# | Domain | Description | Examples |
# |--------|-------------|----------|
# | **Physical** | Wall-clock time | Seconds, samples, frames |
# | **Logical** | Symbolic/musical time | Beats, quarters, ticks |
# | **Graphical** | Visual coordinates | Pixels, centimetres |
#
# This whirlwind tour covers the core concepts in under five minutes.
# Each section links to a full tutorial.

# %%
from pathlib import Path

from timetoalign import BeatGrid, MatchfileLoader, TimelineGroup
from timetoalign.loader.midi.performance import PerformanceMidiLoader
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.maps import TicksToQuarters

DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data"

# %% [markdown]
# ## 1. Timelines & Events
#
# Load a score and create a timeline with nested children.
# ([Full tutorial](tut01a_timelines_events_maps.ipynb))

# %%
loader = PartituraLoader()
loader.load(DATA_DIR / "vienna_1x22" / "Chopin_op10_no3.musicxml")
score = loader.create_timeline(uid="score")
score

# %% [markdown]
# ## 2. Timestamps
#
# A cross-section showing coordinates in the root and all children.
# ([Full tutorial](tut01b_children_regions_timestamps.ipynb))

# %%
score.get_timestamps().head(5)

# %% [markdown]
# ## 3. Conversion Maps
#
# Translate between units (e.g., quarters to MIDI ticks).
# ([Full tutorial](tut01a_timelines_events_maps.ipynb))

# %%
q2t = TicksToQuarters(ppq=480).inverse()
score.add_conversion_map(q2t)
score.convert_to(score.make_coordinate(8), target_unit="ticks")

# %% [markdown]
# ## 4. Timeline Groups
#
# Link timelines for coordinate transfer.
# ([Full tutorial](tut02_timeline_groups.ipynb))

# %%
perf = PerformanceMidiLoader.from_file(
    DATA_DIR / "midi" / "performance" / "rachmaninoff_perf.mid"
).create_timeline(uid="perf")

group = TimelineGroup(id="demo")
group.add_timeline(score)
group.add_timeline(perf)

ts = group.get_timestamp_at(20.0, "score")
ts

# %% [markdown]
# ## 5. Alignment Bundles
#
# Load 22 performances from `.match` files in one go.
# ([Full tutorial](tut03_alignment_bundles.ipynb))

# %%
match_files = sorted((DATA_DIR / "vienna_1x22").glob("*.match"))
bundle = MatchfileLoader().load(*match_files).create_alignment_bundle()

{"timelines": len(bundle.timeline_ids), "groups": len(bundle.group_ids)}

# %% [markdown]
# ## 6. Beat Grids
#
# Rapid measure/beat queries for metrical structure.
# ([Full tutorial](tut04_flow_and_grids.ipynb))

# %%
grid = BeatGrid.from_tempo(tempo_bpm=120, beats_per_measure=4, length_seconds=30)
{"quarters": 6.0, "measure": grid.measure_at(6.0), "beat": grid.beat_at(6.0)}

# %% [markdown]
# ---
#
# **That's it.** The tutorials that follow unpack each topic in detail;
# the How-To Guides show real-world workflows.
