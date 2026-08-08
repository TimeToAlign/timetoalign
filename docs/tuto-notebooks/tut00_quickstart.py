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
# # Quickstart
#
# One piece of music can exist at once as a recording, as notation, and as
# images on a page. Each representation has its own
# {{< glossary Coordinate >}} system and units.
#
# | {{< glossary Domain >}} | Continuous | {{< glossary Discrete >}} |
# |---|---|---|
# | Physical: recording | seconds | samples |
# | Logical: notation | quarters | ticks |
# | Graphical: page image | centimetres | pixels |
#
# TimeToAlign! represents these coordinate systems and the relationships
# between them. It lets you place musical information on the appropriate axis,
# then ask where the same instant or event lies in another representation.
#
# ## What you will build
#
# In five minutes, you will assemble a 30-second audio example, add structure
# and events, connect it to a loaded score, and glimpse repeats, fields, and
# pitch spelling. You will finish with a map to the tutorial that explains each
# idea in full; the setup also locates the one small score used in the loading
# preview.

# %%
from fractions import Fraction

from timetoalign import MatchClaim, PartituraLoader
from timetoalign.core import EnharmonicPitch, FlowMode, SpecificPitch
from timetoalign.testdata import ensure_data
from timetoalign.timelines import (
    BeatGrid,
    ContinuousPhysicalTimeline,
    Flow,
    FlowMap,
    PlaythroughSection,
    TimelineGroup,
)

vienna = ensure_data("vienna_1x22")

# %% [markdown]
# ## 1. Timelines and Coordinates
#
# A {{< glossary Timeline >}} is a measured axis for one representation of the
# music. A `Coordinate` places a value on that axis and keeps its unit attached.

# %%
audio = ContinuousPhysicalTimeline(length=30.0, uid="audio")
audio_coordinate = audio.make_coordinate(12.5)
audio_coordinate

# %% [markdown]
# The result is 12.5 seconds on a 30-second audio axis, displayed with its unit.
# Open [Timelines and Coordinates](tut01_timelines_and_coordinates.ipynb) to
# build and inspect timelines carefully.

# %% [markdown]
# ## 2. Nesting and Timestamps
#
# Nested timelines are {{< glossary Child >}} objects. A
# {{< glossary TimeStamp >}} reads one position across the parent and every
# child present there.

# %%
left_channel = ContinuousPhysicalTimeline(length=30.0, uid="left-channel")
right_channel = ContinuousPhysicalTimeline(length=30.0, uid="right-channel")
audio.add_child(left_channel, offset=0.0)
audio.add_child(right_channel, offset=0.0)
audio_timestamp = audio.get_timestamp(audio_coordinate)
audio_timestamp

# %% [markdown]
# This timestamp shows the same 12.5-second position on the audio axis and both
# channel children. Open [Nesting and Timestamps](tut02_nesting_and_timestamps.ipynb)
# to learn how nested coordinate systems work.

# %% [markdown]
# ## 3. Events on a Timeline
#
# An {{< glossary Event >}} records something that happens at an instant or
# over an interval. Here three labelled cues become part of the audio timeline.

# %%
audio.add_events(
    [
        {
            "id": "opening",
            "event_type": "Cue",
            "temporal_type": "interval",
            "start": 0.0,
            "end": 2.0,
        },
        {
            "id": "theme",
            "event_type": "Cue",
            "temporal_type": "interval",
            "start": 8.0,
            "end": 14.0,
        },
        {
            "id": "coda",
            "event_type": "Cue",
            "temporal_type": "interval",
            "start": 25.0,
            "end": 30.0,
        },
    ]
)
audio_events = audio.get_events(event_type="Cue")
audio_events

# %% [markdown]
# The event store contains the three non-empty cue intervals in seconds.
# Open [Events on a Timeline](tut03_events.ipynb) to add, filter, and retrieve
# musical events.

# %% [markdown]
# ## 4. Loading Real Data
#
# Loaders turn common research formats into the same kind of timeline. This
# single loading expression reads a small MusicXML score prepared in the setup.

# %%
score = PartituraLoader.from_file(vienna / "Chopin_op10_no3.musicxml").create_timeline(
    uid="score"
)
score

# %% [markdown]
# The result is a score timeline in quarters, with its notes and measures ready
# to inspect. Open [Loading Real Data](tut04_loading_data.ipynb) to choose a
# loader and understand what it creates.

# %% [markdown]
# ## 5. Timeline Groups
#
# A {{< glossary TimelineGroup >}} relates commensurable timelines so that a
# position on one can be transferred to another. Here their full extents are
# treated as corresponding.

# %%
group = TimelineGroup(id="quickstart", timelines=[audio, score])
score_value = group.convert(audio_coordinate, source=audio.id, target=score.id)
score_fraction = Fraction(score_value).limit_denominator()
score_coordinate = score.make_coordinate(score_fraction)
coordinate_pair = {"audio": audio_coordinate, "score": score_coordinate}
coordinate_pair

# %% [markdown]
# The dictionary keeps both results as unit-bearing coordinates: 12.5 seconds
# maps to an exact rational position in score quarters. Open
# [Timeline Groups](tut05_timeline_groups.ipynb) to control these relationships.

