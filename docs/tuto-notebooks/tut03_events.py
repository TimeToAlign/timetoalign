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
# # Events on a Timeline
#
# ## What you will build
#
# You will build a hand-made
# {{< glossary Timeline >}} in quarter-note units, place beats and notes on it,
# and organise two voices as children. By the end, you will be able to select
# musical content and read its positions throughout the hierarchy.
#
# ## Before you start
#
# Complete
# [Nesting and Timestamps](tut02_nesting_and_timestamps.ipynb) first.

# %%
from fractions import Fraction

from timetoalign import (
    ContinuousLogicalTimeline,
    EventData,
    EventType,
    TimeUnit,
)

# %% [markdown]
# ## A timeline is an axis; events are what sits on it
#
# Everything so far described **where** something happens. An
# {{< glossary Event >}} records **what** happens at a position or over a span.
# `from_events` builds a timeline directly from event rows and infers the
# timeline's extent from them.

# %%
tl = ContinuousLogicalTimeline.from_events(
    [],
    unit=TimeUnit.quarters,
    uid="movement",
)
axis_origin = tl.make_coordinate(Fraction(0))
axis_origin

# %% [markdown]
# `axis_origin` is a position in quarters, but the empty axis says nothing
# musical yet. The next sections add content without changing the unit.

# %% [markdown]
# ## What an event is
#
# An event has an identity, a temporal type (an {{< glossary Instant >}} or a
# {{< glossary TimeInterval >}}), an event type, and one or more
# {{< glossary Coordinate >}}s.

# %%
beat_rows = [
    {"event_type": "Beat", "instant": axis_origin},
    {"event_type": "Beat", "instant": Fraction(2)},
    {"event_type": "Beat", "instant": Fraction(4)},
    {"event_type": "Beat", "instant": Fraction(8)},
]
tl.add_events(beat_rows, allow_expansion=True)
beat_rows

# %% [markdown]
# Each input row names a `Beat` and its instant. Because `id` and
# `temporal_type` are absent, `add_events` creates an identity and infers the
# instant temporal type; `allow_expansion` lets the initially empty axis grow
# to the last beat.

# %% [markdown]
# ## Interval events
#
# A note occupies a span, so its row supplies `start` and `end` rather than one
# `instant`.

# %%
note_rows = [
    {
        "event_type": "Note",
        "pitch": "C4",
        "start": Fraction(0),
        "end": Fraction(1),
    },
    {
        "event_type": "Note",
        "pitch": "E♭4",
        "start": Fraction(1),
        "end": Fraction(5, 2),
    },
    {
        "event_type": "Note",
        "pitch": "G4",
        "start": Fraction(3),
        "end": Fraction(5),
    },
    {
        "event_type": "Note",
        "pitch": "C5",
        "start": Fraction(6),
        "end": Fraction(15, 2),
    },
]
tl.add_events(note_rows)
note_rows

# %% [markdown]
# These are interval rows: the library infers their temporal type and computes
# each `duration` as `end - start`. The stored durations will be visible in the
# table below; they do not need to be repeated in the input.

# %% [markdown]
# ## Getting them back
#
# `EventData` is the library's event table: for now, think of it as a pandas-like
# table whose time fields know their unit. `get_events` retrieves that table,
# while `n_events` reports how many events the timeline holds.

# %%
all_events = tl.get_events()
{
    "is EventData": isinstance(all_events, EventData),
    "n_events": tl.n_events,
    "input rows": len(beat_rows) + len(note_rows),
}

# %% [markdown]
# `all_events` is an `EventData`, and its count matches the rows added above.
# Tutorial 8 explains how this table is stored; here, its familiar table
# behaviour is enough.

# %% [markdown]
# ## Looking at it
#
# For inspection, `to_dataframe` presents the event table in familiar pandas
# form.

# %%
events_frame = all_events.to_dataframe(coordinates=True)
events_view = events_frame[
    ["id", "temporal_type", "event_type", "start", "end", "duration"]
]
events_view.style.format({"start": repr, "end": repr, "duration": repr})

# %% [markdown]
# This is a view for human inspection, not the underlying storage. Coordinate
# objects retain their quarter-note unit; `None` in `end` and `duration` means
# those fields do not apply to an instant, while note durations equal
# `end - start`.

# %% [markdown]
# ## Filtering
#
# Filters can select an event type and an onset window together. The window
# includes events whose `start` is at least `min_coord` and strictly less than
# `max_coord`; it does not test overlap or containment.

# %%
window_start = tl.make_coordinate(Fraction(1))
window_end = tl.make_coordinate(Fraction(4))
events_in_window = tl.get_events(min_coord=window_start, max_coord=window_end)
notes_in_window = tl.get_events(
    event_type="Note",
    min_coord=window_start,
    max_coord=window_end,
)
window_events_frame = events_in_window.to_dataframe(coordinates=True)
window_event_view = window_events_frame[["id", "event_type", "start", "end"]]
window_event_view

# %% [markdown]
# The returned starts are 1, 2, and 3 quarters: the event at 4 quarters is
# excluded. The interval ending at 5 quarters is included because selection is
# by onset; an event does not need to be contained within the window. The C4
# note ending at 1 quarter is absent because its start is below the minimum.
# `notes_in_window` applies the same bounds together with `event_type="Note"`;
# the next lookup reuses that result.

