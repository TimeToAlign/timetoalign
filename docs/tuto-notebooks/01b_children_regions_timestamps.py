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
# # 01b: Children, Regions, and Timestamps
#
# Timelines nest inside one another. A **timestamp** is a cross-section
# that shows where you are in every active child at a given root coordinate.

# %%
from pathlib import Path

from timetoalign.loader.score.partitura import PartituraLoader

# %% [markdown]
# ## Load a Structured Score

# %%
DATA_DIR = (
    Path(".").resolve().parents[1]
    / "tests"
    / "data"
    / "score"
    / "bruckner5_scherzo"
    / "hauptstimme"
)

loader = PartituraLoader.from_file(DATA_DIR / "Bruckner_WAB.105_3a_Scherzo.mxl")
tl = loader.create_timeline(uid="bruckner_scherzo")
tl

# %% [markdown]
# ## Measures as Regions
#
# The loader's `EventStore` contains measure intervals. We can filter
# notes by coordinate bounds.

# %%
measures = loader.store.measures.to_dataframe()
m2 = measures.iloc[1]
{
    "measure": 2,
    "start": m2.start,
    "end": m2.end,
}

# %%
tl.get_events(
    event_type="Note", min_coord=m2.start, max_coord=m2.end
).to_dataframe().head()

# %% [markdown]
# ## Timestamps: Cross-Section Queries
#
# At root coordinate X, what is the local coordinate inside each active
# child timeline?

# %%
timestamps_df = tl.get_timestamps()
timestamps_df.head(10)

# %% [markdown]
# `NaN` means the coordinate falls outside that child's extent.

# %% [markdown]
# **Next:** [02 Timeline Groups](02_timeline_groups.ipynb)
