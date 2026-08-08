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
# **What you will build.** You will build a hand-made
# {{< glossary Timeline >}} in quarter-note units, place beats and notes on it,
# and organise two voices as children. By the end, you will be able to select
# musical content and read its positions throughout the hierarchy.
#
# **Before you start.** Complete
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
# `get_events` retrieves the content, while `n_events` reports how many events
# the timeline holds.

# %%
all_events = tl.get_events()
{
    "is EventData": isinstance(all_events, EventData),
    "n_events": tl.n_events,
    "input rows": len(beat_rows) + len(note_rows),
}

# %% [markdown]
# `all_events` is an `EventData`: a typed, columnar table of events. Its count
# matches the rows added above; the data-model tutorial explains the table in
# full.

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
events_view

# %% [markdown]
# This is a view for human inspection, not the underlying storage. Coordinate
# objects retain their quarter-note unit; `None` in `end` and `duration` means
# those fields do not apply to an instant, while note durations equal
# `end - start`.

# %% [markdown]
# ## Filtering
#
# Filters can select an event type, a half-open coordinate window, or both at
# once.

# %%
notes_by_type = tl.get_events(event_type="Note")
window_start = tl.make_coordinate(Fraction(1))
window_end = tl.make_coordinate(Fraction(4))
events_in_window = tl.get_events(min_coord=window_start, max_coord=window_end)
notes_in_window = tl.get_events(
    event_type="Note",
    min_coord=window_start,
    max_coord=window_end,
)
{
    "notes": len(notes_by_type),
    "events in window": len(events_in_window),
    "notes in window": len(notes_in_window),
}

# %% [markdown]
# The three results build from `event_type`, through `min_coord` and
# `max_coord`, to their combination. Every query method in the library shares
# this filter vocabulary, so learning it once is enough.

# %% [markdown]
# ## One event, one position
#
# Use an event identity for one exact lookup, or a coordinate to ask which
# events are active there.

# %%
window_notes_frame = notes_in_window.to_dataframe(coordinates=True)
selected_id = window_notes_frame.iloc[0]["id"]
selected_event = tl.get_event(selected_id)
window_frame = events_in_window.to_dataframe(coordinates=True)
query_position = window_frame.iloc[0]["start"]
events_at_position = tl.get_events_at(query_position)
{
    "event": {
        "id": selected_event["id"],
        "event_type": selected_event["event_type"],
    },
    "position": query_position,
    "active event ids": [
        event["id"]
        for timeline_events in events_at_position.values()
        for event in timeline_events
    ],
}

# %% [markdown]
# `get_event` returns the row with the chosen identity. At `query_position`,
# `get_events_at` returns both instants exactly there and intervals that cover
# the position, grouped by timeline.

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
root_event_count = tl.n_events
hierarchy_events = tl.get_events(include_children=True)
hierarchy_frame = hierarchy_events.to_dataframe(coordinates=True)
hierarchy_frame["source_timeline"] = hierarchy_frame["source_timeline"].fillna(tl.id)
hierarchy_frame[["id", "temporal_type", "event_type", "start", "source_timeline"]]

# %% [markdown]
# The parent's eight events (`root_event_count`) become ten rows from
# `movement`, `upper_voice`, and `lower_voice`; child coordinates have been
# shifted into the parent's axis. Nesting came first because
# `include_children=True` relies on that hierarchy.

# %% [markdown]
# ## A timestamp for every event
#
# One {{< glossary TimeStamp >}} row can cross-section the entire hierarchy at
# each event's starting coordinate.

# %%
event_positions = hierarchy_frame["start"].tolist()
event_ids = hierarchy_frame["id"].tolist()
timestamp_table = tl.get_timestamp_table(
    coordinates=event_positions,
)
timestamp_rows = tl.to_dataframe(
    coordinates=event_positions,
)
timestamp_rows.index = event_ids
timestamp_rows.index.name = "event_id"
timestamp_rows

# %% [markdown]
# Each index label is an event identity, and its row shows the simultaneous
# coordinate in the parent and both voices; `timestamp_table` is the same
# result in columnar form. This table is complete because both children span
# the parent's full eight quarters, so no event coordinate falls outside a
# child's extent and no `NaN` is produced.

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
# - You can combine event-type and coordinate-range filters.
# - You can retrieve one event by identity or all events active at a coordinate.
# - You can gather events from a parent and its children.
# - You can read one hierarchy-wide timestamp row per queried event.
# - You can distinguish the library's `EventType` vocabulary from project labels.
#
# **Next.** [Loading Real Data](tut04_loading_data.ipynb)
#
# **Go deeper.** See
# [Manual Timeline Construction](../howto/how01_manual_timeline_construction.ipynb)
# and [Advanced Timestamps](../howto/how01_advanced_timestamps.ipynb).
