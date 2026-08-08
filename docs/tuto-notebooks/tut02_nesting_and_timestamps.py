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
# # Nesting and Timestamps
#
# ## What you will build
#
# You will build an exact three-level {{< glossary Timeline >}} hierarchy: a
# piece as the {{< glossary Root >}}, a movement inside it, and three phrases
# inside the movement. You will be able to move a {{< glossary Coordinate >}}
# in both directions through every level and ask for one cross-section through
# the whole hierarchy.

# %% [markdown]
# ## Before you start
#
# Complete [Timelines and Coordinates](tut01_timelines_and_coordinates.ipynb)
# first.

# %%
from fractions import Fraction

from timetoalign import TimeIntervalStamp, TimeStamp, TimeUnit
from timetoalign.maps import TicksToQuarters
from timetoalign.timelines import ContinuousLogicalTimeline

# %% [markdown]
# ## 1. Why nesting
#
# A piece contains movements, and a movement contains phrases; putting all
# three on one flat axis discards those relationships. A {{< glossary Child >}}
# is therefore part of the library's model, not merely a display convenience.

# %%
structure = {
    "piece": (Fraction(0), Fraction(20)),
    "movement": (Fraction(3), Fraction(15)),
    "phrases": ["opening", "development", "closing"],
    "phrase_boundaries": [Fraction(0), Fraction(4), Fraction(9), Fraction(12)],
}
structure

# %% [markdown]
# The nested plan keeps the movement's range and its phrase names together.
# We will turn this plan into timelines rather than flattening it into labels
# on the piece axis.

# %% [markdown]
# ## 2. A child at an offset
#
# Place the movement on its {{< glossary Parent >}} at an exact offset. The
# offset is the mapping between their coordinate systems: conversion only adds
# or subtracts it, with no interpolation or numerical error.

# %%
piece = ContinuousLogicalTimeline(length=Fraction(3), uid="piece")
introduction = piece.create_child(length=Fraction(3), uid="introduction")
movement = ContinuousLogicalTimeline(length=Fraction(12), uid="movement")
movement_offset = piece.make_coordinate(structure["movement"][0])
piece.add_child(movement, offset=movement_offset, allow_expansion=True)
coda = ContinuousLogicalTimeline(length=Fraction(5), uid="coda")
piece.append_child(coda)
movement_offset

# %% [markdown]
# `movement_offset` is a coordinate in quarters, so its representation keeps
# both the exact value and the unit visible. `create_child` made the opening
# span, while `append_child` placed the coda directly after the movement and
# expanded the piece to its planned length.

# %% [markdown]
# ## 3. Converting down and up
#
# Lift a movement-local position into the piece, then subtract the same offset
# to return. This is the first of three coordinate-transfer mechanisms in the
# series; {{< glossary TimelineGroup >}} and {{< glossary AlignmentBundle >}}
# transfer arrive in their own tutorials.

# %%
movement_position = movement.make_coordinate(Fraction(5, 2))
piece_position = piece.get_coordinate(
    movement_position.value,
    timeline_id="movement",
)
returned_value = piece_position.value - movement_offset.value
returned_position = movement.get_coordinate(returned_value)
coordinate_round_trip = {
    "movement to piece": piece_position,
    "piece back to movement": returned_position,
    "exact round trip": returned_position == movement_position,
}
coordinate_round_trip

# %% [markdown]
# The local position gains three quarters on the way to the piece and loses
# exactly three on the way back. The final `True` proves that this transfer is
# exact offset arithmetic.

# %% [markdown]
# ## 4. Many children at once
#
# A boundary list is a compact way to divide one timeline into named children:
# *k* + 1 boundaries create *k* children.

# %%
phrase_boundaries = structure["phrase_boundaries"]
phrase_names = structure["phrases"]
phrases = movement.create_children_from_boundaries(
    phrase_boundaries,
    names=phrase_names,
)
listed_children = movement.list_children()
phrase_count = movement.n_children
development = movement.get_child("development")
development_offset = movement.get_child_offset("development")
phrase_inventory = {
    "ids": listed_children,
    "count": phrase_count,
    "retrieved ID": development.id,
    "selected offset": development_offset,
}
phrase_inventory

