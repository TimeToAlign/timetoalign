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
# # Alignment Bundles
#
# An `AlignmentBundle` manages multiple timelines and the groups that
# connect them. We load the Vienna 1x22 corpus (one score, 22
# performances) using the `MatchfileLoader` to illustrate the pattern.

# %%
from pathlib import Path

from timetoalign import MatchfileLoader

DATA_DIR = Path(".").resolve().parents[1] / "tests" / "data" / "vienna_1x22"

# %% [markdown]
# ## Load All Match Files at Once
#
# A single `MatchfileLoader` instance processes all `.match` files that
# share the same score.

# %%
match_files = sorted(DATA_DIR.glob("*.match"))
loader = MatchfileLoader()
loader.load(*match_files)

{
    "files loaded": len(match_files),
    "timelines": len(loader.create_timelines()),
}

# %% [markdown]
# ## Create the Bundle

# %%
bundle = loader.create_alignment_bundle()
bundle

# %% [markdown]
# ## Explore Timelines

# %%
score_tl = bundle.get_timeline("score")
score_tl

# %%
score_tl.get_events(event_type="Note").to_dataframe().head()

# %% [markdown]
# ## Query Coordinates Across Groups
#
# `get_timestamp_at()` returns coordinates on all connected timelines.

# %%
perf_id = [uid for uid in bundle.timeline_ids if uid != "score"][0]

ts = bundle.get_timestamp_at(100.0, "score")
ts

# %% [markdown]
# **Next:** [Flow Control and Grids](tut04_flow_and_grids.ipynb)
