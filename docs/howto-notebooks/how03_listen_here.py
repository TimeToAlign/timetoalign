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
# # How to Load an Audio-to-Audio Alignment (Listen Here!)
#
# *Listen Here!* aligns **several recordings of one work** to each other and
# exports the result as a single JSON file. Each recording is warped onto a
# shared, equidistant **reference grid**: per recording, the file stores a
# `times` array whose `i`-th entry is that recording's clock-time (in seconds)
# at reference-grid column `i`. Because every recording is sampled against the
# *same* grid, the arrays are parallel and equal length — together they form a
# dense alignment matrix of shape `(recordings × grid columns)`. This guide
# loads such an export into a single audio-to-audio
# {{< glossary AlignmentBundle >}} with `ListenHereLoader`.
#
# This is a different shape of data from the score↔performance loaders. There,
# each file relates **one** score to **one** performance, and a
# {{< glossary MatchGraph >}} only emerges once several such bundles are
# combined. A Listen Here! file instead encodes the alignment of *all*
# recordings against one another **directly** — one file already carries the
# whole graph. The natural reading is a **complete pairwise topology**: at every
# grid column, every unordered pair of recordings is related by a synchronous
# instant {{< glossary MatchClaim >}}.
#
# We **load an existing alignment**; nothing here runs an aligner. The warp was
# computed once, offline, and written to disk; the loader reads it faithfully.
#
# The arc:
#
# 1. Build a small self-contained Listen Here! export and load it in one call.
# 2. Inspect the columnar {{< glossary MatchClaimField >}} that holds the whole
#    pairwise claim set.
# 3. The headline: place a point on one recording and read it on all the others.
# 4. A note on scale — why the claims live in a column, not a million objects.
# 5. What a real export carries beyond what this loader yet reads.

# %% [markdown]
# ## Setup
#
# The published Listen Here! corpus is not yet bundled with the project, so this
# guide is **self-contained**: we synthesise a small but plausible export in a
# temporary file and load that. It stands in for the real thing — four
# recordings of one work, warped onto a reference grid at 0.02 s (50 Hz)
# spacing.

# %%
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from timetoalign.loader.alignment import ListenHereLoader

# The reference recording fixes the grid origin; the other three are warped
# onto it. Each per-recording warp is a scale (a steadier or quicker reading of
# the same music) plus a small onset offset. One recording (PARK) begins after
# the reference's grid origin, so its early columns carry small *negative*
# seconds — a pre-onset extrapolation the loader keeps faithfully.
_REFERENCE = "mdw-Wataru-MASHIMO.mp3"
_N_COLUMNS = 24
_GRID = [round(i * 0.02, 5) for i in range(_N_COLUMNS)]


def _warp(scale: float, offset: float) -> list[float]:
    return [round(scale * g + offset, 5) for g in _GRID]


_TIMES = {
    "mdw-Wataru-MASHIMO.mp3": _GRID,  # the reference itself
    "mdw-Seika-ISHIDA.mp3": _warp(0.94, 0.030),
    "mdw-Martin-NOEBAUER.mp3": _warp(1.08, 0.015),
    "mdw-Hyo-Eun-PARK.mp3": _warp(1.15, -0.025),  # negative pre-onset
}

_EXPORT = {
    "header": {"ref": _REFERENCE, "createdBy": "Listen Here! v0.20.0"},
    "body": {
        "audio": {
            key: {
                "times": times,
                "peaks": [0.1, 0.2],
                "duration": round(max(times) + 0.5, 3),
            }
            for key, times in _TIMES.items()
        }
    },
}

alignment_json = Path(tempfile.mkdtemp()) / "alignment.json"
alignment_json.write_text(json.dumps(_EXPORT), encoding="utf-8")

# %% [markdown]
# ## 1. Load the export in one call
#
# `ListenHereLoader` parses the single alignment JSON file: it reads each
# recording's `times` array, checks that they all index the same reference grid
# (equal length), and assembles the complete pairwise claim set. `from_file()`
# is the one-line form of the standard two-phase loader pattern.

# %%
loader = ListenHereLoader.from_file(alignment_json)
loader

# %% [markdown]
# Four recordings, and the loader reports its recording stems in sorted order.
# The recording named by `header.ref` is just another recording here — it fixes
# the grid origin but is **not** a privileged hub.

# %%
loader.recording_keys

# %% [markdown]
# ---
#
# ## 2. The whole pairwise claim set, in a column
#
# The loader's `claim_field` is a {{< glossary MatchClaimField >}}: a columnar,
# PyArrow-backed store that holds the entire set of pairwise
# {{< glossary MatchClaim >}}s as Arrow columns and materialises individual
# `MatchClaim` objects only on demand. Its length is the **complete topology**:
# for `R` recordings and `N` grid columns, every unordered pair at every column,
# i.e. `C(R, 2) × N` claims. Here `C(4, 2) × 24 = 6 × 24 = 144`:

# %%
claims = loader.claim_field
claims

# %%
{
    "claims": len(claims),
    "recordings": len(loader.recording_keys),
    "grid columns": _N_COLUMNS,
    "C(4,2) x 24": 6 * _N_COLUMNS,
}

# %% [markdown]
# Indexing the field materialises one {{< glossary MatchClaim >}} on demand. It
# is an ordinary pairwise claim — two timelines, a synchronous instant anchor,
# and the shared provenance the export recorded (Listen Here!'s chroma-feature
# DTW). The first claim relates the reference to the first warped recording at
# grid column 0:

# %%
claims[0]

# %% [markdown]
# Because the field is columnar, narrowing it is a vectorised Arrow filter, not
# a Python loop over a million objects. `connecting(...)` returns a **new**
# `MatchClaimField` holding only the claims that touch a given timeline — here,
# every claim involving the PARK recording. With four recordings each is paired
# with the other three, so PARK appears in `3 × 24 = 72` of the 144 claims:

# %%
park_claims = claims.connecting("mdw-Hyo-Eun-PARK:cpt1")

{
    "claims touching PARK": len(park_claims),
    "3 pairs x 24 columns": 3 * _N_COLUMNS,
    "timelines in the view": sorted(park_claims.timeline_ids),
}

# %% [markdown]
# One of PARK's claims at the very first grid column carries the **negative**
# pre-onset coordinate — the recording's clock has not yet reached its first
# onset at the reference origin. The loader stores it as written, neither
# clamped nor dropped:

# %%
park_claims[0]

# %% [markdown]
# ---
#
# ## 3. Place a point on one recording, read it on all the others
#
# `create_bundle()` assembles the {{< glossary AlignmentBundle >}}: one seconds
# {{< glossary Timeline >}} per recording, each in its own group, and the
# complete pairwise claim set tying every recording to every other. The
# recordings carry **no symbolic events** — the timelines hold only a length (the
# recording's stored duration) and a unit; all the alignment lives in the
# cross-group claims.

# %%
bundle = loader.create_bundle()
bundle

# %%
{
    "timelines": bundle.n_timelines,
    "groups": bundle.n_groups,
    "groups_listed": bundle.group_ids,
}

# %% [markdown]
# Here is the promise that makes audio-to-audio alignment compelling: **place a
# point on one recording, and it is instantly placed on all the others.**
# `get_matchstamp_at` takes a coordinate on any one recording's timeline and
# returns the corresponding coordinate on *every* recording connected to it.
# Read 0.24 seconds into the reference recording across the whole bundle:

# %%
stamp = bundle.get_matchstamp_at(0.24, "mdw-Wataru-MASHIMO:cpt1")
stamp

# %% [markdown]
# Read across that {{< glossary MatchStamp >}}: the same musical instant the
# reference reaches at 0.24 s falls at a slightly different second in each of the
# other three recordings — the steadier reading reaches it a touch earlier, the
# quicker one a touch later. Because the topology is complete, the same query
# works from *any* recording as the anchor, not only the reference. The same
# grid column read from NOEBAUER's clock (0.2742 s) returns the very same set of
# positions:

# %%
bundle.get_matchstamp_at(0.2742, "mdw-Martin-NOEBAUER:cpt1")

# %% [markdown]
# ---
#
# ## 4. A note on scale
#
# The synthetic export above has four recordings and 24 grid columns. A real
# whole-work export is far larger. Six recordings give `C(6, 2) = 15` pairs, and
# a 25-minute work sampled at 50 Hz is on the order of tens of thousands of grid
# columns — so the complete topology runs to **roughly a million pairwise
# claims** for one work.
#
# This is exactly why the claims live in a {{< glossary MatchClaimField >}}
# rather than as a million individual `MatchClaim` objects. The field stores the
# whole set as four Arrow columns (the two timeline ids dictionary-encoded, the
# two coordinates as `float64`) and the loader builds it **vectorised** — never
# constructing a Python claim per row. A `MatchClaim` is materialised only when a
# single row is indexed or iterated. The columnar store is what lets one
# `AlignmentBundle` hold a whole-work, every-pair audio-to-audio graph without
# strain.

# %% [markdown]
# ---
#
# ## 5. What a real export carries beyond this
#
# This loader reads the part of a Listen Here! export that makes the
# audio-to-audio graph: the per-recording warp arrays over the reference grid. A
# real export additionally carries a couple of things this loader does **not yet
# read**:
#
# - an in-file **score↔reference bridge** (the export can also align a symbolic
#   score to the reference grid, which would add a logical score group tied to
#   the recordings); and
# - **per-recording sample grids** (a samples timeline alongside each seconds
#   timeline, once a sample rate is resolved from the audio).
#
# Neither is loaded here. What this guide does build is the core of the model:
# many recordings of one work, every pair directly related, in one bundle.

# %% [markdown]
# ## Recap
#
# | What the bundle expresses | How |
# |---|---|
# | One recording per group | `<stem>:cpt1` seconds timeline, no events, length = the recording's duration |
# | The whole pairwise alignment | a columnar {{< glossary MatchClaimField >}} (`loader.claim_field`), `C(R,2) × N` |
# | One claim, materialised | `claim_field[i]` → a synchronous instant {{< glossary MatchClaim >}} |
# | Claims touching one recording | `claim_field.connecting(timeline_id)` → a new (vectorised) `MatchClaimField` |
# | A point placed everywhere | `bundle.get_matchstamp_at(coord, "<stem>:cpt1")` → every recording at once |
#
# A single file encodes an entire audio-to-audio {{< glossary MatchGraph >}} —
# every recording of one work warped onto a shared reference grid, every pair
# directly related. `ListenHereLoader` reads it into one
# {{< glossary AlignmentBundle >}} in which a coordinate placed on any one
# recording resolves, in a single query, across all the others; and the dense
# claim set that makes that possible is held in a column, not a million objects.
