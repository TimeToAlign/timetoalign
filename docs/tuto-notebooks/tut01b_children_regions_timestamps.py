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
# # Children, Regions, and Timestamps
#
# Timelines nest inside one another. A **timestamp** is a cross-section
# that shows where you are in every active child at a given root coordinate.

# %%
from timetoalign import IdCoordinate, TimeUnit
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.testdata import ensure_data
from timetoalign.timelines import ContinuousLogicalTimeline

# %% [markdown]
# ## Load a Structured Score

# %%
DATA_DIR = ensure_data("vienna_1x22")

loader = PartituraLoader()
loader.load(DATA_DIR / "Chopin_op10_no3.musicxml")
tl = loader.create_timeline(uid="chopin_etude")
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
    "start": float(m2.start),
    "end": float(m2.end),
}

# %%
tl.get_child("notes").get_events(
    event_type="Note", min_coord=float(m2.start), max_coord=float(m2.end)
).to_dataframe().head()

# %% [markdown]
# ## Create Children from Boundaries
#
# A boundary list with *k*+1 coordinates creates *k* named children. The
# children use their parent's concrete timeline class and tile each interval
# without copying the parent's events.

# %%
movement = ContinuousLogicalTimeline(length=12, uid="movement")
phrases = movement.create_children_from_boundaries(
    [0, 4, 9, 12],
    names=["opening", "middle", "closing"],
)

[
    {
        "name": phrase.name,
        "offset": movement.get_child_offset(phrase.id),
        "length": phrase.length,
    }
    for phrase in phrases
]

# %% [markdown]
# Because the children cover the parent contiguously from 0 to 12, this
# hierarchy has the structure of a segment line.

# %%
movement.is_segment_line()

# %% [markdown]
# ## Resolve a Grandchild Coordinate
#
# Nest the movement at offset 3 in a larger score. `get_coordinate()` follows
# the entire descendant path: local coordinate 2 in the `middle` phrase first
# gains that phrase's offset 4, then the movement's offset 3.

# %%
piece = ContinuousLogicalTimeline(length=20, uid="piece")
piece.add_child(movement, offset=3)

middle_coordinate = IdCoordinate(2, TimeUnit.quarters, "middle")
{
    "from IdCoordinate": piece.get_coordinate(middle_coordinate),
    "from value and timeline_id": piece.get_coordinate(2, timeline_id="middle"),
}

# %% [markdown]
# ## Control Diagram Depth
#
# The default recurses through the full hierarchy. `depth=1` keeps only the
# root's direct children, which is useful for a compact overview.

# %%
print("Full hierarchy:")
print(piece.diagram(depth=True))
print("\nOne child level:")
print(piece.diagram(depth=1))

# %% [markdown]
# ## Timestamps: Cross-Section Queries
#
# At root coordinate X, what is the local coordinate inside each active
# child timeline?

# %%
timestamps_df = tl.to_dataframe()
timestamps_df.head(10)

# %% [markdown]
# `NaN` means the coordinate falls outside that child's extent.

# %% [markdown]
# **Next:** [Timeline Groups](tut02_timeline_groups.ipynb)
