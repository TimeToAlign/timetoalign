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
# # Flow Control and Grids

# %% [markdown]
# ## What you will build
#
# You will build a folded {{< glossary Timeline >}}, describe its played order,
# and obtain an unfolded timeline that preserves the route back to the page.
# You will also build a metrical grid whose measures and beats can be queried in
# either direction and exported for annotation software.

# %% [markdown]
# ## Before you start
#
# This notebook continues from [Alignment Bundles](tut06_alignment_bundles.ipynb).

# %%
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from timetoalign import (
    BeatGrid,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    Ms3Loader,
)
from timetoalign.testdata import ensure_data
from timetoalign.timelines import Flow, FlowMap, ScoreFlowController

score_data = ensure_data("score")

# %% [markdown]
# ## 1. A page is not a performance
#
# A repeat sign or *Da Capo* changes traversal order without changing the page.
# The written timeline is **folded**; the route actually played is **unfolded**.

# %%
written_score = ContinuousLogicalTimeline.from_events(
    [
        {
            "id": "written_end",
            "temporal_type": "instant",
            "event_type": "Boundary",
            "instant": Fraction(12),
        }
    ],
    uid="written_score",
    name="Three written spans",
)
span_bounds = {
    "A": (Fraction(0), Fraction(4)),
    "B": (Fraction(4), Fraction(8)),
    "C": (Fraction(8), Fraction(12)),
}
written_order = list(span_bounds)
played_order = ["A", "A", "C"]
page_and_performance = {
    "written length": written_score.length,
    "written order": written_order,
    "played order": played_order,
}
page_and_performance

# %% [markdown]
# The length is a {{< glossary Coordinate >}} measured in quarters. The page
# contains A, B, and C once each, but the performance repeats A and skips B.

# %% [markdown]
# ## 2. Naming the played spans
#
# A {{< glossary Region >}} gives a stable name to a span of the written score.
# We reuse `create_region` from the nesting tutorial.

# %%
created_regions = [
    written_score.create_region(name, start, end)
    for name, (start, end) in span_bounds.items()
]
opening_region = created_regions[0]
closing_region = created_regions[2]
named_spans = written_score.list_regions()
region_overview = {
    "opening span": opening_region,
    "region names": named_spans,
}
region_overview

# %% [markdown]
# Each region keeps its quarter-valued start and end. These names now let the
# played route refer to legible musical spans rather than unexplained numbers.

# %% [markdown]
# ## 3. Building the map
#
# A {{< glossary FlowMap >}} records how folded spans are placed in played
# order. `create_flow_map(intervals)` accepts a name, a Region, a `(start, end)`
# pair, a Timeline, or an iterable mixing any of those shapes.

# %%
flow_intervals = [played_order[0], opening_region, closing_region]
performance_map = written_score.create_flow_map(
    flow_intervals,
    id="performance",
)
written_score.add_flow_map(performance_map, id="played")
retrieved_map = written_score.get_flow_map("played")
available_maps = written_score.list_flow_maps()
map_overview = {
    "is a FlowMap": isinstance(retrieved_map, FlowMap),
    "attached ids": available_maps,
    "selected map": retrieved_map,
}
map_overview

# %% [markdown]
# The single `flow_intervals` argument mixes a region name with Region objects.
# `add_flow_map` attaches an existing map under another id; `get_flow_map` and
# `list_flow_maps` retrieve and enumerate the attached maps.

# %% [markdown]
# ## 4. Unfolding one position
#
# `unfold_coordinate(coord)` takes one folded position and returns a list,
# because repeated material can occur at several positions in performance.

# %%
repeated_folded = written_score.get_coordinate(Fraction(1))
skipped_folded = written_score.get_coordinate(Fraction(5))
repeated_values = written_score.unfold_coordinate(repeated_folded, "played")
skipped_values = written_score.unfold_coordinate(skipped_folded, "played")
repeated_unfolded = [
    written_score.make_coordinate(Fraction(value)) for value in repeated_values
]
skipped_unfolded = [
    written_score.make_coordinate(Fraction(value)) for value in skipped_values
]
unfold_report = {
    "folded position in A": repeated_folded,
    "played positions": repeated_unfolded,
    "folded position in B": skipped_folded,
    "played positions for skipped B": skipped_unfolded,
}
unfold_report

