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
# # Timestamps: Cross-Section Views Through Timelines
#
# This tutorial introduces **Timestamps** - cross-section tables that show
# synchronous coordinates across timeline hierarchies and conversion maps.
#
# **Learning Objectives:**
# - Understand what timestamps represent conceptually
# - Generate timestamp tables from timelines
# - Work with hierarchical coordinate projection
# - Combine timestamps with ConversionMaps for unit conversion
# - Use the `TimeStamp` object for single-coordinate queries
# - Use `TimeIntervalStamp` for interval queries across timelines
#
# **Prerequisites:**
# - 04_building_timelines.ipynb (Timelines, events, hierarchies)
# - 03_conversion_maps.ipynb (C-Maps)

# %% [markdown]
# ## Why Timestamps Matter
#
# When working with hierarchical timelines, a fundamental question arises:
#
# > "At coordinate X on the root timeline, what are the local coordinates on each child timeline?"
#
# For example, in a score with nested measures:
#
# ```
# Root timeline (quarters): [0 ────────────────────────── 16]
#                               ↑ measure 1      ↑ measure 2
# Measure 1 [offset=0]:    [0 ──── 4]
# Measure 2 [offset=4]:              [0 ──── 4]
# ```
#
# At root coordinate `5`, what's the local coordinate in each measure?
# - Root: 5
# - Measure 1 (offset=0): 5 → out of bounds (measure ends at 4)
# - Measure 2 (offset=4): 5 - 4 = **1** (local coordinate)
#
# **Timestamps** compute these projections for all event coordinates and present them as a table.

# %% [markdown]
# ## Setup


# %%
import numpy as np

from timetoalign import TimeUnit
from timetoalign.maps import TicksToQuarters
from timetoalign.timelines import Timeline

# %% [markdown]
# ---
#
# ## Basic Timestamp Generation
#
# Let's start with a simple timeline with events:

# %%
# Create a simple timeline
tl = Timeline(length=10, unit=TimeUnit.seconds, uid="simple")

