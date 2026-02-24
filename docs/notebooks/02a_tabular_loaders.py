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
# # Loading Tabular Data
#
# The fastest way to get music data into TimeToAlign! is through **tabular
# loaders**. If your data is in CSV or TSV format, you're just 3 lines of
# code away from analysis.
#
# **What you'll learn:**
# - Load music annotations from TSV/CSV files
# - Access event counts, coordinate ranges, and metadata
# - Create timelines from loaded data
# - Create custom loaders with different `extra_columns` strategies
# - Use `Field` for nested JSON column access
#
# **Time:** 15 minutes

# %% [markdown]
# ## TL;DR
#
# ```python
# from timetoalign.loader.tabular import Ms3Loader
#
# loader = Ms3Loader()
# loader.load("beethoven.notes.tsv")
#
# df = loader.events.to_pandas()       # Get as DataFrame
# timeline = loader.create_timeline()  # Create Timeline
# ```

# %% [markdown]
# ## Setup

# %%
import os
from pathlib import Path

# Specimen directories - relative to the notebook's location
_notebook_dir = Path(os.getcwd()).resolve()
SPECIMENS = _notebook_dir.parent.parent.parent / "dashboard" / "specimens"
BEETHOVEN = SPECIMENS / "beethoven_woo71"
THORESEN = SPECIMENS / "thoresen"

# Available files
{
    "Beethoven files": [f.name for f in BEETHOVEN.glob("WoO71.*.tsv")],
    "Thoresen files": [f.name for f in THORESEN.glob("*.tsv")],
}

# %% [markdown]
# ## Loading Notes from TSV
#
# The `Ms3Loader` handles TSV files exported from the
# [ms3](https://github.com/johentsch/ms3) parser, which processes MuseScore
# files.
#
# **Three lines of code:**

# %%
from timetoalign.loader.tabular import Ms3Loader  # noqa: E402

loader = Ms3Loader()
loader.load(BEETHOVEN / "WoO71.notes.tsv")

f"{len(loader.events):,} notes loaded"

# %% [markdown]
# ## Converting to pandas
#
# Use `to_pandas()` to get a DataFrame with clean coordinate values:

# %%
loader.events.to_pandas().head()

# %% [markdown]
# ## Quick Statistics
#
# The loader provides immediate access to summary information:

# %%
{
    "event_count": len(loader.events),
    "coordinate_range": loader.events.coordinate_range(),
    "unit": str(loader.unit),
    "number_type": str(loader.number_type),
}

# %% [markdown]
# ## Creating Timelines
#
# TimeToAlign! represents temporal data as **Timelines**:

# %%
timeline = loader.create_timeline(uid="beethoven_notes")
timeline

# %% [markdown]
# ## Custom Loaders for Non-Standard Formats
#
# For files that don't match the ms3 format, create a custom loader
# by subclassing `TsvLoader` or `CsvLoader`.
#
# Let's load the Thoresen annotations file which has a different column structure:

# %%
import pandas as pd  # noqa: E402

pd.read_csv(THORESEN / "thoresen_test.tsv", sep="\t", nrows=3)

# %% [markdown]
# ### Strategy 1: Simplest Case (No Extra Columns)
#
# The simplest custom loader just maps the core coordinate columns.
# No `extra_columns` means only the base event fields are loaded:

# %%
from timetoalign.core import NumberType, TimeUnit  # noqa: E402
from timetoalign.loader.tabular import TsvLoader  # noqa: E402


class ThoresenMinimalLoader(TsvLoader):
    """Minimal loader - only core event fields."""

    id_column = "event_id"
    start_column = "start_time_sec"
    duration_column = "duration_sec"
    event_type_column = "event_type"
    name_column = "description"

    _default_unit = TimeUnit.seconds
    coordinate_type = NumberType.float


minimal = ThoresenMinimalLoader()
minimal.load(THORESEN / "thoresen_test.tsv")
minimal.events.to_pandas()


# %% [markdown]
# ### Strategy 2: Auto-Infer All Columns
#
# Set `extra_columns = True` to automatically include all remaining columns with inferred types:


# %%
class ThoresenAutoLoader(TsvLoader):
    """Auto-infer all remaining columns."""

    id_column = "event_id"
    start_column = "start_time_sec"
    duration_column = "duration_sec"
    event_type_column = "event_type"
    name_column = "description"

    _default_unit = TimeUnit.seconds
    coordinate_type = NumberType.float

    # Include ALL remaining columns with inferred types
    extra_columns = True


auto = ThoresenAutoLoader()
auto.load(THORESEN / "thoresen_test.tsv")
auto.events.to_pandas()


