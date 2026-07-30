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
# # How to Build a FlowMap from Regions
#
# A printed score is **folded**: every coordinate on it is written once, even
# where the music is played several times or skipped entirely. A performance is
# **unfolded**: it plays a particular *path* through the page, in which some
# spans are repeated, some are omitted, and the rest follow in a single stream.
#
# A {{< glossary FlowMap >}} is the bidirectional map between those two views. It
# is an ordered sequence of {{< glossary TimeInterval >}}s cut from the folded
# timeline; concatenating them in order gives the performance (unfolded) order.
#
# This guide builds a FlowMap **from named spans you define yourself** rather
# than from parsed {{< glossary Break >}}/{{< glossary Jump >}} events. That is
# the right tool when the path is a performing decision — a cut, an omitted
# repeat, a bespoke concert ending — rather than something notated in the score.
#
# The worked example is a **cut**: a performance that plays measures 1–41,
# **skips measures 42 and 43**, then continues from measure 44 to the end.
#
# **Learning objectives:**
#
# 1. Mark the played spans as {{< glossary Region >}}s on the folded timeline
# 2. Build and attach a FlowMap in one call with `Timeline.create_flow_map()`
# 3. Map a folded coordinate to its performance position with
#    `unfold_coordinate()` — and see a skipped coordinate return `[]`
# 4. `fold()` a performance coordinate back onto the score
# 5. Assemble the whole unfolded timeline with `apply_flow()` — a timeline of the
#    source's own type whose played spans are appended as named children, each
#    also recorded as a {{< glossary Region >}}
# 6. Recognise that FlowMap construction takes **one** argument in many shapes:
#    region names, `Region` objects, coordinate pairs, a `Timeline`, or a
#    collection of any of these
#
# **Prerequisites:** `how01_manual_timeline_construction`, `how01_coordinate_math`

# %% [markdown]
# ## Setup
#
# We work in quarterbeats (QB). The example score is 50 measures of 3/4, so each
# measure is 3 QB long and the whole score is 150 QB. `build_score()` returns a
# folded {{< glossary Timeline >}} with one downbeat marker per measure;
# `probe()` unfolds a handful of coordinates through a map so we can compare
# construction shapes side by side.

# %%
from timetoalign.timelines import ContinuousLogicalTimeline, FlowMap

QB_PER_MEASURE = 3
N_MEASURES = 50


def build_score(
    n_measures: int = N_MEASURES, qb_per_measure: int = QB_PER_MEASURE
) -> ContinuousLogicalTimeline:
    """Return a folded score timeline with one downbeat marker per measure."""
    length = n_measures * qb_per_measure
    score = ContinuousLogicalTimeline(length=length, uid="score")
    score.add_events(
        [
            {
                "id": f"m{m}",
                "temporal_type": "instant",
                "event_type": "Downbeat",
                "instant": (m - 1) * qb_per_measure,
            }
            for m in range(1, n_measures + 1)
        ]
    )
    return score


def downbeat(measure: int, qb_per_measure: int = QB_PER_MEASURE) -> float:
    """Folded QB coordinate of a measure's downbeat."""
    return float((measure - 1) * qb_per_measure)


def probe(flow_map: FlowMap, coords: list[float]) -> dict[float, list[float]]:
    """Unfold each probe coordinate; a skipped coordinate yields ``[]``."""
    return {c: [float(t) for t in flow_map.unfold_coordinate(c)] for c in coords}


# %%
score = build_score()
{
    "id": score.id,
    "unit": str(score.unit),
    "length_qb": float(score.length),
    "n_measures": score.n_events,
}

# %% [markdown]
# ## The played spans
#
# The performance omits measures 42 and 43. In QB space those two measures
# occupy `[123, 129)` — the downbeat of measure 42 is at QB 123 and the downbeat
# of measure 44 is at QB 129. Everything before and after is played, so the path
# is exactly two spans:
#
# - measures 1–41 → `[0, 123)`
# - measures 44–50 → `[129, 150)`
#
# We record each span as a named {{< glossary Region >}} on the folded timeline.

