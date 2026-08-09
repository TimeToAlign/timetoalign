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
# # Timeline Groups
#
# ## What you will build
#
# You will put a Rachmaninoff score and performance
# into one {{< glossary TimelineGroup >}}, keeping the events loaded from both
# MIDI files as {{< glossary Event >}}s on two {{< glossary Timeline >}}s. The
# group's first stored pair links score tick 0 to performance
# tick 0, and its last pair links the two endpoints; for a score position
# between those pairs, you will ask the group for the corresponding performance
# {{< glossary Coordinate >}} and see that the answer was interpolated.
#
# ## Before you start
#
# Complete [Loading Real Data](tut04_loading_data.ipynb).

# %%
from fractions import Fraction

from timetoalign import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    Coordinate,
    DiscreteLogicalTimeline,
    GroupTimestamp,
    IdCoordinate,
    InterpolationMap,
    PerformanceMidiLoader,
    ScoreMidiLoader,
    TimelineGroup,
    TimeUnit,
)
from timetoalign.testdata import ensure_data

midi_dir = ensure_data("midi")
score_path = midi_dir / "score" / "rachmaninoff_piano.mid"
performance_path = midi_dir / "performance" / "rachmaninoff_perf.mid"

# %% [markdown]
# ## The problem groups solve
#
# Load the two files with the methods introduced in the previous tutorial.
# Each loader creates a complete timeline. Its {{< glossary Length >}} is
# available through `length`, without inspecting loader metadata or
# MIDI-specific settings.

# %%
score_loader = ScoreMidiLoader.from_file(score_path)
performance_loader = PerformanceMidiLoader.from_file(performance_path)

score = score_loader.create_timeline(uid="rachmaninoff-score")
performance = performance_loader.create_timeline(uid="rachmaninoff-performance")
source_facts = {
    "score extent": score.length,
    "score events": score.n_events,
    "performance extent": performance.length,
    "performance events": performance.n_events,
}
source_facts

# %% [markdown]
# Both results contain the loaded musical events. Their extents are native MIDI
# ticks: ticks in a quantized score and ticks in a performance are separate
# coordinate systems even though they share a unit name, so a value on one is
# not automatically a value on the other.

# %% [markdown]
# ## Building a group
#
# Create an empty group, then add the two loaded timelines. Membership declares
# their {{< glossary Commensurability >}}: the group may relate positions on
# one member to positions on the other.

# %%
group = TimelineGroup(id="rachmaninoff-score-performance")
group.add_timeline(score)
group.add_timeline(performance)

retrieved_score = group.get_timeline(score.id)
members_present = all(
    timeline_id in group.timeline_ids for timeline_id in (score.id, performance.id)
)
group_facts = {
    "are_commensurable": members_present,
    "n_timelines": group.n_timelines,
    "timeline_ids": group.timeline_ids,
    "retrieved timeline": retrieved_score.id,
}
group_facts

# %% [markdown]
# Both IDs are present, `n_timelines` is two, and `get_timeline` returns the
# score by ID. The `are_commensurable` label reports the consequence of that
# membership; the method with that name belongs to the bundle API introduced
# in the next tutorial.

# %% [markdown]
# ## Between the stored pairs
#
# Adding the second member makes an `InterpolationMap` between each direction
# of the pair. Use the group's public `convert` method to apply that map to one
# score position. This interpolation is the second of three coordinate-transfer
# mechanisms in the series, after the exact parent/child offsets introduced in
# [Nesting and Timestamps](tut02_nesting_and_timestamps.ipynb).

# %%
assert group_facts["are_commensurable"]
assert score.n_events == source_facts["score events"]

score_position = Coordinate(6000, TimeUnit.ticks)
performance_position = group.convert(score_position, score.id, performance.id)
map_example = {
    "map class": InterpolationMap,
    "score coordinate": score_position,
    "performance coordinate": performance_position,
}
map_example