# %% [markdown]
# ## One event by identity
#
# `get_event` uses an event identity for one exact lookup. Choose an identity
# from the filtered notes, then retrieve its row from the timeline.

# %%
window_notes_frame = notes_in_window.to_dataframe(coordinates=True)
selected_id = window_notes_frame.iloc[0]["id"]
selected_event = tl.get_event(selected_id)
selected_event_view = {
    "id": selected_event["id"],
    "event_type": selected_event["event_type"],
    "pitch": selected_event["pitch"],
}
selected_event_view

# %% [markdown]
# `get_event` returns one event row, shown here through its identifying and
# descriptive fields. It is a different return shape from the grouped lookup
# in the next section.

# %% [markdown]
# ## Events active at one position
#
# `get_events_at` asks which events are active at a coordinate. Use 2 quarters,
# where an instant and an interval coincide, so both rules are visible.

# %%
query_position = tl.make_coordinate(Fraction(2))
events_at_position = tl.get_events_at(query_position)
position_lookup = {
    "position": query_position,
    "events by timeline": events_at_position,
}
position_lookup

# %% [markdown]
# The top-level position retains its quarter-note unit. The nested dictionary
# keeps the grouping returned by `get_events_at`: its `movement` list contains
# the beat exactly at 2 quarters and the note whose interval covers that
# position. Child timelines will add further keys once they exist.

# %% [markdown]
# ## Events in the hierarchy
#
# A {{< glossary Child >}} can hold its own events. Two full-length voice
# children let the parent gather content from every level in one query.

# %%
upper_voice = tl.create_child(length=Fraction(8), uid="upper_voice")
lower_voice = tl.create_child(length=Fraction(8), uid="lower_voice")
upper_voice.add_events(
    [
        {
            "id": "upper:a4",
            "event_type": "Note",
            "pitch": "A4",
            "start": Fraction(2),
            "end": Fraction(3),
        }
    ]
)
lower_voice.add_events(
    [
        {
            "id": "lower:c3",
            "event_type": "Note",
            "pitch": "C3",
            "start": Fraction(5),
            "end": Fraction(6),
        }
    ]
)
hierarchy_events = tl.get_events(include_children=True)
hierarchy_frame = hierarchy_events.to_dataframe(coordinates=True)
hierarchy_view = hierarchy_frame[
    ["id", "temporal_type", "event_type", "start", "source_timeline"]
]
hierarchy_view

# %% [markdown]
# The eight rows with a missing `source_timeline` belong to the parent itself:
# that provenance field is populated only when an event is gathered from a
# child. The two labelled child rows bring the total to ten, and their
# coordinates have been shifted into the parent's axis. The missing values are
# therefore the library's convention, not unknown event ownership.

# %% [markdown]
# ## A timestamp for every event
#
# One {{< glossary TimeStamp >}} row can cross-section the entire hierarchy at
# each event's starting coordinate. `get_timestamp_table` provides the
# low-level PyArrow form of those rows.

# %%
event_positions = hierarchy_frame["start"].tolist()
timestamp_table = tl.get_timestamp_table(
    coordinates=event_positions,
)
timestamp_table

# %% [markdown]
# Rows come back in the same order as `event_positions`, including repeated
# positions. `axis` is the queried position on the parent reference axis;
# `movement`, `upper_voice`, and `lower_voice` are the simultaneous local
# coordinates. The low-level Arrow table stores these columns as doubles, so it
# does not return `Coordinate` or `Fraction` objects on this path. All four
# columns are complete because both children span the parent's full eight
# quarters.

# %% [markdown]
# ## `EventType`
#
# The library defines the temporal vocabulary, while a project supplies its
# own descriptive event-type labels such as `Beat` and `Note`.

# %%
event_labels = sorted(events_frame["event_type"].unique())
type_vocabulary = {
    "library temporal types": [EventType.instant, EventType.interval],
    "event labels used here": event_labels,
    "one timestamp row per queried event": timestamp_table.num_rows
    == len(hierarchy_events),
}
type_vocabulary

# %% [markdown]
# `EventType.instant` and `EventType.interval` are the two temporal shapes that
# `add_events` inferred. The strings in the `event_type` field describe the
# musical content and come from the researcher, file format, or loader.

# %% [markdown]
# ## What you learned
#
# - You can distinguish a timeline axis from the events placed on it.
# - You can add instant events while letting identity and temporal type be inferred.
# - You can add interval events with exact starts, ends, and derived durations.
# - You can retrieve an `EventData` and count a timeline's events.
# - You can inspect event content as a pandas view without mistaking it for storage.
# - You can combine event-type and half-open onset filters.
# - You can retrieve one event by identity.
# - You can preserve timeline grouping when finding events active at a coordinate.
# - You can gather events from a parent and its children while reading provenance.
# - You can read the axis and hierarchy coordinates in a timestamp table.
# - You can distinguish the library's `EventType` vocabulary from project labels.
#
# ## Next
#
# [Loading Real Data](tut04_loading_data.ipynb)
#
# ## Go deeper
#
# See
# [Manual Timeline Construction](../howto/how01_manual_timeline_construction.ipynb)
# and [Advanced Timestamps](../howto/how01_advanced_timestamps.ipynb).