# Add some events
tl.add_events(
    [
        {"id": "e1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
        {"id": "e2", "temporal_type": "instant", "event_type": "Beat", "instant": 2.5},
        {
            "id": "e3",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 1.0,
            "end": 3.0,
        },
        {"id": "e4", "temporal_type": "instant", "event_type": "Beat", "instant": 5.0},
        {
            "id": "e5",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 6.0,
            "end": 8.0,
        },
    ]
)

print(f"Timeline: {tl}")
print(f"Events: {tl.n_events}")

# %%
# Generate timestamp table
timestamps_df = tl.get_timestamps()
timestamps_df

# %% [markdown]
# ### Understanding the Table
#
# The timestamp table has:
#
# | Column | Description |
# |--------|-------------|
# | `axis` | Root coordinate (the "cross-section" point) |
# | `{timeline_id}` | Local coordinate on each timeline |
#
# For a single timeline, the `axis` and timeline column are identical
# (no offset). But with hierarchies, they differ!

# %% [markdown]
# ---
#
# ## Timestamps with Hierarchies
#
# The real power of timestamps shows with nested timelines:

# %%
# Create a parent timeline: 100 seconds
parent = Timeline(length=100, unit=TimeUnit.seconds, uid="parent")
parent.add_events(
    [
        {"id": "p1", "temporal_type": "instant", "event_type": "Beat", "instant": 0.0},
        {"id": "p2", "temporal_type": "instant", "event_type": "Beat", "instant": 50.0},
    ]
)

# Create child 1: 20 seconds, placed at offset 10 on parent
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

# Create child 2: 15 seconds, placed at offset 60 on parent
child2 = Timeline(length=15, unit=TimeUnit.seconds, uid="child2")
child2.add_events(
    [
        {"id": "c2a", "temporal_type": "instant", "event_type": "Note", "instant": 5.0},
    ]
)

# Build hierarchy
parent.add_child(child1, offset=10)  # child1 spans [10, 30] on parent
parent.add_child(child2, offset=60)  # child2 spans [60, 75] on parent

print(f"Parent: {parent}")
for offset, child in parent.iter_children():
    end = offset.value + child.length.value
    print(f"  {child.id}: [{offset.value}, {end}]")

# %%
# Generate timestamp table for the hierarchy
timestamps_df = parent.get_timestamps()
timestamps_df

# %% [markdown]
# ### Understanding the Hierarchy Timestamps
#
# Let's analyze the output:
#
# - **axis=0.0**: Parent event. child1 (offset=10) → local = 0-10 = -10 →
#   **NaN** (out of bounds). child2 (offset=60) → **NaN**.
# - **axis=10.0**: child1 boundary. child1 → local = 10-10 = **0.0**. child2 → **NaN**.
# - **axis=20.0**: child1 event at local 10. child1 → 20-10 = **10.0**. child2 → **NaN**.
# - **axis=30.0**: child1 boundary (end). child1 → 30-10 = **20.0**
#   (at length, still valid). child2 → **NaN**.
# - **axis=50.0**: Parent event. child1 → **NaN** (50 > 30). child2 → **NaN** (50 < 60).
# - **axis=60.0**: child2 boundary. child1 → **NaN**. child2 → 60-60 = **0.0**.
# - **axis=65.0**: child2 event. child1 → **NaN**. child2 → 65-60 = **5.0**.
# - **axis=75.0**: child2 boundary (end). child2 → 75-60 = **15.0**.
#
# **Key insight:** NaN means the axis coordinate is outside that child's valid range.

# %% [markdown]
# ---
#
# ## Custom Coordinates
#
# Instead of extracting coordinates from events, you can provide explicit coordinates:

# %%
# Query specific coordinates
coords = [0.0, 15.0, 25.0, 50.0, 65.0, 100.0]

timestamps_df = parent.get_timestamps(coordinates=coords)
timestamps_df

# %%
# Works with numpy arrays too (efficient for large queries)
coords = np.linspace(0, 100, 21)  # 0, 5, 10, ..., 100

timestamps_df = parent.get_timestamps(coordinates=coords)
print(f"Generated {len(timestamps_df)} timestamps")
timestamps_df

# %% [markdown]
# ---
#
# ## Boundary Tables
#
# For a quick overview of timeline boundaries (start and end only):

# %%
# Get boundaries only (no events)
boundary_df = parent.get_boundary_table().to_pandas()
boundary_df

# %% [markdown]
# The boundary table shows:
# - Parent boundaries: 0.0 and 100.0
# - child1 boundaries (on parent coords): 10.0 and 30.0
# - child2 boundaries (on parent coords): 60.0 and 75.0

# %% [markdown]
# ---
#
# ## Filtered Timestamps
#
# Generate timestamps for specific event types only:

# %%
# Get timestamps for Note events only
note_df = parent.get_timestamps_filtered({"event_type": "Note"})
print("Note events only:")
note_df

# %%
# Get timestamps for Beat events only
beat_df = parent.get_timestamps_filtered({"event_type": "Beat"})
print("Beat events only:")
beat_df

# %% [markdown]
# ---
#
# ## ConversionMaps in Timestamps
#
# Timestamps can include C-Map conversions as additional columns:

# %%
# Create a timeline in MIDI ticks with events
midi_tl = Timeline(length=1920, unit=TimeUnit.ticks, uid="midi")
midi_tl.add_events(
    [
        {
            "id": "n1",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 0,
            "end": 480,
        },
        {
            "id": "n2",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 480,
            "end": 960,
        },
        {
            "id": "n3",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 960,
            "end": 1440,
        },
        {
            "id": "n4",
            "temporal_type": "interval",
            "event_type": "Note",
            "start": 1440,
            "end": 1920,
        },
    ]
)

# Attach a C-Map: ticks to quarters
t2q = TicksToQuarters(ppq=480)
midi_tl.add_conversion_map(t2q)

print(f"Timeline: {midi_tl}")
print(f"C-Map: {t2q}")

# %%
# Generate timestamps with C-Map column
timestamps_df = midi_tl.get_timestamps(conversion_maps=[t2q])
timestamps_df

# %% [markdown]
# The table now includes:
# - `axis`: Root coordinate (in ticks)
# - `midi`: Local coordinate (same as axis for root timeline)
# - C-Map column: Converted value (in quarters)
#
# This is powerful for seeing the same coordinate in multiple units simultaneously!

# %% [markdown]
# ---
#
# ## Putting It All Together: A Real Example
#
# Let's model a hierarchical timeline with measures and notes, then generate
# timestamps with unit conversion:

# %%
# Create a score timeline in quarters (8 measures of 4/4)
score = Timeline(length=32, unit=TimeUnit.quarters, uid="score")

# Create measure timelines
for i in range(1, 9):
    measure = Timeline(length=4, unit=TimeUnit.quarters, uid=f"m{i}")
    # Add a note at beat 1 of each measure
    measure.add_events(
        [
            {
                "id": f"m{i}_note1",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 0.0,
                "end": 1.0,
            },
            {
                "id": f"m{i}_note2",
                "temporal_type": "interval",
                "event_type": "Note",
                "start": 2.0,
                "end": 3.0,
            },
        ]
    )
    score.add_child(measure, offset=(i - 1) * 4)

print(f"Score: {score}")
print(f"Measures: {score.n_children}")

# %%
# Generate timestamp table - shows all note coordinates across all measures
timestamps_df = score.get_timestamps()

print(f"Total timestamps: {len(timestamps_df)}")
print(f"Columns: {list(timestamps_df.columns)}")

# Show first 15 rows
timestamps_df.head(15)

# %%
# Count how many valid (non-NaN) local coordinates per measure
measure_cols = [f"m{i}" for i in range(1, 9)]
valid_counts = timestamps_df[measure_cols].notna().sum()

print("Events within each measure:")
valid_counts

# %%
# Find all timestamps where measure 3 is active
m3_active = timestamps_df[timestamps_df["m3"].notna()]
print(f"Timestamps within measure 3: {len(m3_active)}")
m3_active

# %% [markdown]
# ---
#
# ## Performance: PyArrow Tables
#
# For large datasets, timestamps are computed efficiently using PyArrow.
# The `get_timestamp_table()` method returns a PyArrow Table directly:

# %%
# Get PyArrow Table (no pandas conversion)
table = score.get_timestamp_table()

print(f"Type: {type(table)}")
print(f"Rows: {table.num_rows}")
print(f"Columns: {table.column_names}")
print("\nSchema:")
print(table.schema)

# %%
# Convert to pandas only when needed
df = table.to_pandas()
df.head()

# %% [markdown]
# ---
#
# ## The Unified TimeStamp Object
#
# While `get_timestamps()` returns a tabular DataFrame, sometimes you need
# to query a **single coordinate** and get all related values. The `TimeStamp`
# object provides this:
#
# - **Lightweight**: Computes coordinates on-demand (no table materialization)
# - **O(log n)**: Uses interpolation maps for fast lookup
# - **Unified**: Same API for Timeline (children) and TimelineGroup (members)

# %%
# Get a single TimeStamp object
ts = parent.get_timestamp(40.0)

{
    "axis": ts.axis,
    "source_id": ts.source_id,
    "is_interpolated": ts.is_interpolated,
}

# %%
# Access child coordinates via subscript
{
    "parent coordinate": ts.axis,
    "child1 coordinate": ts["child1"],  # 40 - 10 = 30
    "child2 coordinate": ts[
        "child2"
    ],  # 40 - 60 = -20 (extrapolated, before child starts)
}

# %%
# Materialize all coordinates at once
ts.to_dict()

# %% [markdown]
# ### TimeIntervalStamp: Intervals Across Timelines
#
# For interval queries (start + end), use `get_interval_stamp()`:

# %%
# Get an interval stamp
interval = parent.get_interval_stamp(20.0, 60.0)

{
    "axis duration": interval.duration,
    "child1 interval": interval["child1"],  # (10, 50)
    "child1 duration": interval.get_duration("child1"),
}

# %%
# Get all intervals at once
interval.zip_intervals()

# %% [markdown]
# ### Why Use TimeStamp Objects?
#
# | Use Case | Method | Returns |
# |----------|--------|--------|
# | Query many coordinates | `get_timestamps()` | DataFrame |
# | Query single coordinate | `get_timestamp(coord)` | `TimeStamp` object |
# | Query single interval | `get_interval_stamp(start, end)` | `TimeIntervalStamp` object |
#
# The `TimeStamp` object is particularly useful when:
# - You need to look up one coordinate at a time (interactive use)
# - You want to convert between timelines without materializing a full table
# - You're implementing coordinate transfer in alignment workflows

# %% [markdown]
# ### Getting Coordinates with Units
#
# Sometimes you need not just the numeric value, but a proper `Coordinate`
# object that carries its unit. The `TimeStamp` object provides methods
# for this:

# %%

# Get a TimeStamp at coordinate 25.0 on parent
ts = parent.get_timestamp(25.0)

# Get the axis as a Coordinate object (with unit)
axis_coord = ts.axis_coordinate
print(f"axis_coordinate: {axis_coord}")
print(f"  Value: {axis_coord.value}")
print(f"  Unit: {axis_coord.unit}")

# %%
# Get a Coordinate for any timeline in the hierarchy
child1_coord = ts.get_coordinate("child1")
print(f"child1 Coordinate: {child1_coord}")
print(f"  Value: {child1_coord.value}")
print(f"  Unit: {child1_coord.unit}")

# Returns None for unknown timelines
unknown = ts.get_coordinate("nonexistent")
print(f"unknown timeline: {unknown}")

# %% [markdown]
# For intervals, use `get_coordinate_interval()` to get a tuple of `Coordinate` objects:

# %%
# Get an interval stamp
interval = parent.get_interval_stamp(15.0, 25.0)

# Get the interval as Coordinate objects
start_coord, end_coord = interval.get_coordinate_interval("child1")
print("child1 interval:")
print(f"  Start: {start_coord} ({start_coord.value} {start_coord.unit})")
print(f"  End: {end_coord} ({end_coord.value} {end_coord.unit})")

# %% [markdown]
# ### Unit Metadata in PyArrow Tables
#
# When you use `get_timestamp_table()`, each column includes unit metadata
# that can be accessed via the PyArrow schema:

# %%
# Get the PyArrow table
table = parent.get_timestamp_table(coordinates=[0.0, 25.0, 50.0])

# Each column has metadata with the unit and timeline_id
for field in table.schema:
    if field.metadata:
        unit = field.metadata.get(b"unit", b"N/A").decode()
        tl_id = field.metadata.get(b"timeline_id", b"N/A").decode()
        print(f"{field.name}: unit={unit}, timeline_id={tl_id}")

# %% [markdown]
# ---
#
# ## Current State and Roadmap
#
# The timestamp system is the foundation for more advanced features:
#
# ### What's Implemented
#
# | Feature | Status | Method |
# |---------|--------|--------|
# | Basic timestamps | Complete | `get_timestamps()` |
# | Hierarchical projection | Complete | Child offset subtraction |
# | Custom coordinates | Complete | `coordinates=` parameter |
# | Boundary tables | Complete | `get_boundary_table()` |
# | Filtered timestamps | Complete | `get_timestamps_filtered()` |
# | C-Map integration | Complete | `conversion_maps=` parameter |
# | PyArrow output | Complete | `get_timestamp_table()` |
# | Unified TimeStamp object | Complete | `get_timestamp()` |
# | Interval stamps | Complete | `get_interval_stamp()` |
# | Coordinate objects with units | Complete | `get_coordinate()`, `axis_coordinate` |
# | Unit metadata in tables | Complete | PyArrow field metadata |
#
# ### Coming Soon
#
# | Feature | Status | Description |
# |---------|--------|-------------|
# | TimelineGroup timestamps | Complete | `get_unified_timestamp()` in Notebook 07 |
# | Alignment Matches | Phase 7 | Cross-timeline event matching |
# | MatchLine | Phase 7 | Ordered match sequences |
# | AlignmentAnchors | Phase 7 | Synchronized timestamp sets |
# | WarpMaps | Phase 7 | Timeline warping based on matches |

# %% [markdown]
# ---
#
# ## Summary
#
# In this tutorial, we learned:
#
# 1. **Timestamps** are cross-section views through timeline hierarchies
# 2. **`get_timestamps()`** extracts coordinates from events and computes local positions
# 3. **Hierarchical projection**: Child local coord = axis coord - child offset
# 4. **NaN values** indicate the axis coordinate is outside a timeline's range
# 5. **Custom coordinates** can be queried with `coordinates=` parameter
# 6. **`get_boundary_table()`** shows timeline boundaries only
# 7. **`get_timestamps_filtered()`** filters events before extracting coordinates
# 8. **C-Maps** can be included as columns for unit conversion
# 9. **PyArrow Tables** provide efficient underlying storage
# 10. **`get_timestamp()`** returns a single `TimeStamp` object for on-demand coordinate lookup
# 11. **`get_interval_stamp()`** returns a `TimeIntervalStamp` for interval queries
# 12. **`get_coordinate()`** returns a `Coordinate` object with proper unit information
# 13. **`axis_coordinate`** property provides the axis as a typed Coordinate
# 14. **PyArrow tables** include unit metadata accessible via `field.metadata[b'unit']`
#
# **Key Takeaway:**
# > Timestamps answer the question: "At this root coordinate, where are we
# > in each nested timeline and in each unit?" They are the foundation for
# > alignment and cross-timeline analysis.

# %% [markdown]
# ## Next Steps
#
# - **07_alignment_basics.ipynb**: Learn how `TimelineGroup` uses the same
#   unified TimeStamp API for coordinate transfer between aligned timelines
# - **Application notebooks**: Real-world alignment workflows
# - **API Reference**: Full documentation of timestamp methods

# %% [markdown]
# ---
#
# ## Exercise 1: Score with Tempo Change
#
# **Task:** Create a 4-measure score (16 quarters) with:
# - A note at beat 1 of each measure
# - A TicksToQuarters C-Map (PPQ=480)
#
# Then generate timestamps in ticks and quarters.
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Create timeline in ticks (4 measures = 16 quarters = 7680 ticks)
# ppq = 480
# score = Timeline(length=7680, unit=TimeUnit.ticks, uid="score")
#
# # Add notes at beat 1 of each measure (0, 1920, 3840, 5760 ticks)
# for i in range(4):
#     score.add_events([{
#         "id": f"m{i+1}_note",
#         "temporal_type": "interval",
#         "event_type": "Note",
#         "start": i * 1920,
#         "end": i * 1920 + 480,
#     }])
#
# # Attach C-Map
# t2q = TicksToQuarters(ppq=ppq)
# score.add_conversion_map(t2q)
#
# # Generate timestamps with C-Map
# df = score.get_timestamps(conversion_maps=[t2q])
# df
# ```
#
# </details>

# %%
# Your solution here


# %% [markdown]
# ---
#
# ## Exercise 2: Query Specific Measure
#
# **Task:** Using the hierarchy from the "Putting It All Together" example,
# find all timestamps where measure 5 is active and show the local coordinate
# in measure 5.
#
# <details>
# <summary>Solution</summary>
#
# ```python
# # Get all timestamps
# df = score.get_timestamps()
#
# # Filter to where m5 is not NaN
# m5_active = df[df["m5"].notna()][["axis", "m5"]]
# m5_active
# ```
#
# </details>

# %%
# Your solution here