# %% [markdown]
# ### Strategy 3: Explicit Columns with Types
#
# Use a dict to specify exactly which columns to include and their types:


# %%
class ThoresenTypedLoader(TsvLoader):
    """Explicit columns with types."""

    id_column = "event_id"
    start_column = "start_time_sec"
    duration_column = "duration_sec"
    event_type_column = "event_type"
    name_column = "description"

    _default_unit = TimeUnit.seconds
    coordinate_type = NumberType.float

    # Explicit columns with types
    extra_columns = {
        "image_filename": str,
        "graphical_element_id": int,
    }


typed = ThoresenTypedLoader()
typed.load(THORESEN / "thoresen_test.tsv")
typed.events.to_pandas()

# %% [markdown]
# ## Nested JSON Column Access with Field
#
# The Thoresen data has a `rect_coords_json` column containing pixel coordinates as JSON:
# ```json
# {"x": 10, "y": 90, "width": 148, "height": 55}
# ```
#
# Use `Field("column", "nested_field")` to access nested fields directly.
# TimeToAlign! automatically parses JSON when needed:

# %%
from timetoalign.loader import ComputedField, Field  # noqa: E402


class ThoresenGraphicalLoader(TsvLoader):
    """Loader using PIXEL coordinates from nested JSON.

    Field automatically parses JSON columns when accessing nested fields.
    """

    # Use nested fields directly - JSON is parsed automatically
    start_column = Field("rect_coords_json", "x")
    end_column = ComputedField(
        "end", formula="rect_coords_json.x + rect_coords_json.width"
    )

    _default_unit = TimeUnit.pixels
    coordinate_type = NumberType.float
    default_event_type = "Rectangle"


graphical = ThoresenGraphicalLoader()
graphical.load(THORESEN / "thoresen_test.tsv")

{
    "unit": str(graphical.unit),
    "coordinate_range": graphical.events.coordinate_range(),
}

# %% [markdown]
# ### Two Coordinate Systems from One File
#
# The same TSV file can create timelines in different coordinate systems:

# %%
# Physical timeline (seconds)
typed.events.to_pandas()

# %%
# Graphical timeline (pixels)
graphical.events.to_pandas()

# %% [markdown]
# ### Creating Timelines
#
# Use `create_timeline()` to convert loaded events into a Timeline object.
# The `diagram()` method shows an ASCII visualization:

# %%
# Create Physical Timeline (seconds)
physical_tl = typed.create_timeline(uid="thoresen_physical")
physical_tl

# %%
physical_tl.get_timestamp_table()

# %%
# Create Graphical Timeline (pixels)
graphical_tl = graphical.create_timeline(uid="thoresen_graphical")
graphical_tl

# %% [markdown]
# **Note:** Both timelines represent the same 11 events, but in different coordinate systems:
# - **Physical:** `0 - 142.5 seconds` (audio time)
# - **Graphical:** `10 - 760 pixels` (image coordinates)
#
# TimeToAlign! uses these dual representations to align graphical annotations with audio.

# %% [markdown]
# ---
#
# ## Advanced Features
#
# The following sections cover advanced features for complex data loading scenarios.

# %% [markdown]
# ### CoordinateField: Loading Multiple Coordinate Columns
#
# Sometimes your data contains coordinates in **multiple systems** (e.g.,
# seconds AND pixels). Use `CoordinateField` to parse any column as a
# proper coordinate struct with unit metadata, enabling:
#
# - Multiple coordinate columns in one EventData
# - C-Map creation from loaded coordinate pairs
# - Full precision preservation with Fraction number type
# - Proper unit tracking per column (not just the primary unit)
#
# The Thoresen data has both time coordinates (seconds) and pixel
# coordinates (in JSON):

# %%
from timetoalign.core import NumberType, TimeUnit  # noqa: E402, F811
from timetoalign.loader import CoordinateField, Field  # noqa: E402, F811
from timetoalign.loader.tabular import TsvLoader  # noqa: E402, F811


class MultiCoordinateLoader(TsvLoader):
    """Loader that extracts multiple coordinate columns.
    \n    Primary coordinates in seconds, with additional x_pixels column.
    This enables creating C-Maps between coordinate systems.
    """

    # Primary coordinates: seconds
    id_column = "event_id"
    start_column = "start_time_sec"
    duration_column = "duration_sec"
    event_type_column = "event_type"

    _default_unit = TimeUnit.seconds
    coordinate_type = NumberType.float

    # Extra columns - mix of regular and coordinate columns
    extra_columns = [
        "image_filename",  # Regular string column
        # CoordinateField extracts x as a proper coordinate struct
        CoordinateField(
            "x_pixels",
            source=Field("rect_coords_json", "x"),  # Nested JSON access
            unit=TimeUnit.pixels,
        ),
    ]