# %% [markdown]
# `convert` returns a `Coordinate`, not a bare number, so the target unit and
# the integer required by the {{< glossary Discrete >}} performance timeline
# remain visible.
# `TimelineGroup` does not expose its pairwise map through a public accessor;
# `convert` is the public way to use it. With only endpoint pairs, the map uses
# one constant ratio and cannot represent rubato, fermatas, or other local
# timing differences.

# %% [markdown]
# ## Transferring one coordinate
#
# `get_timestamp_at` returns a {{< glossary TimeStamp >}} across the group.
# Its coordinate accessors expose the queried position and the corresponding
# position on the other member.

# %%
shared_stamp = group.get_timestamp_at(score_position, score.id)
stamp_view = {
    "score coordinate": shared_stamp.get_coordinate(score.id),
    "performance coordinate": shared_stamp.get_coordinate(performance.id),
    "is_interpolated": shared_stamp.is_interpolated,
}
assert stamp_view["performance coordinate"] == map_example["performance coordinate"]
stamp_view

# %% [markdown]
# Both values are unit-bearing coordinates. `is_interpolated` is true because
# score tick 6000 is between the stored start and end pairs rather than on one
# of them; the flag describes how the answer was obtained, not how accurately
# two endpoints model expressive timing.

# %% [markdown]
# ## Transferring several coordinates
#
# `get_timestamps_at` performs the same transfer for a batch. Use integer tick
# positions because ticks are a discrete unit.

# %%
batch_positions = [
    Coordinate(0, TimeUnit.ticks),
    Coordinate(4000, TimeUnit.ticks),
    Coordinate(8000, TimeUnit.ticks),
]
batch_frame = group.get_timestamps_at(
    batch_positions,
    score.id,
)
batch_frame

# %% [markdown]
# Each input score tick appears beside its mapped performance tick. This batch
# result contains plain numbers rather than `Coordinate` objects, but the
# unit-bearing column names identify both discrete coordinate systems and the
# displayed values remain integers.

# %% [markdown]
# ## The row view
#
# `get_timestamp_at_index` retrieves one stored pair by row number. Its result
# is a {{< glossary GroupTimestamp >}}, the second of three stamp types
# introduced across the series, and a view over a boundary row rather than a
# newly estimated position.

# %%
boundary_row = group.get_timestamp_at_index(0)
assert isinstance(boundary_row, GroupTimestamp)
boundary_view = {
    score.id: boundary_row.get_coordinate(score.id),
    performance.id: boundary_row.get_coordinate(performance.id),
    "is_interpolated": boundary_row.is_interpolated,
}
boundary_view

# %% [markdown]
# The mapping displays both unit-bearing coordinates at row zero and shows
# `is_interpolated` as false. Use this row view when you need a stored boundary
# and its coordinates on every member.

# %% [markdown]
# ## The whole table
#
# `group.to_dataframe()` materializes all stored pairs at once. This is useful
# when you want to inspect or export the group's complete tabular view.

# %%
assert boundary_view["is_interpolated"] is False
assert len(batch_frame) == 3
group_frame = group.to_dataframe(units=True)
group_frame

# %% [markdown]
# The two rows are the stored start and end pairs; the three-row batch above
# contained requested positions, not three stored boundaries. Unlike the typed
# scalar accessors, this table currently stores the tick columns as plain
# floating-point numbers. The notebook leaves those library results unchanged
# rather than manufacturing integer or rational values for display.

# %% [markdown]
# ## The represented range
#
# `get_range` reports the part of one member represented in the group. Query
# the loaded score to compare that range with its full extent.

# %%
score_range = group.get_range(score.id)
range_view = {
    "reported range": score_range,
    "timeline extent": retrieved_score.length,
}
range_view

# %% [markdown]
# The numeric range runs from zero to the same endpoint carried by the score's
# unit-bearing `length`. `get_range` currently returns plain floats, including
# for discrete ticks; the adjacent `Coordinate` shows the typed alternative
# without repairing the range behind the reader's back.

# %% [markdown]
# ## Locking a group
#
# Marking a group {{< glossary Locked >}} records that its represented extent
# should not be extended accidentally. Here an attempted end beyond the loaded
# score range is deliberate, so the refusal can be inspected without a noisy
# traceback; the group is unlocked again after the attempt.