# %% [markdown]
# The position in A appears once in each rendition. The empty list for B is the
# correct answer, not a failure: that written span is absent from this route.

# %% [markdown]
# ## 5. Folding back
#
# `fold(coord)` goes in the other direction: many possible performance
# positions collapse to one position on the written page.

# %%
later_unfolded = repeated_unfolded[1]
folded_value = written_score.fold(later_unfolded, "played")
folded_coordinate = written_score.make_coordinate(Fraction(folded_value))
fold_report = {
    "later performance position": later_unfolded,
    "position on the page": folded_coordinate,
    "matches the original": folded_coordinate == repeated_folded,
}
fold_report

# %% [markdown]
# The second rendition folds back to the same written position as the first.
# Keep the directions distinct: unfolding is one-to-many; folding is many-to-one.

# %% [markdown]
# ## 6. Assembling the whole unfolded timeline
#
# `apply_flow(id)` constructs the complete played timeline. It preserves the
# source's concrete type and makes one {{< glossary Child >}} timeline for every
# played span.

# %%
unfolded_score = written_score.apply_flow("played")
unfolded_children = unfolded_score.list_children()
unfolded_regions = unfolded_score.list_regions()
reverse_map = unfolded_score.get_flow_map("source")
unfolded_overview = {
    "same concrete type": type(unfolded_score) is type(written_score),
    "children": unfolded_children,
    "regions": unfolded_regions,
    "reverse map": reverse_map,
    "earlier round trip": folded_coordinate,
}
unfolded_overview

# %% [markdown]
# The second visit to A is named `A-rend2`; further visits would use `-rend3`
# and so on. Matching regions cover the spans in unfolded coordinates; those
# named intervals are what make the route invertible through the `source` map.

# %% [markdown]
# ## 7. Flow from a real score
#
# Score loaders retain repeat signs as flow-control {{< glossary Event >}}s.
# A `ScoreFlowController` turns those records into a {{< glossary Flow >}} and
# reports traversal problems without interrupting the notebook.

# %%
score_dir = score_data / "beethoven_woo71"
score_loader = Ms3Loader.from_file(
    score_dir / "WoO71.notes.tsv",
    score_dir / "WoO71.measures.tsv",
)
measure_data = score_loader.store.measures
measure_table = measure_data.to_dataframe()
repeat_mask = measure_table["start_repeat"] | measure_table["end_repeat"]
repeat_rows = measure_table.loc[
    repeat_mask,
    ["mc", "mn", "start_repeat", "end_repeat", "next"],
]
repeat_events = repeat_rows.head(6)
controller = score_loader.create_flow_controller()
real_flow_map = controller.create_flow_map()
real_flow = real_flow_map.flow
diagnostics = controller.flow_diagnostics(real_flow.mode)
score_timeline = score_loader.create_timeline(uid="woo71_folded")
section_boundaries = controller.get_section_boundary_coordinates()
score_segments = score_timeline.create_segment_line(
    [score_timeline.origin, *section_boundaries, score_timeline.length]
)
flow_report = {
    "controller type": isinstance(controller, ScoreFlowController),
    "flow type": isinstance(real_flow, Flow),
    "flow-map type": isinstance(real_flow_map, FlowMap),
    "folded measures": real_flow.folded_length,
    "played measures": real_flow.unfolded_length,
    "parsed repeat events": repeat_events.to_dict(orient="records"),
    "diagnostics": [item.kind for item in diagnostics] or "none",
    "segments from flow boundaries": score_segments.n_children,
}
flow_report

# %% [markdown]
# The folded MS3 export contains explicit repeat starts, repeat ends, and
# non-sequential `next` destinations. `create_segment_line` is the natural way
# to turn controller boundaries into a {{< glossary SegmentLine >}} for
# inspection. `flow_diagnostics(mode)` detects and reports issues such as
# `flow_cycle`, `flow_nonconvergence`, `ambiguous_repeat_end`, and
# `dangling_repeat_end`; this score reports none, and the method never raises
# merely because it found a diagnostic.

# %% [markdown]
# ## 8. Metre as a queryable grid
#
# A `BeatGrid` represents metre on an exact quarter-note axis. `from_tempo`
# supplies a uniform tempo, meter, and duration, after which positions can be
# queried in either direction.

