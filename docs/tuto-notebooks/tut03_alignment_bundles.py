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
from timetoalign import AlignmentBundle, MatchfileLoader
from timetoalign.core import SupportPolicy
from timetoalign.testdata import ensure_data
from timetoalign.timelines import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteLogicalTimeline,
)

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
bundle = loader.create_bundle()
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
perf_id = [uid for uid in bundle.timeline_ids if uid != score_tl.id][0]

stamp = bundle.get_matchstamp_at(100.0, "score:clt1")
stamp

# %% [markdown]
# The returned stamp exposes unit-bearing coordinates through
# `get_coordinate()`, and `is_interpolated` identifies a WarpMap fallback
# rather than an exact claim anchor.

# %%
{
    "score coordinate": stamp.get_coordinate("score:clt1"),
    "interpolated": stamp.is_interpolated,
}

# %% [markdown]
# ## Merge Bundles and Bridge Them
#
# Two bundles built separately can be merged into one with
# `AlignmentBundle.from_bundles`. Merging registers every group, timeline,
# and `MatchClaim` from each source, but does **not** itself align the two
# sides — you bridge them afterwards by adding `MatchClaim`s. Everything
# below is built in memory, with no data files.
#
# The first bundle is a symbolic score, four measures of 4/4:

# %%
score = ContinuousLogicalTimeline(length=12, uid="score")
score.add_events(
    [
        {
            "id": f"m{m}",
            "temporal_type": "instant",
            "event_type": "Measure",
            "instant": float(4 * m),
        }
        for m in range(4)
    ]
)
symbolic = AlignmentBundle(name="symbolic")
symbolic.add_timeline(score, as_group="score")

# %% [markdown]
# The second bundle is one performance, its audio (`seconds`) and MIDI
# (`ticks`) placed in a single group, so a coordinate transfers between them
# by interpolation:

# %%
perf = ContinuousPhysicalTimeline(length=6.0, uid="perf")
midi = DiscreteLogicalTimeline(length=2880, uid="midi")
audio = AlignmentBundle(name="audio")
audio.add_timeline(perf, as_group="performance")
audio.add_timeline(midi, grouped_with="perf")

merged = AlignmentBundle.from_bundles([symbolic, audio], name="merged")
merged

# %% [markdown]
# The merged bundle holds all three timelines but no connection between the
# two sides yet. `create_match_claims` bridges the score to the performance
# at the measure downbeats — quarters on `score` to seconds on `perf`:

# %%
merged.create_match_claims(
    [
        ({"start": q}, "score", {"start": s}, "perf")
        for q, s in [(4.0, 1.0), (8.0, 3.0), (12.0, 5.0)]
    ]
)
sorted(merged.timeline_ids)

# %% [markdown]
# ## The Transitive Union Across Both Bundles
#
# A single `get_matchstamp_at()` on `score` now resolves the whole chain:
# the bridge warps `score` to `perf`, and `perf`'s own group carries the
# reach on to `midi`. The stamp spans all three timelines even though no
# claim ties `score` directly to `midi`.

# %%
merged.get_matchstamp_at(8.0, "score")

# %% [markdown]
# ## Out-of-Support Coordinates
#
# The bridge's earliest anchor is measure 2 (quarter 4). A query below it —
# quarter 0 — lies outside the WarpMap's support, so `perf` (and the `midi`
# reached through it) has no defined position there. `support_policy` decides
# what happens. The default, `SupportPolicy.omit`, drops the unsupported
# timelines; the queried timeline's own coordinate always stays:

# %%
merged.get_matchstamp_at(0.0, "score")  # support_policy defaults to omit

# %% [markdown]
# `clamp` reports the nearest in-support boundary coordinate instead of
# dropping the timeline; `extrapolate` keeps the linear extrapolation but
# clips it to each timeline's `[0, length]` span. No policy ever yields a
# negative coordinate. The per-call `support_policy` argument overrides the
# bundle-wide `AlignmentBundle.support_policy` default:

# %%
{
    "clamp": merged.get_matchstamp_at(0.0, "score", support_policy="clamp"),
    "extrapolate": merged.get_matchstamp_at(
        0.0, "score", support_policy=SupportPolicy.extrapolate
    ),
}

# %% [markdown]
# **Next:** [Flow Control and Grids](tut04_flow_and_grids.ipynb)