# %% [markdown]
# ## 6. Alignment Bundles
#
# An {{< glossary AlignmentBundle >}} collects broader alignment evidence; its
# basic link is a {{< glossary MatchClaim >}}. A claim can expose a
# {{< glossary MatchStamp >}} for the corresponding positions.

# %%
claim = MatchClaim.from_events(
    {"start": coordinate_pair["audio"].value},
    audio.id,
    {"start": coordinate_pair["score"].value},
    score.id,
    unit_a=audio.unit,
    unit_b=score.unit,
)
matchstamp = claim.get_matchstamp(from_graph=False)
alignment_preview = {"matchstamp": matchstamp, "positions": coordinate_pair}
alignment_preview

# %% [markdown]
# The matchstamp is shown beside the two unit-bearing positions for its claimed
# musical instant. Open
# [Alignment Bundles](tut06_alignment_bundles.ipynb) to assemble and query
# larger alignments.

# %% [markdown]
# ## 7. Flow and Grids
#
# A {{< glossary FlowMap >}} can unfold a printed passage that is played more
# than once. A beat grid then answers metrical questions with exact fractions.

# %%
section = PlaythroughSection(1, 2, ("A",))
repeat_flow = Flow.from_sections([section, section], mode=FlowMode.default)
quarter_span = (Fraction(0), Fraction(4))
repeat_map = FlowMap.from_qb_sections(repeat_flow, [quarter_span] * 2)
unfolded_positions = repeat_map.unfold_coordinate(Fraction(2))
unfolded_coordinates = [score.make_coordinate(value) for value in unfolded_positions]
beat_grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=30)
beat_position = beat_grid.beat_at(Fraction(17, 4))
flow_preview = {"unfolded": unfolded_coordinates, "beat": beat_position}
flow_preview

# %% [markdown]
# The printed position at two quarters appears twice after unfolding, while the
# grid reports beat 5/4 for quarter 17/4. Open
# [Flow and Grids](tut07_flow_and_grids.ipynb) to model complete playthroughs
# and metrical queries.

# %% [markdown]
# ## 8. The Data Model
#
# Timeline events are stored in typed columns. Asking for the `start` field
# reconstructs the library object represented by the Arrow data.

# %%
first_start = audio_events.get_field("start")[0]
first_start

# %% [markdown]
# The first value is a `Coordinate` in seconds, not a bare floating-point
# number. Open [The Data Model](tut08_data_model.ipynb) to understand fields,
# scalars, and their tabular representation.

# %% [markdown]
# ## 9. Pitch and Harmony
#
# MIDI pitch can leave a black key's spelling open, while notation can preserve
# the written accidental. TimeToAlign! keeps those meanings distinct.

# %%
enharmonic_pitch = EnharmonicPitch(61)
spelled_pitch = SpecificPitch.from_string("C♯4")
pitch_pair = {"enharmonic": enharmonic_pitch, "spelled": spelled_pitch}
pitch_pair

# %% [markdown]
# The first pitch allows C♯ or D♭; the second records C♯ specifically. Open
# [Pitch and Harmony](tut09_pitch_and_harmony.ipynb) to work with pitch
# representations, spelling, and harmonic labels.

# %% [markdown]
# ## Series map
#
# | Tutorial | Promise |
# |---|---|
# | 1. Timelines and Coordinates | Build a measured axis and place a coordinate on it. |
# | 2. Nesting and Timestamps | Read one position across nested timelines. |
# | 3. Events on a Timeline | Store and retrieve musical observations. |
# | 4. Loading Real Data | Turn a research file into timelines and events. |
# | 5. Timeline Groups | Transfer positions between commensurable timelines. |
# | 6. Alignment Bundles | Collect claims and query cross-timeline matches. |
# | 7. Flow and Grids | Unfold score order and ask metrical questions. |
# | 8. The Data Model | Recover typed library objects from columns. |
# | 9. Pitch and Harmony | Preserve pitch meaning and written spelling. |

# %% [markdown]
# ## What you learned
#
# - You can build a timeline and make a unit-bearing coordinate.
# - You can nest child timelines and read across them with a timestamp.
# - You can add events to a timeline and retrieve a non-empty selection.
# - You can load a score file into the same timeline model.
# - You can group timelines and transfer a coordinate between them.
# - You can express one match claim and inspect its matchstamp.
# - You can unfold a repeated position and query a beat grid exactly.
# - You can retrieve a typed coordinate from an event-data field.
# - You can distinguish an enharmonic pitch from a specifically spelled pitch.
#
# ## Next
#
# Continue with [Timelines and Coordinates](tut01_timelines_and_coordinates.ipynb).
#
# ## Go deeper
#
# - [Coordinate arithmetic](../howto/how01_coordinate_math.ipynb)
# - [Advanced timestamps](../howto/how01_advanced_timestamps.ipynb)
# - [Loading data](../howto/how01_loading_data.ipynb)
# - [Flow control](../howto/how01_flow_control.ipynb)
# - [Creating a note alignment](../howto/how03_create_note_alignment.ipynb)
