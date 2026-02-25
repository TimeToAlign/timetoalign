# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Loading a Specimen from the 4x22 Vienna Corpus
#
# This guide demonstrates how to load score-to-performance alignment data
# from the **Vienna 4x22 Corpus** using the `MatchfileLoader`.
#
# ## About the Dataset
#
# The full **4x22 Vienna Corpus** (Grachten & Widmer, 2012) contains four
# classical piano pieces, each performed by 22 pianists, yielding 88
# score-to-performance alignments in the `.match` file format. Each `.match`
# file encodes three things simultaneously:
#
# - A **score representation** (note identities, pitch, metrical position,
#   duration in quarter beats).
# - A **performance representation** (MIDI pitch, onset/offset in ticks,
#   velocity).
# - An **alignment** linking each score note to its performed counterpart
#   (or marking it as a deletion when the pianist omitted it).
#
# **What we demonstrate here is a 1x22 sample** — one piece (Chopin Etude
# Op. 10 No. 3 in E major) performed by all 22 pianists. This is one quarter
# of the full dataset, and it is the specimen shipped with the TimeToAlign!
# test suite. The workflow generalises straightforwardly to the remaining
# three pieces.
#
# **What you will learn:**
#
# 1. Load all 22 `.match` files through a single `MatchfileLoader` instance
# 2. Create an `AlignmentBundle` containing the shared score and 22
#    performance timelines
# 3. Inspect the bundle contents — timelines, groups, and match claims
# 4. Access individual timelines and their conversion maps

# %% [markdown]
# ## Setup

# %%
from pathlib import Path

from timetoalign import MatchfileLoader

_notebook_dir = Path(".").resolve()
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data" / "vienna_1x22"
assert DATA_DIR.is_dir(), f"Data directory not found: {DATA_DIR}"

match_files = sorted(DATA_DIR.glob("*.match"))
len(match_files)

# %% [markdown]
# We have 22 `.match` files — one per pianist — all sharing the same score
# (Chopin Op. 10 No. 3).

# %% [markdown]
# ## Step 1: Load All Match Files
#
# The `MatchfileLoader` is designed to process **all** `.match` files for a
# given piece through a single instance. It builds a shared score timeline
# from the first file and verifies each subsequent file against it. If a
# file contains contradictory score data it is rejected with a warning;
# compatible files add their performance timeline and match claims.

# %%
loader = MatchfileLoader()
loader.load(*match_files)
loader

# %% [markdown]
# The loader has ingested all 22 files successfully. The `repr` shows the
# number of performance timelines, total match claims across all files, and
# any rejected files (zero in this case — all 22 are compatible).

# %% [markdown]
# ## Step 2: Create the AlignmentBundle
#
# The second phase of the loader pattern: `create_alignment_bundle()`
# assembles an `AlignmentBundle` from the data already parsed by `load()`.
# The score goes into its own group; each performance is a standalone
# timeline; all match claims connect them.

# %%
bundle = loader.create_alignment_bundle()
bundle

# %% [markdown]
# The bundle contains 23 timelines (1 score + 22 performances), 1 group
# (the score group), and cross-group match claims connecting every
# performance to the shared score.

# %% [markdown]
# ## Step 3: Inspect the Bundle
#
# The bundle diagram gives an overview of all timelines and groups:

# %%
bundle.diagram()

# %% [markdown]
# For a structured summary with exact counts:

# %%
bundle.summary()

# %% [markdown]
# ## Step 4: Access Individual Timelines
#
# The loader provides two methods for accessing timelines directly:
#
# - `create_timeline(id)` — retrieve a single timeline by role or uid
# - `create_timelines()` — retrieve all timelines as a list (score first)
#
# Role shorthands for the score:

# %%
score = loader.create_timeline("score")
score

# %% [markdown]
# The score is a `ContinuousLogicalTimeline` in quarter-beat coordinates.
# It carries conversion maps for unit transforms (e.g. quarters to MIDI
# divisions) and a `ShiftMap` for anacrusis normalisation.

# %% [markdown]
# For performances, use the `"perf:N"` shorthand (1-indexed) or the
# `"perf:pNN"` pattern:

# %%
perf_01 = loader.create_timeline("perf:1")
perf_01

# %% [markdown]
# Each performance is a `DiscreteLogicalTimeline` in MIDI tick coordinates,
# with a `ticks_to_seconds` conversion map attached.

# %% [markdown]
# ## Step 5: Coordinate Transfer Across Timelines
#
# The bundle enables coordinate transfer between any pair of connected
# timelines. For example, transferring a score coordinate to a performance:

# %%
bundle.transfer(10.0, "score", perf_01.id)

# %% [markdown]
# This returns the MIDI tick coordinate on performance p01 that corresponds
# to quarter-beat 10.0 in the score, computed via the match claims and the
# internal WarpMap.

# %% [markdown]
# ## Summary
#
# The complete workflow for loading a specimen from the Vienna corpus:
#
# ```python
# from timetoalign import MatchfileLoader
#
# loader = MatchfileLoader()
# loader.load(*sorted(data_dir.glob("*.match")))
# bundle = loader.create_alignment_bundle()
# ```
#
# Three lines. The `AlignmentBundle` then supports coordinate transfer,
# timestamp queries, and further analysis across all 22 performances.