# %%
grid = BeatGrid.from_tempo(
    tempo_bpm=120,
    beats_per_measure=3,
    length_seconds=12.0,
    uid="three_four_grid",
)
quarter_position = grid.make_coordinate(Fraction(6))
measure_number = grid.measure_at(quarter_position)
beat_number = grid.beat_at(quarter_position)
inverse_quarter_value = grid.quarter_at(
    measure=2,
    beat=Fraction(3, 2),
)
inverse_quarter = grid.make_coordinate(inverse_quarter_value)
grid_query = {
    "quarter position": quarter_position,
    "measure": measure_number,
    "beat": beat_number,
    "measure 2, beat 3/2": inverse_quarter,
}
grid_query

# %% [markdown]
# Six quarters is the start of measure 3 in this 3/4 grid. The inverse query
# returns an exact rational coordinate: quarter positions and beat positions
# remain `Fraction` values rather than drifting into floats.

# %% [markdown]
# ## 9. Vectorised accessors
#
# `beat_seconds()` and `measure_seconds()` provide NumPy arrays for bulk work.
# The same grid can write label tracks for Sonic Visualiser or Audacity.

# %%
beat_times = grid.beat_seconds()
measure_times = grid.measure_seconds()
with TemporaryDirectory() as temporary_dir:
    export_path = Path(temporary_dir) / "beats.csv"
    exported_rows = grid.export_to_csv(
        str(export_path),
        format="sonic_visualiser",
    )
    exported_text = export_path.read_text(encoding="utf-8")
    first_export_lines = exported_text.splitlines()[:4]
vector_report = {
    "first beat times": beat_times[:6],
    "first measure times": measure_times[:4],
    "rows written": exported_rows,
    "first CSV lines": first_export_lines,
}
vector_report

# %% [markdown]
# The arrays are measured in seconds, matching the annotation file's first
# column. The temporary export is genuinely written and read back; it leaves no
# tutorial artefact behind.

# %% [markdown]
# ## 10. Grids on a timeline
#
# A physical timeline can create a metrical grid for its full extent or for one
# named region. Each result links seconds and quarters in a
# {{< glossary TimelineGroup >}}.

# %%
audio_timeline = ContinuousPhysicalTimeline.from_events(
    [
        {
            "id": "audio_end",
            "temporal_type": "instant",
            "event_type": "Boundary",
            "instant": 12.0,
        }
    ],
    uid="audio_excerpt",
)
audio_region = audio_timeline.create_region("analysis_window", 2.0, 8.0)
whole_metre = audio_timeline.create_metrical_grid(
    first_beat_at=0.0,
    tempo_bpm=120,
    beats_per_measure=4,
)
region_metre = audio_timeline.create_metrical_region(
    "analysis_window",
    tempo_bpm=120,
    beats_per_measure=4,
)
whole_grid = whole_metre.grid
region_grid = region_metre.grid
metrical_overview = {
    "source region": audio_region,
    "whole-grid length": whole_grid.length,
    "region-grid length": region_grid.length,
}
metrical_overview

# %% [markdown]
# `create_metrical_grid` covers all twelve seconds, whereas
# `create_metrical_region` limits the grid to the six-second analysis window.
# Their logical lengths are shown as quarter-valued coordinates.

# %% [markdown]
# ## What you learned
#
# - You can distinguish a folded page from its unfolded performance order.
# - You can name written spans with regions.
# - You can build, attach, retrieve, and list polymorphic flow maps.
# - You can unfold one written position to zero, one, or several played positions.
# - You can fold a played position back to one place on the page.
# - You can assemble and inspect a complete unfolded timeline.
# - You can inspect parsed score repeats and obtain non-raising flow diagnostics.
# - You can query measure and beat positions while preserving rational quarters.
# - You can access grid positions as arrays and export a real annotation CSV.
# - You can create metrical grids for a complete timeline or one named region.

# %% [markdown]
# ## Next
#
# Continue with [The Data Model](tut08_data_model.ipynb).
#
# ## Go deeper
#
# - [Flow control](../howto/how01_flow_control.ipynb)
# - [Flow maps from regions](../howto/how01_flowmap_from_regions.ipynb)
# - [Beat grids](../howto/how01_beat_grids.ipynb)