multi = MultiCoordinateLoader()
multi.load(THORESEN / "thoresen_test.tsv")

# The x_pixels column is now a proper coordinate with unit metadata
multi.events.to_pandas()[["id", "start", "end", "x_pixels", "image_filename"]]

# %%
multi.events.table.schema

# %% [markdown]
# ### create_cmap(): Building Conversion Maps
#
# With dual coordinates loaded, you can create **Conversion Maps** (C-Maps)
# to convert between coordinate systems. The loader's `create_cmap()` method
# supports:
#
# - **TableMap** (default): Point-to-point mapping with interpolation
# - **LinearMap**: Fits a linear function `y = ax + b`
# - **ScalarMap**: Fits a pure scaling `y = ax`

# %%
from timetoalign.maps import LinearMap  # noqa: E402

# Create a TableMap from start (seconds) -> x_pixels
table_cmap = multi.create_cmap("start", "x_pixels")

# Create a LinearMap (fits y = ax + b)
linear_cmap = multi.create_cmap("start", "x_pixels", map_type=LinearMap)

# Compare the two map types
{
    "TableMap": str(table_cmap),
    "LinearMap": str(linear_cmap),
    "5.0 seconds (TableMap)": f"{table_cmap(5.0):.1f} pixels",
    "5.0 seconds (LinearMap)": f"{linear_cmap(5.0):.1f} pixels",
}

# %% [markdown]
# ### group_by: Creating Child Timelines from Column Values
#
# When your data contains events from **multiple sources** (e.g., multiple
# images, pages, or tracks), use `group_by` to automatically create child
# timelines for each unique value.
#
# The Thoresen data has events from 5 different image files:

# %%
# Using the earlier 'auto' loader which has image_filename
from timetoalign.timelines import create_timeline  # noqa: E402

# Create timeline grouped by image filename
grouped_tl = create_timeline(auto, group_by="image_filename")
grouped_tl

# %%
# Each child timeline represents events from one image
{
    "parent_id": grouped_tl.id,
    "n_children": grouped_tl.n_children,
    "children": {
        child.id: len(child._events) if child._events else 0
        for _, child in grouped_tl.iter_children()
    },
}

# %% [markdown]
# ---
#
# ## Summary
#
# ### Extra Columns Strategies
#
# | Strategy | Syntax | Use Case |
# |----------|--------|----------|
# | None | `extra_columns` not set | Only core event fields |
# | Auto-infer | `extra_columns = True` | Include all columns, infer types |
# | Explicit dict | `extra_columns = {"col": type}` | Specific columns with types |
# | With CoordinateField | `extra_columns = [CoordinateField(...)]` | C-Maps |
#
# ### Key API
#
# ```python
# # Load
# loader = Ms3Loader()
# loader.load("file.tsv")
#
# # Access
# df = loader.events.to_pandas()
# timeline = loader.create_timeline()
#
# # Custom loader with explicit columns
# class MyLoader(TsvLoader):
#     start_column = "onset"
#     duration_column = "dur"
#     extra_columns = {"pitch": int, "velocity": int}
#
# # Nested JSON field access (auto-parses JSON)
# from timetoalign.loader import Field, ComputedField
#
# class GraphicalLoader(TsvLoader):
#     start_column = Field("rect_json", "x")  # JSON parsed automatically
#     end_column = ComputedField("end", formula="rect_json.x + rect_json.width")
#
# # Multiple coordinate columns with CoordinateField
# from timetoalign.loader import CoordinateField
#
# class MyCoordinateLoader(TsvLoader):
#     start_column = "time_sec"
#     extra_columns = [
#         CoordinateField("x_pixels", source="x_px", unit=TimeUnit.pixels),
#     ]
#
# # Create C-Maps from loaded coordinates
# cmap = loader.create_cmap("start", "x_pixels")  # TableMap (default)
# cmap = loader.create_cmap("start", "x_pixels", map_type=LinearMap)
#
# # Group events by column value into child timelines
# timeline = create_timeline(loader, group_by="image_filename")
# ```
#
# > **Key Takeaway:** Tabular loaders provide a declarative way to map CSV/TSV
# > columns to TimeToAlign! events. Use `Field` for nested JSON access,
# > `CoordinateField` for additional coordinate columns with unit tracking,
# > and `group_by` for multi-source timelines.