# %%
CUT = (42, 43)
before_end = downbeat(CUT[0])  # 123.0 — start of measure 42
after_start = downbeat(CUT[1] + 1)  # 129.0 — start of measure 44

score.create_region("before_cut", start=0, end=before_end)
score.create_region("after_cut", start=after_start, end=score.length)

score.list_regions()

# %% [markdown]
# ## Build and attach the FlowMap
#
# `Timeline.create_flow_map()` takes the played spans as a single argument,
# resolves each region name against the timeline's own {{< glossary Region >}}s,
# builds the {{< glossary FlowMap >}}, attaches it under the given id, and
# returns it. The spans concatenate in the order given, so the unfolded timeline
# runs measures 1–41 straight into measures 44–50 with no gap.

# %%
cut_map = score.create_flow_map(["before_cut", "after_cut"], id="cut")
cut_map

# %% [markdown]
# ## Unfold a coordinate: folded → performance
#
# `unfold_coordinate()` reports where a folded coordinate lands in the
# performance. Because a folded coordinate could be played more than once (under
# a repeat), it always returns a **list** of positions. Here nothing repeats, so
# a played coordinate yields exactly one position.
#
# The first span is unshifted — measures 1–41 play at their score coordinates:

# %%
{
    "folded_qb": downbeat(11),
    "unfolded": [float(t) for t in cut_map.unfold_coordinate(downbeat(11))],
}

# %% [markdown]
# The second span slides earlier by the 6 QB of removed music (two 3-QB
# measures). Measure 46's downbeat sits at QB 135 on the page but arrives at
# QB 129 in performance:

# %%
{
    "folded_qb": downbeat(46),
    "unfolded": [float(t) for t in cut_map.unfold_coordinate(downbeat(46))],
}

# %% [markdown]
# ### A skipped coordinate returns `[]`
#
# The downbeats of the omitted measures 42 and 43 lie in neither span, so they
# are played **nowhere**. `unfold_coordinate()` returns an empty list — the
# coordinate has no performance position at all.

# %%
probe(cut_map, [downbeat(42), downbeat(43)])

# %% [markdown]
# ## Fold: performance → folded
#
# `fold()` is the inverse. The performance timeline has no repeated positions,
# so it always returns a single folded coordinate. Folding measure 46's arrival
# time (QB 129 in performance) recovers its score position (QB 135):

# %%
{"performance_qb": 129.0, "folded": float(cut_map.fold(129.0))}

# %% [markdown]
# The map is also attached to the timeline under its id, so
# `score.unfold_coordinate()` and `score.fold()` delegate to it without your
# having to hold the FlowMap object:

# %%
{
    "via_timeline_unfold": score.unfold_coordinate(downbeat(46), id="cut"),
    "via_timeline_fold": score.fold(129.0, id="cut"),
}

# %% [markdown]
# ## Unfold the whole timeline
#
# Everything above maps a *single* coordinate. To materialise the entire
# performance as its own timeline, call `apply_flow()` with the attached
# FlowMap's id. Where `unfold_coordinate()` answers "where does this one
# coordinate land?", `apply_flow(id)` assembles the whole performance: it returns
# a new timeline of the **source's own concrete type** — here a
# `ContinuousLogicalTimeline`, not some special container — and appends each played
# span as a **child**, named for the {{< glossary Region >}} it was cut from.
#
# Its length is the two spans summed (123 QB before the cut + 21 QB after =
# 144 QB), the 6 QB of the omitted measures removed from the folded 150.

# %%
unfolded = score.apply_flow("cut")
{
    "type": type(unfolded).__name__,
    "n_children": unfolded.n_children,
    "length_qb": float(unfolded.length.value),
}

# %% [markdown]
# Each played span is now a **child** whose id and name are the source Region's
# name, in the order they are played. `list_children()` names them and
# `get_child()` returns one:

