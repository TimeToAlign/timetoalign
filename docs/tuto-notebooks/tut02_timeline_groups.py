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
# # Timeline Groups and Commensurability
#
# Two timelines become **commensurable** --- meaning coordinates can be
# transferred between them --- once they share a `TimelineGroup`.

# %%
from pathlib import Path

from timetoalign import TimelineGroup
from timetoalign.loader.midi.performance import PerformanceMidiLoader
from timetoalign.loader.score.partitura import PartituraLoader

DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data"

# %% [markdown]
# ## Load a Score and a Performance

# %%
_pt = PartituraLoader()
_pt.load(DATA_DIR / "midi" / "score" / "rachmaninoff_piano.mid")
score_tl = _pt.create_timeline(uid="score")

perf_tl = PerformanceMidiLoader.from_file(
    DATA_DIR / "midi" / "performance" / "rachmaninoff_perf.mid"
).create_timeline(uid="performance")

{
    "score": f"{score_tl.length} {score_tl.unit.name}",
    "performance": f"{perf_tl.length} {perf_tl.unit.name}",
}

# %% [markdown]
# ## Create a Group
#
# Adding both timelines to the same group establishes a linear mapping
# between their full extents.

# %%
group = TimelineGroup(id="rachmaninoff")
group.add_timeline(score_tl)
group.add_timeline(perf_tl)
group

# %% [markdown]
# ## Transfer Coordinates

# %%
# Get timestamp at score position 20.0 - shows ALL peer timelines
ts = group.get_timestamp_at(20.0, "score")
ts

# %%
# Transfer back: get timestamp at performance position 50.0 (ticks are DISCRETE)
ts_back = group.get_timestamp_at(50, "performance")
ts_back

# %% [markdown]
# ## Partial Alignment
#
# If the performance only covers part of the score (say, quarter-beat
# positions 8 to 20), specify `start` and `end` boundaries.

# %%
partial = TimelineGroup(id="partial")
partial.add_timeline(score_tl)
partial.add_timeline(
    perf_tl,
    start=(8.0, "score"),
    end=(20.0, "score"),
)
partial

# %% [markdown]
# **Next:** [Alignment Bundles](tut03_alignment_bundles.ipynb)
