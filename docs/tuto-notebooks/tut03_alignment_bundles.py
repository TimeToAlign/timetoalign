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
# # Alignment Bundles
#
# An `AlignmentBundle` manages multiple timelines and the groups that
# connect them. We load the Vienna 1x22 corpus (one score, 22
# performances) using the `MatchfileLoader` to illustrate the pattern.

# %%
from timetoalign import MatchfileLoader
from timetoalign.testdata import ensure_data

DATA_DIR = ensure_data("vienna_1x22")

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
# `get_matchstamp_at()` is the cross-domain resolution method for an
# `AlignmentBundle`: it accepts a coordinate on any timeline and returns a
# `MatchStamp` spanning all connected timelines. `MatchStamp` shares the
# unified stamp interface used by the other timestamp types.

# %%
perf_id = [uid for uid in bundle.timeline_ids if uid != "score"][0]

stamp = bundle.get_matchstamp_at(100.0, "score")
stamp

# %% [markdown]
# The returned stamp exposes unit-bearing coordinates through
# `get_coordinate()`, and `is_interpolated` identifies a WarpMap fallback
# rather than an exact claim anchor.

# %%
{
    "score coordinate": stamp.get_coordinate("score"),
    "interpolated": stamp.is_interpolated,
}

# %% [markdown]
# **Next:** [Flow Control and Grids](tut04_flow_and_grids.ipynb)
