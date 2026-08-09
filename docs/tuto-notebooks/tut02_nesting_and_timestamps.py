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
# in both directions through the hierarchy and inspect point and interval
# cross-sections of its coordinate systems.

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
# ## Why nesting
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
# ## Creating a child
#
# Start the piece with one direct child. `create_child` makes a child at the
# beginning of its {{< glossary Parent >}} and returns it.

# %%
piece = ContinuousLogicalTimeline(length=Fraction(3), uid="piece")
initial_piece_length = piece.length
introduction = piece.create_child(length=Fraction(3), uid="introduction")
introduction_offset = piece.get_child_offset("introduction")
created_child_view = {
    "piece length": initial_piece_length,
    "child ID": introduction.id,
    "child offset": introduction_offset,
}
created_child_view

# %% [markdown]
# The piece is deliberately only three quarters long at first. The returned
# `introduction` begins at zero and fills that initial span.

# %% [markdown]
# ## Adding a child at an offset
#
# Place an existing movement timeline three quarters along the piece. The
# offset is measured on the parent's axis, and the relation is
# `parent_position = child_position + child_offset`.

# %%
movement = ContinuousLogicalTimeline(length=Fraction(12), uid="movement")
movement_offset = piece.make_coordinate(structure["movement"][0])
piece.add_child(movement, offset=movement_offset, allow_expansion=True)
piece_length_after_movement = piece.length
added_child_view = {
    "movement offset": movement_offset,
    "piece length before": initial_piece_length,
    "piece length after": piece_length_after_movement,
}
added_child_view

# %% [markdown]
# The movement starts at parent position 3 and ends at 15 quarters. Because
# that exceeds the piece's initial length, `allow_expansion=True` permits the
# parent to grow from 3 to 15 quarters instead of rejecting the child.

# %% [markdown]
# ## Appending a child
#
# `append_child` places a child at the current end of its parent. Append a coda
# to complete the planned twenty-quarter piece.

# %%
coda = ContinuousLogicalTimeline(length=Fraction(5), uid="coda")
piece.append_child(coda)
coda_offset = piece.get_child_offset("coda")
final_piece_length = piece.length
appended_child_view = {
    "previous piece length": piece_length_after_movement,
    "coda offset": coda_offset,
    "final piece length": final_piece_length,
}
appended_child_view

# %% [markdown]
# The coda offset equals the previous piece length, so there is no gap. Its
# five-quarter length extends the piece from 15 to the planned 20 quarters.

# %% [markdown]
# ## Converting down and up
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
# ## Many children at once
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
# ## Seeing the shape
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
# ## A grandchild
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
# ## Segment lines
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
# ## Regions: naming a span without creating a child
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
# ## Timestamps
#
# `piece.get_timestamp(coord)` returns a {{< glossary TimeStamp >}}: a
# cross-section answering, “given this position on the piece, which related
# positions can I query?”

# %%
timestamp = piece.get_timestamp(root_position)
is_timestamp = isinstance(timestamp, TimeStamp)
present_timeline_ids = timestamp.present_timelines
movement_value = timestamp.get("movement")
movement_coordinate_from_stamp = timestamp.get_coordinate("movement")
phrase_coordinate_from_stamp = timestamp.get_coordinate("development")
timestamp_view = {
    "is TimeStamp": is_timestamp,
    "present timelines": present_timeline_ids,
    "get('movement')": movement_value,
    "get(...) result type": type(movement_value).__name__,
    "get_coordinate('movement')": movement_coordinate_from_stamp,
    "get_coordinate('development')": phrase_coordinate_from_stamp,
    "coordinate value type": type(phrase_coordinate_from_stamp.value).__name__,
}
timestamp_view

# %% [markdown]
# These accessors have different scopes and return types. `present_timelines`
# lists the source and active direct child, while `get_coordinate` can traverse
# farther to the active grandchild. Raw `get` returns the float `5.5`; the typed
# accessor returns a `Coordinate` with an exact `Fraction` value and its unit.
# This is the first of three point-stamp types introduced across the series.