# %%
assert score_range is not None
extension_limit = score.length.value + 100
extension_probe = DiscreteLogicalTimeline.from_events(
    [{"id": "probe-end", "event_type": "Boundary", "instant": extension_limit}],
    uid="extension-probe",
)
extension_error = None
group.lock()
try:
    group.add_timeline(
        extension_probe,
        end=IdCoordinate(extension_limit, TimeUnit.ticks, score.id),
    )
except ValueError as exc:
    extension_error = exc
group.unlock()
extension_error

# %% [markdown]
# The `ValueError` shows that the out-of-range boundary was refused before the
# group changed. In the current API, boundary validation happens before a
# lock-specific error can be produced, so this output does not pretend that the
# exception itself proves the lock caused the refusal.

# %% [markdown]
# ## Partial alignment
#
# A member need not cover the whole reference timeline. In this small,
# deliberately constructed example, a 40-second recording covers only score
# quarters 8 through 16; quarter 8 is a stored pair, while quarter 25/2 lies
# between stored pairs.

# %%
assert group.is_locked is False
partial_score = ContinuousLogicalTimeline.from_events(
    [{"id": "score-end", "event_type": "Boundary", "instant": Fraction(16)}],
    uid="sixteen-quarter-score",
)
second_half_recording = ContinuousPhysicalTimeline.from_events(
    [{"id": "recording-end", "event_type": "Boundary", "instant": 40.0}],
    uid="second-half-recording",
)
partial_group = TimelineGroup(id="second-half-only")
partial_group.add_timeline(partial_score)
partial_group.add_timeline(
    second_half_recording,
    start=IdCoordinate(Fraction(8), TimeUnit.quarters, partial_score.id),
    end=IdCoordinate(Fraction(16), TimeUnit.quarters, partial_score.id),
)

second_half_boundary = Coordinate(Fraction(8), TimeUnit.quarters)
between_pairs = Coordinate(Fraction(25, 2), TimeUnit.quarters)
boundary_stamp = partial_group.get_timestamp_at(second_half_boundary, partial_score.id)
between_stamp = partial_group.get_timestamp_at(between_pairs, partial_score.id)
partial_checks = {
    "boundary score": boundary_stamp.get_coordinate(partial_score.id),
    "boundary performance": partial_group.convert(
        second_half_boundary, partial_score.id, second_half_recording.id
    ),
    "boundary is_interpolated": boundary_stamp.is_interpolated,
    "between-pairs score": between_stamp.get_coordinate(partial_score.id),
    "between-pairs performance": partial_group.convert(
        between_pairs, partial_score.id, second_half_recording.id
    ),
    "between-pairs is_interpolated": between_stamp.is_interpolated,
}
partial_checks

# %% [markdown]
# Quarter 8 is the stored start and maps to 0 seconds, so its flag is false.
# The exact rational quarter 25/2 survives the coordinate-returning accessor
# without reconstruction, maps to 22.5 seconds, and has a true interpolation
# flag. With no further stored pairs, the group cannot measure how far this
# straight-line estimate departs from the performed rubato.

# %% [markdown]
# ## What you learned
#
# - You can load event-bearing score and performance timelines and compare their extents.
# - You can build a group, inspect its members, and establish commensurability.
# - You can use the group's interpolation through its public `convert` method.
# - You can transfer one coordinate and identify an interpolated answer.
# - You can transfer a batch of discrete coordinates.
# - You can retrieve a stored pair as a unit-bearing row view.
# - You can inspect the full boundary table and recognize its plain-number representation.
# - You can query a member's represented range.
# - You can lock, test a deliberate out-of-range change, and unlock a group.
# - You can align a recording to only a named part of a score.
#
# ## Next
#
# [Alignment Bundles and MatchClaims](tut06_alignment_bundles.ipynb)
#
# ## Go deeper
#
# [Coordinate Math](../howto/how01_coordinate_math.ipynb) and
# [Create a Note Alignment](../howto/how03_create_note_alignment.ipynb).
