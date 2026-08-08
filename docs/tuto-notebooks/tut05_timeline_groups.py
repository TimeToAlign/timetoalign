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
# *What you will build* — You will put a Rachmaninoff score in quarters and a
# performance in seconds into one {{< glossary TimelineGroup >}}. You will be
# able to ask about a {{< glossary Coordinate >}} on either timeline, read the
# corresponding position on both, and tell whether the answer is a stored
# boundary or an interpolation.
#
# *Before you start* — Complete [Loading Real Data](tut04_loading_data.ipynb).

# %%
from fractions import Fraction

from timetoalign import (
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    Coordinate,
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
# A score in quarters and a performance in seconds describe the same music,
# but neither timeline knows about the other. The offset arithmetic from the
# nesting tutorial cannot help: expressive timing changes the ratio as well as
# the shift, so we need a way to declare the timelines comparable.

# %%
score_loader = ScoreMidiLoader.from_file(score_path)
performance_loader = PerformanceMidiLoader.from_file(performance_path)

score_ticks = score_loader.create_timeline(uid="rachmaninoff-score-ticks", flatten=True)
score_length = Fraction(score_ticks.length.value, score_loader.ticks_per_beat)
performance_length = performance_loader.metadata["sources"][0]["length_seconds"]

score = ContinuousLogicalTimeline.from_events(
    [{"id": "score-end", "event_type": "Boundary", "instant": score_length}],
    uid="rachmaninoff-score",
)
performance = ContinuousPhysicalTimeline.from_events(
    [
        {
            "id": "performance-end",
            "event_type": "Boundary",
            "instant": performance_length,
        }
    ],
    uid="rachmaninoff-performance",
)
source_extents = {"score": score.length, "performance": performance.length}
source_extents

# %% [markdown]
# The score endpoint is an exact rational number of quarters; the performance
# endpoint is measured in seconds. These coordinates have units, but there is
# not yet any relationship between them.

# %% [markdown]
# ## Building a group
#
# Create an empty group, then add each timeline. This establishes
# {{< glossary Commensurability >}}: a coordinate on either member can now be
# expressed on the other member.

# %%
group = TimelineGroup(id="rachmaninoff-score-performance")
group.add_timeline(score)
group.add_timeline(performance)

retrieved_score = group.get_timeline(score.id)
are_commensurable = all(
    timeline_id in group.timeline_ids for timeline_id in (score.id, performance.id)
)
group_facts = {
    "are_commensurable": are_commensurable,
    "n_timelines": group.n_timelines,
    "timeline_ids": group.timeline_ids,
    "retrieved_timeline": retrieved_score.id,
}
group_facts

# %% [markdown]
# Both IDs are members, the count is two, and `get_timeline` returns the score
# object by ID. Group membership is the declaration that makes this pair
# commensurable.

# %% [markdown]
# ## What adding actually did
#
# Adding the second member made an `InterpolationMap`, a
# {{< glossary ConversionMap >}} that stretches one full extent onto the other.
# With only the two endpoints, it assumes a constant ratio; it therefore cannot
# represent rubato, fermatas, or other local timing differences.

# %%
assert group_facts["are_commensurable"]
extent_map = InterpolationMap(
    source_coords=[Fraction(0), retrieved_score.length.value],
    target_coords=[0.0, performance.length.value],
    source_id=retrieved_score.id,
    target_id=performance.id,
    source_unit=retrieved_score.unit,
    target_unit=performance.unit,
)
score_midpoint = Coordinate(retrieved_score.length.value / 2, TimeUnit.quarters)
mapped_midpoint = Coordinate(extent_map(score_midpoint.value), TimeUnit.seconds)
map_example = {"score midpoint": score_midpoint, "mapped performance": mapped_midpoint}
map_example

# %% [markdown]
# The two endpoints define a straight-line map, so the score midpoint becomes
# the performance midpoint. This is the second coordinate-transfer mechanism
# in the series: unlike the exact offset addition used for nesting, it estimates
# positions between known points by interpolation.

# %% [markdown]
# ## Transferring a coordinate
#
# `get_timestamp_at` asks for one position on one member and returns a
# {{< glossary TimeStamp >}} spanning the group. `get_timestamps_at` performs
# the same transfer for a batch of positions.

# %%
shared_stamp = group.get_timestamp_at(score_midpoint, retrieved_score.id)
stamp_position = Coordinate(shared_stamp.get(performance.id), TimeUnit.seconds)
assert stamp_position == map_example["mapped performance"]

batch_positions = [
    Coordinate(Fraction(0), TimeUnit.quarters),
    Coordinate(Fraction(8), TimeUnit.quarters),
    Coordinate(Fraction(16), TimeUnit.quarters),
]
batch_frame = group.get_timestamps_at(
    batch_positions,
    retrieved_score.id,
)
batch_score_column = f"{score.id} (quarters)"
batch_frame[batch_score_column] = [
    Fraction(value).limit_denominator() for value in batch_frame[batch_score_column]
]
batch_frame

# %% [markdown]
# Each requested score coordinate remains in the quarters column, and the
# corresponding performance coordinate appears beside it in seconds. The
# returned stamp has the interface introduced for nested timelines in the
# timestamps tutorial, but now it spans peer timelines rather than children:
# this is the second rung of coordinate transfer. Its `is_interpolated` value
# reports whether the answer came from a stored row or from the map; it does not
# claim that a two-endpoint model captures expressive timing accurately.

# %% [markdown]
# ## The row view
#
# `get_timestamp_at_index` retrieves one stored boundary by row number. Its
# result is a {{< glossary GroupTimestamp >}}, a view over one row rather than
# a newly estimated position.

# %%
assert shared_stamp.is_interpolated
boundary_row = group.get_timestamp_at_index(0)
assert isinstance(boundary_row, GroupTimestamp)
boundary_row

# %% [markdown]
# This is row zero of the group's timestamp data, so both member coordinates
# are read together and `is_interpolated` is false. Use a row view when you
# need a known boundary and its coordinates on every member.

# %% [markdown]
# ## The whole table
#
# `group.to_dataframe()` materialises every stored boundary at once. This is
# useful when you want to inspect or export the group's complete tabular view.

# %%
group_frame = group.to_dataframe(units=True)
group_score_column = f"{score.id} (quarters)"
group_frame[group_score_column] = [
    Fraction(value).limit_denominator() for value in group_frame[group_score_column]
]
assert group_frame.iloc[boundary_row.row_index][group_score_column] == Fraction(0)
assert len(batch_frame) == 3
group_frame

# %% [markdown]
# There is one row for each stored timestamp and one column for each timeline.
# Here the full alignment has only its start and end boundaries; the three-row
# batch above contained requested positions, not three stored boundaries.

# %% [markdown]
# ## Range and locking
#
# `get_range` reports the part of a member represented in the group. Marking a
# group {{< glossary Locked >}} prevents accidental extension while code is
# relying on its current boundary table.

# %%
score_range_values = group.get_range(score.id)
score_range = tuple(
    Coordinate(Fraction(value).limit_denominator(), TimeUnit.quarters)
    for value in score_range_values
)
assert score_range[-1].value == group_frame.iloc[-1][group_score_column]

group.lock()
locked_state = group.is_locked
group.unlock()
unlocked_state = group.is_locked
range_and_locking = {
    "score range": score_range,
    "after lock": locked_state,
    "after unlock": unlocked_state,
}
range_and_locking

# %% [markdown]
# The score occupies the group's full range. Locking protects that extent from
# being extended by a later addition; unlocking makes intentional changes
# possible again. It is useful to lock a group once downstream analysis assumes
# its set of boundaries is stable.

# %% [markdown]
# ## Partial alignment
#
# A group member need not cover the whole reference timeline. In this small
# example the score is 16 quarters long, while a 40-second recording contains
# only its named second half: quarters 8 through 16.

# %%
assert range_and_locking["after unlock"] is False
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
second_half_middle = Coordinate(Fraction(12), TimeUnit.quarters)
boundary_stamp = partial_group.get_timestamp_at(second_half_boundary, partial_score.id)
middle_stamp = partial_group.get_timestamp_at(second_half_middle, partial_score.id)
partial_checks = {
    "boundary score": second_half_boundary,
    "boundary performance": Coordinate(
        boundary_stamp.get(second_half_recording.id), TimeUnit.seconds
    ),
    "boundary is_interpolated": boundary_stamp.is_interpolated,
    "middle score": second_half_middle,
    "middle performance": Coordinate(
        middle_stamp.get(second_half_recording.id), TimeUnit.seconds
    ),
    "middle is_interpolated": middle_stamp.is_interpolated,
}
partial_checks

# %% [markdown]
# Quarter 8 is the stored start boundary and maps exactly to 0 seconds. Quarter
# 12 is halfway through the covered score span and maps to 20 seconds by
# interpolation. The status flags distinguish those two kinds of answer; with
# no further anchors, the group cannot measure how far the straight-line model
# departs from the performed rubato.

# %% [markdown]
# ## What you learned
#
# - You can state why timelines in unlike units need a group rather than an offset.
# - You can build a group, inspect its members, and establish commensurability.
# - You can explain the constant-ratio assumption behind its interpolation map.
# - You can transfer one coordinate or a batch and identify interpolated answers.
# - You can retrieve a stored boundary as a row view.
# - You can inspect the group's complete timestamp table.
# - You can query a member's range and protect group boundaries by locking them.
# - You can align a recording to only a named part of a score with `start` and `end`.
#
# *Next* — [Alignment Bundles and MatchClaims](tut06_alignment_bundles.ipynb)
#
# *Go deeper* — [Coordinate Math](../howto/how01_coordinate_math.ipynb) and
# [Create a Note Alignment](../howto/how03_create_note_alignment.ipynb).
