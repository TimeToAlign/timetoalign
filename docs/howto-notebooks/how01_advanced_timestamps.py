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

from timetoalign import TimeUnit
from timetoalign.timelines import Timeline

# %% [markdown]
# ## Setup: A Hierarchical Timeline

# %%
parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent")
parent.add_events(
    [
        {"id": "p1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
        {"id": "p2", "temporal_type": "instant", "event_type": "Beat", "instant": 50.0},
    ]
)

child1 = Timeline(length=20, unit=TimeUnit.seconds, uid="child1")
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

child2 = Timeline(length=15, unit=TimeUnit.seconds, uid="child2")
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
parent.get_timestamps(coordinates=coords)

# %%
# Efficient numpy array query
coords = np.linspace(0, 100, 21)
parent.get_timestamps(coordinates=coords)

# %% [markdown]
# ## Boundary Tables

# %%
parent.get_boundary_table().to_pandas()

# %% [markdown]
# ## Filtered Timestamps

# %%
parent.get_timestamp_table_filtered({"event_type": "Note"}).to_pandas()

# %%
parent.get_timestamp_table_filtered({"event_type": "Beat"}).to_pandas()

# %% [markdown]
# ## PyArrow Tables
#
# For large datasets, `get_timestamp_table()` returns a PyArrow Table
# directly --- convert to pandas only when needed.

# %%
table = parent.get_timestamp_table()
{
    "rows": table.num_rows,
    "columns": table.column_names,
}

# %%
table.to_pandas().head()

# %% [markdown]
# ## The TimeStamp Object
#
# Query a **single coordinate** and get all related values on demand.

# %%
ts = parent.get_timestamp(15.0)
ts.to_dict()

# %%
# Access child coordinates via subscript
{
    "parent": ts.axis,
    "child1": ts["child1"],
    "child2": ts["child2"],
}

# %% [markdown]
# ## TimeIntervalStamp

# %%
interval = parent.get_interval_stamp(20.0, 60.0)
{
    "axis_duration": interval.duration,
    "child1_interval": interval["child1"],
}

# %%
interval.zip_intervals()

# %% [markdown]
# ## Coordinates with Units
#
# `TimeStamp` and `TimeIntervalStamp` can produce proper `Coordinate`
# objects that carry their unit.

# %%
ts = parent.get_timestamp(25.0)
axis_coord = ts.axis_coordinate
{
    "value": axis_coord.value,
    "unit": axis_coord.unit,
}

# %%
child1_coord = ts.get_coordinate("child1")
{
    "child1 value": child1_coord.value,
    "child1 unit": child1_coord.unit,
}

# %% [markdown]
# ## Unit Metadata in PyArrow Tables

# %%
table = parent.get_timestamp_table(coordinates=[0.0, 25.0, 50.0])

for field in table.schema:
    if field.metadata:
        unit = field.metadata.get(b"unit", b"N/A").decode()
        tl_id = field.metadata.get(b"timeline_id", b"N/A").decode()
        print(f"{field.name}: unit={unit}, timeline_id={tl_id}")
