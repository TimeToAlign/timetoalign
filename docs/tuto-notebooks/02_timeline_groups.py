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
# # 02: Timeline Groups and Commensurability
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
score_tl = PartituraLoader.from_file(
    DATA_DIR / "midi" / "score" / "rachmaninoff_piano.mid"
).create_timeline(uid="score")

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
ts = group.get_timestamp_at(20.0, "score")
{
    "score coordinate": 20.0,
    "performance coordinate": ts["performance"],
}

# %%
ts_back = group.get_timestamp_at(50.0, "performance")
{
    "performance coordinate": 50.0,
    "score coordinate": ts_back["score"],
}

# %% [markdown]
# ## Partial Alignment
#
# If the performance only covers measures 10--20 (say, beats 40--80 in
# the score), specify `start` and `end` boundaries.

# %%
partial = TimelineGroup(id="partial")
partial.add_timeline(score_tl)
partial.add_timeline(
    perf_tl,
    start=(40.0, "score"),
    end=(80.0, "score"),
)
partial

# %% [markdown]
# **Next:** [03 Alignment Bundles](03_alignment_bundles.ipynb)