# %% [markdown]
# ## Reversing a conversion map
#
# `TicksToQuarters` points from ticks to quarters, but the piece needs a map
# from quarters to ticks. `inverse()` flips the direction of a
# {{< glossary ConversionMap >}} before it is attached.

# %%
ticks_to_quarters = TicksToQuarters(ppq=480)
quarters_to_ticks = ticks_to_quarters.inverse()
piece.add_conversion_map(quarters_to_ticks)
conversion_direction = {
    "original": (ticks_to_quarters.source_unit, ticks_to_quarters.target_unit),
    "inverse": (quarters_to_ticks.source_unit, quarters_to_ticks.target_unit),
}
conversion_direction

# %% [markdown]
# The original map reads `(ticks, quarters)`; its inverse reads
# `(quarters, ticks)`. The inverse therefore accepts positions on the piece and
# produces discrete tick positions.

# %% [markdown]
# ## Conversion maps show up in an existing stamp
#
# Ask the earlier timestamp for ticks after attaching the map. A stamp retains
# its source hierarchy and resolves available maps when an accessor is called.

# %%
ticks_from_method = timestamp.get_unit(TimeUnit.ticks)
ticks_from_subscript = timestamp["ticks"]
tick_view = {
    "get_unit(TimeUnit.ticks)": ticks_from_method,
    "timestamp['ticks']": ticks_from_subscript,
    "result type": type(ticks_from_method).__name__,
}
tick_view

# %% [markdown]
# Both access paths find the newly attached map even though `timestamp` already
# existed. These stamp accessors deliberately return the integer scalar `4080`
# for the discrete tick unit; the requested unit remains explicit in the
# accessor and the output labels.

# %% [markdown]
# ## A span instead of a point
#
# `get_interval_stamp(start, end)` extends the same cross-section idea over a
# span and returns a {{< glossary TimeIntervalStamp >}}, the span variant of
# the first point-stamp rung rather than another rung in the three-part ladder.

# %%
interval_start = piece.make_coordinate(Fraction(8))
interval_end = piece.make_coordinate(Fraction(9))
interval_stamp = piece.get_interval_stamp(interval_start, interval_end)
is_interval_stamp = isinstance(interval_stamp, TimeIntervalStamp)
development_interval_values = interval_stamp["development"]
development_interval_types = tuple(
    type(value).__name__ for value in development_interval_values
)
interval_view = {
    "is TimeIntervalStamp": is_interval_stamp,
    "start on piece": interval_start,
    "end on piece": interval_end,
    "interval_stamp['development']": development_interval_values,
    "endpoint value types": development_interval_types,
}
interval_view

# %% [markdown]
# The result holds a start stamp and an end stamp from the same hierarchy. Its
# subscript view reports the two phrase-local positions as the raw float pair
# `(1.0, 2.0)`; it does not claim exact rational coordinates. The exact
# `Coordinate` objects shown here are the original endpoints on the piece.

# %% [markdown]
# ## What you learned
#
# - You can preserve musical containment instead of flattening every level.
# - You can create a child at the beginning of a parent.
# - You can add an existing child at an exact offset and permit necessary growth.
# - You can append a child at the current end of a parent.
# - You can transfer a coordinate down and up with an exact round trip.
# - You can create, list, count, retrieve, and locate many named children.
# - You can inspect the full hierarchy or limit a diagram's depth.
# - You can resolve a grandchild coordinate to the root and invert the path.
# - You can recognize a segment line, find its child at a position, and slice it.
# - You can choose regions for names on the current axis and children for local axes.
# - You can distinguish a timestamp's raw and typed coordinate accessors.
# - You can reverse a conversion map to obtain the direction a timeline needs.
# - You can read a newly attached unit conversion from an existing timestamp.
# - You can inspect a span across nested levels without disguising raw float values.

# %% [markdown]
# ## Next
#
# [Events on a Timeline](tut03_events.ipynb) adds {{< glossary Event >}} data
# to a timeline like this one and builds an event-driven timestamp table.
#
# ## Go deeper
#
# - [Coordinate math](../howto/how01_coordinate_math.ipynb)
# - [Manual timeline construction](../howto/how01_manual_timeline_construction.ipynb)
# - [Advanced timestamps](../howto/how01_advanced_timestamps.ipynb)