# %%
{
    "children": unfolded.list_children(),
    "before_cut": unfolded.get_child("before_cut"),
}

# %% [markdown]
# `apply_flow()` also records each span as a {{< glossary Region >}} on the
# result — in **performance** (unfolded) coordinates, not the folded ones. These
# named Regions are what let the unfolding be inverted later: they carry the
# information needed to fold a performance coordinate back onto the score.

# %%
unfolded.list_regions()

# %% [markdown]
# The flattened event stream — every child's events in performance order —
# is available with `get_events(include_children=True)`:

# %%
unfolded.get_events(include_children=True).to_dataframe()

# %% [markdown]
# ## One argument, many shapes
#
# FlowMap construction is uniform: the same single argument accepts anything
# that describes an interval, on its own or as a collection. The region-name
# list above is one shape. `FlowMap(...)` builds the map directly (without
# attaching it to a timeline) from the others.
#
# **Coordinate pairs** — each `(start, end)` is a folded span:

# %%
cut_from_pairs = FlowMap([(0, before_end), (after_start, 150)], id="cut_pairs")
probe(cut_from_pairs, [downbeat(11), downbeat(42), downbeat(46)])

# %% [markdown]
# **`Region` objects** — reuse the regions already on the timeline:

# %%
cut_from_regions = FlowMap(
    [score.get_region("before_cut"), score.get_region("after_cut")],
    id="cut_regions",
)
probe(cut_from_regions, [downbeat(11), downbeat(42), downbeat(46)])

# %% [markdown]
# All three constructions describe the same path, so they unfold identically:

# %%
probes = [downbeat(11), downbeat(42), downbeat(46)]
{
    "from_region_names": probe(cut_map, probes),
    "from_pairs": probe(cut_from_pairs, probes),
    "from_regions": probe(cut_from_regions, probes),
}

# %% [markdown]
# A **single** interval-like value is equally valid and needs no wrapping list —
# `FlowMap((0, 123))` is a one-span map, and passing a whole
# {{< glossary Timeline >}} takes its full extent as one span. Whatever the
# shape, the result is one FlowMap with the same `unfold_coordinate()`/`fold()`
# behaviour.

# %%
one_span = FlowMap((0, before_end), id="opening_only")
probe(one_span, [downbeat(11), downbeat(46)])

# %% [markdown]
# ## Summary
#
# | Task | API |
# |------|-----|
# | Mark a played span | `timeline.create_region(name, start, end)` |
# | Build + attach a FlowMap from spans | `timeline.create_flow_map(intervals, id=...)` |
# | Build a FlowMap directly | `FlowMap(intervals, id=...)` |
# | Accepted `intervals` shapes | region name, `Region`, `(start, end)`, `Timeline`, or interval event |
# | Coordinate folded → performance (1→N) | `flow_map.unfold_coordinate(coord)` · `timeline.unfold_coordinate(coord)` |
# | A skipped coordinate | `unfold_coordinate()` returns `[]` |
# | Map a coordinate performance → folded (N → 1) | `flow_map.fold(coord)` · `timeline.fold(coord, id=...)` |
# | Assemble the whole unfolded timeline | `timeline.apply_flow(id)` → one child + Region per span |
# | Inspect / flatten the result | `.list_children()` · `.get_events(include_children=True)` |
#
# The same {{< glossary FlowMap >}} also unfolds *repeats* — a span listed twice
# plays twice, and `unfold_coordinate()` then returns two positions. In the
# assembled timeline that span appears as two children: the first occurrence
# bare (`before_cut`) and the second suffixed `before_cut-rend2`, following the
# Verovio rendering-order convention (`-rend3`, `-rend4`, … for any further
# repeats). Unnamed coordinate-pair spans fall back to `span_1`, `span_2`, … .
# For repeats read straight from a score's notated {{< glossary Break >}}s and
# {{< glossary Jump >}}s, see the multimodal alignment guide.
