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
# # How to Query Timestamps
#
# Boundary tables, filtered timestamps, the `TimeStamp` /
# `TimeIntervalStamp` objects, and the underlying PyArrow tables.

# %%
import numpy as np

from timetoalign.timelines import ContinuousPhysicalTimeline

# %% [markdown]
# ## Setup: A Hierarchical Timeline

# %%
parent = ContinuousPhysicalTimeline(length=100, uid="parent")
parent.add_events(
    [
        {"id": "p1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
        {"id": "p2", "temporal_type": "instant", "event_type": "Beat", "instant": 50.0},
    ]
)

child1 = ContinuousPhysicalTimeline(length=20, uid="child1")
child1.add_events(
    [
        {"id": "c1a", "temporal_type": "instant", "event_type": "Note", "instant": 0.0},
        {
            "id": "c1b",
            "temporal_type": "instant",
            "event_type": "Note",
            "instant": 10.0,
        },
    ]
)

child2 = ContinuousPhysicalTimeline(length=15, uid="child2")
child2.add_events(
    [
        {"id": "c2a", "temporal_type": "instant", "event_type": "Note", "instant": 5.0},
    ]
)

parent.add_child(child1, offset=10)  # child1 spans [10, 30] on parent
parent.add_child(child2, offset=60)  # child2 spans [60, 75] on parent

# %% [markdown]
# ## Custom Coordinates

# %%
coords = [0.0, 15.0, 25.0, 50.0, 65.0, 100.0]
parent.get_timestamp_table(coords, format="dataframe")

# %%
# Efficient numpy array query
coords = np.linspace(0, 100, 21)
parent.get_timestamp_table(coords, format="dataframe")

# %% [markdown]
# ## Boundary Tables
#
# `get_boundary_table()` is a narrower exit onto the same table builder: it
# collects the child boundaries instead of the events. Asking
# `get_timestamp_table()` for the boundaries directly is the way to choose the
# output format.

# %%
parent.get_timestamp_table(
    include_events=False,
    include_boundaries=True,
    format="dataframe",
)

# %% [markdown]
# ## Filtering Events

# %%
parent.get_events(event_type="Note", include_children=True).to_dataframe()

# %%
parent.get_events(event_type="Beat", include_children=True).to_dataframe()

# %% [markdown]
# ## PyArrow Tables
#
# For large datasets, `get_timestamp_table()` returns a PyArrow Table directly.
# Its cells are coordinate structs rather than bare numbers, which is what keeps
# an authored ratio exact through a parquet round-trip. Ask for the pandas shape
# with `format="dataframe"` rather than calling `.to_pandas()` on the Arrow
# table, which would hand you one dict per cell.

# %%
table = parent.get_timestamp_table()
{
    "rows": table.num_rows,
    "columns": table.column_names,
}

# %%
parent.get_timestamp_table(format="dataframe").head()

# %% [markdown]
# ## The TimeStamp Object
#
# Query a **single coordinate** and get all related values on demand.

# %%
ts = parent.get_timestamp(15.0)
ts.to_dict()

# %%
# Access child coordinates by timeline ID. Only the children that actually
# cover the queried position are present; an absent ID raises KeyError.
{
    "parent": ts.axis,
    "present": ts.present_timelines,
    **{
        child_id: ts.get_coordinate_for(child_id)
        for child_id in ("child1", "child2")
        if child_id in ts.present_timelines
    },
}

# %% [markdown]
# ## TimeIntervalStamp

# %%
interval = parent.get_interval_stamp(20.0, 60.0)
{
    "axis_interval": interval.get_interval("parent"),
    "axis_duration": interval.duration,
    "present": interval.present_timelines,
}

# %%
interval.get_intervals()

# %% [markdown]
# ## Coordinates with Units
#
# `TimeStamp` and `TimeIntervalStamp` can produce proper `Coordinate`
# objects that carry their unit.

# %%
ts = parent.get_timestamp(25.0)
axis_coord = ts.axis
{
    "value": axis_coord.value,
    "unit": axis_coord.unit,
    "timeline_id": axis_coord.timeline_id,
}

# %%
child1_coord = ts.get_coordinate_for("child1")
{
    "child1 value": child1_coord.value,
    "child1 unit": child1_coord.unit,
}

# %% [markdown]
# ## Unit Metadata in PyArrow Tables

# %%
table = parent.get_timestamp_table([0.0, 25.0, 50.0])

for field in table.schema:
    if field.metadata:
        unit = field.metadata.get(b"unit", b"N/A").decode()
        tl_id = field.metadata.get(b"timeline_id", b"N/A").decode()
        print(f"{field.name}: unit={unit}, timeline_id={tl_id}")