# %% [markdown]
# Four boundaries produced three named phrase timelines. The inventory shows
# how to list and count direct children, retrieve one by ID, and inspect its
# offset on the movement.

# %% [markdown]
# ## 5. Seeing the shape
#
# A diagram makes containment visible. Its default view follows every level,
# while `depth=1` stops after the piece's direct children.

# %%
full_shape = piece.diagram()
shallow_shape = piece.diagram(depth=1)
print(f"Full hierarchy ({phrase_inventory['count']} phrases):")
print(full_shape)
print("\nOne level below the piece:")
print(shallow_shape)

# %% [markdown]
# The full view reaches the phrases beneath `movement`; the shallow view keeps
# only `introduction`, `movement`, and `coda`. Diagram depth changes the view,
# not the hierarchy itself.

# %% [markdown]
# ## 6. A grandchild
#
# Because the movement sits inside the larger piece and the phrases sit inside
# the movement, a phrase-local position crosses two offsets to reach the root.

# %%
phrase_position = development.make_coordinate(Fraction(3, 2))
root_position = piece.get_coordinate(
    phrase_position.value,
    timeline_id="development",
)
movement_again_value = root_position.value - movement_offset.value
movement_again = movement.get_coordinate(movement_again_value)
phrase_again_value = movement_again.value - development_offset.value
phrase_again = development.get_coordinate(phrase_again_value)
grandchild_round_trip = {
    "development to piece": root_position,
    "piece back to development": phrase_again,
    "both round trips exact": (
        coordinate_round_trip["exact round trip"] and phrase_again == phrase_position
    ),
}
grandchild_round_trip

# %% [markdown]
# The phrase position gains the phrase offset and then the movement offset.
# Subtracting those offsets in reverse order restores the original coordinate;
# the round trip is the proof.

# %% [markdown]
# ## 7. Segment lines
#
# When children tile their parent with no gaps or overlaps, the hierarchy is a
# {{< glossary SegmentLine >}}. Every parent position then belongs to exactly
# one child, so lookup is unambiguous.

# %%
piece_is_segment_line = piece.is_segment_line()
movement_is_segment_line = movement.is_segment_line()
children_here = movement.get_children_at(movement_again)
children_here_ids = [child.id for child in children_here]
development_end_value = development_offset.value + development.length.value
development_end = movement.make_coordinate(development_end_value)
development_slice = movement.get_slice(development_offset, development_end)
slice_child_count = development_slice.n_children
segment_line_view = {
    "piece tiles exactly": piece_is_segment_line,
    "movement tiles exactly": movement_is_segment_line,
    "child at the position": children_here_ids,
    "slice length": development_slice.length,
    "children retained by the slice": slice_child_count,
}
segment_line_view

# %% [markdown]
# Both levels tile exactly. `get_children_at` identifies the one phrase that
# owns the position, while `get_slice` returns an independent, zero-based copy
# of the selected movement span and preserves its child structure.

# %% [markdown]
# ## 8. Regions: naming a span without creating a child
#
# A {{< glossary Region >}} names a range without adding another coordinate
# system. A child is a timeline with its own coordinates; a region is a name
# for an interval of this timeline's coordinates.

# %%
transition = piece.create_region("transition", Fraction(8), Fraction(11))
large_regions = piece.create_regions_from_boundaries(
    [Fraction(0), Fraction(8), Fraction(16), Fraction(20)],
    names=["first part", "second part", "final part"],
)
named_transition = piece.get_region("transition")
regions_here = piece.get_regions_at(root_position)
listed_regions = piece.list_regions()
region_count = piece.n_regions
region_view = {
    "one region": named_transition,
    "boundary regions": large_regions,
    "regions at the position": regions_here,
    "all names": listed_regions,
    "count": region_count,
}
region_view

# %% [markdown]
# The queried position belongs to both `transition` and `second part`, because
# regions may overlap. Rule of thumb: choose a child when the span needs local
# coordinates of its own; choose a region when a name on the current axis is
# enough.

# %% [markdown]
# ## 9. Timestamps
#
# `piece.get_timestamp(coord)` returns a {{< glossary TimeStamp >}}: a
# cross-section answering, “given this position on me, where am I in every
# level below?”

# %%
timestamp = piece.get_timestamp(root_position)
is_timestamp = isinstance(timestamp, TimeStamp)
present_timeline_ids = timestamp.present_timelines
movement_value = timestamp.get("movement")
phrase_coordinate_from_stamp = timestamp.get_coordinate("development")
movement_coordinate_from_stamp = movement.make_coordinate(
    Fraction(movement_value).limit_denominator()
)
phrase_exact_from_stamp = development.make_coordinate(
    Fraction(phrase_coordinate_from_stamp.value).limit_denominator()
)
stamp_is_interpolated = timestamp.is_interpolated
timestamp_view = {
    "is TimeStamp": is_timestamp,
    "present timelines": present_timeline_ids,
    "get('movement')": movement_coordinate_from_stamp,
    "get_coordinate('development')": phrase_exact_from_stamp,
    "is interpolated": stamp_is_interpolated,
}
timestamp_view

# %% [markdown]
# The stamp reads the piece, movement, and requested phrase from one root
# position. `present_timelines` currently reports the source and active direct
# child; `get_coordinate` also reaches the active grandchild and keeps its unit
# visible. This is the first of three stamp types with the same interface and
# progressively wider scope across the series.

# %% [markdown]
# ## 10. Conversion maps show up in the stamp
#
# Attach the tick C-Map from the previous tutorial to the root. A
# {{< glossary ConversionMap >}} then becomes available through the same stamp
# rather than through a separate query.

# %%
ticks_to_quarters = TicksToQuarters(ppq=480)
quarters_to_ticks = ticks_to_quarters.inverse()
piece.add_conversion_map(quarters_to_ticks)
ticks_from_method = timestamp.get_unit(TimeUnit.ticks)
ticks_from_subscript = timestamp["ticks"]
tick_view = {
    "get_unit(TimeUnit.ticks)": ticks_from_method,
    "timestamp['ticks']": ticks_from_subscript,
}
tick_view

# %% [markdown]
# Both access paths return the same integer tick position. This is the payoff
# of the previous tutorial: a conversion map attached to a timeline is already
# part of every timestamp made from that hierarchy.

# %% [markdown]
# ## 11. A span instead of a point
#
# `get_interval_stamp(start, end)` extends the same cross-section idea over a
# span and returns a {{< glossary TimeIntervalStamp >}}.

# %%
interval_start = piece.make_coordinate(Fraction(8))
interval_end = piece.make_coordinate(Fraction(9))
interval_stamp = piece.get_interval_stamp(interval_start, interval_end)
is_interval_stamp = isinstance(interval_stamp, TimeIntervalStamp)
development_interval_values = interval_stamp["development"]
development_interval = tuple(
    development.make_coordinate(Fraction(value).limit_denominator())
    for value in development_interval_values
)
interval_view = {
    "is TimeIntervalStamp": is_interval_stamp,
    "start on piece": interval_start,
    "end on piece": interval_end,
    "development span": development_interval,
}
interval_view

# %% [markdown]
# The result holds a start stamp and an end stamp from the same hierarchy. Its
# subscript view pairs the two phrase-local positions, so one object describes
# the span at both the piece and phrase levels.

# %% [markdown]
# ## What you learned
#
# - You can preserve musical containment instead of flattening every level.
# - You can add children with exact offsets, direct creation, or appending.
# - You can transfer a coordinate down and up with an exact round trip.
# - You can create, list, count, retrieve, and locate many named children.
# - You can inspect the full hierarchy or limit a diagram's depth.
# - You can resolve a grandchild coordinate to the root and invert the path.
# - You can recognize a segment line, find its child at a position, and slice it.
# - You can choose regions for names on the current axis and children for local axes.
# - You can use a timestamp to read coordinates across nested levels.
# - You can read attached unit conversions directly from a timestamp.
# - You can represent the same cross-section over a span with an interval stamp.

# %% [markdown]
# ## Next
#
# [Events on a Timeline](tut03_events.ipynb) adds {{< glossary Event >}} data
# to this hierarchy and builds an event-driven timestamp table from it.
#
# ## Go deeper
#
# - [Coordinate math](../howto/how01_coordinate_math.ipynb)
# - [Manual timeline construction](../howto/how01_manual_timeline_construction.ipynb)
# - [Advanced timestamps](../howto/how01_advanced_timestamps.ipynb)
