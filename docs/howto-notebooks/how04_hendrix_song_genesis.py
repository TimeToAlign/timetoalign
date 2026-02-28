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
# # How to Encode Song Genesis Relationships (Hendrix)
#
# This notebook demonstrates how to encode **conceptual and temporal
# relationships** between multiple versions of a work using
# {{< glossary MatchClaim >}} objects, {{< glossary MatchGraph >}} structures,
# and the **NOMATCH** sentinel.
#
# The use case comes from a genesis study of Jimi Hendrix's
# *1983... (A Merman I Should Turn to Be)*, comparing three versions:
#
# - **Studio** -- the studio recording from *Electric Ladyland* (CPT1)
# - **Demo2** -- a band demo with Mitch Mitchell on drums (CPT2)
# - **Demo1** -- a solo demo (CPT3)
#
# Form analyses for each version are encoded as TiLiA hierarchy timelines.
# A CSV file records which sections correspond across versions, whether
# those correspondences are **synchronous** (temporal alignment possible)
# or merely **conceptual** (structural equivalence only), and where a
# section is explicitly absent from a version (**NOMATCH**).
#
# ## Key Concepts Demonstrated
#
# - Loading TiLiA JSON files via `TiliaJsonLoader`
# - Creating an {{< glossary AlignmentBundle >}} from independent timelines
# - Parsing a match table with **synchronous** and **NOMATCH** columns
# - Creating synchronous vs. conceptual {{< glossary MatchClaim >}} objects
# - Using `MatchClaim.nomatch()` for explicit structural absence
# - Querying events by name on hierarchy timelines

# %% [markdown]
# ## Setup

# %%
from pathlib import Path

import pandas as pd

from timetoalign import AlignmentBundle
from timetoalign.alignment.anchors import MatchClaim, MatchMetadata
from timetoalign.loader.alignment import TiliaJsonLoader

# Resolve data paths (works both as script and as notebook)
try:
    _notebook_dir = Path(__file__).parent.resolve()
except NameError:
    _notebook_dir = Path(".").resolve()

DATA_DIR = _notebook_dir.parent.parent / "tests" / "data" / "hendrix"

# %% [markdown]
# ## 1. Load the Three Versions
#
# Each version of the song has been annotated in TiLiA, producing a JSON
# file with hierarchy timelines encoding the form analysis.  We load each
# file and extract the first hierarchy timeline (`HIERARCHY_TIMELINE_0`),
# which contains the section-level annotations (Intro, Verse, Bridge, etc.).

# %%
names = ["Studio", "Demo2", "Demo1"]

timelines = {}
for name in names:
    loader = TiliaJsonLoader.from_file(DATA_DIR / f"Hendrix_Merman_{name}.json")
    tl = loader.create_timeline("HIERARCHY_TIMELINE_0")
    timelines[name] = tl

timelines

# %% [markdown]
# ## 2. Load the Match Data
#
# The file `match_data.csv` is a tab-separated table recording which
# sections correspond across the three versions.  Each row represents a
# {{< glossary MatchGraph >}} (M1--M15).
#
# - Cells contain the **event name** (section label) on the respective
#   timeline.
# - The value `NOMATCH` explicitly records that a section has no equivalent
#   in that version.
# - The `synchronous` column indicates whether the correspondence is
#   temporal (`TRUE`) or merely conceptual (`FALSE`).

# %%
df = pd.read_csv(DATA_DIR / "match_data.csv", sep="\t")
df

# %% [markdown]
# ## 3. Create the AlignmentBundle
#
# We add each hierarchy timeline to a single {{< glossary AlignmentBundle >}},
# assigning human-readable IDs that match the column names in `match_data.csv`.

# %%
bundle = AlignmentBundle(name="Hendrix Song Genesis")
for name, tl in timelines.items():
    bundle.add_timeline(tl, uid=name)

bundle

# %% [markdown]
# ## 4. Build MatchClaims from the Match Table
#
# For each row in the CSV we:
#
# 1. Look up the named event on each timeline.
# 2. Create **NOMATCH sentinels** where the CSV says `NOMATCH`.
# 3. For the remaining timelines with events present, create **pairwise
#    MatchClaims** -- synchronous or conceptual according to the
#    `synchronous` column.
#
# The pairwise strategy fans out from the first available timeline to
# each of the others (a "star" topology).

# %%
metadata = MatchMetadata(agent="user", decision_criteria="match_data.csv")
tl_columns = [c for c in df.columns if c not in ("match", "synchronous")]

sync_claims = []
conceptual_claims = []
nomatch_claims = []

for _, row in df.iterrows():
    match_id = row["match"]
    is_synchronous = str(row["synchronous"]).strip().upper() == "TRUE"

    # Collect events and detect NOMATCH sentinels
    present = []  # (timeline_name, event_dict)
    for tl_name in tl_columns:
        val = str(row[tl_name]).strip()

        if val.upper() == "NOMATCH":
            # Create a NOMATCH sentinel for every other timeline
            for other_name in tl_columns:
                if other_name == tl_name:
                    continue
                sentinel = MatchClaim.nomatch(
                    event={},
                    source_tl_id=tl_name,
                    target_tl_id=other_name,
                    metadata=metadata,
                )
                nomatch_claims.append(sentinel)
            continue

        # Look up the event by name
        tl = timelines[tl_name]
        evs = tl.get_events(name=val)
        if len(evs) != 1:
            continue
        event_id = str(evs.table[0][0])
        event = tl.get_event(event_id)
        present.append((tl_name, event))

    # Create pairwise claims from the first present timeline to the others
    if len(present) < 2:
        continue

    tl_a_name, ev_a = present[0]
    for tl_b_name, ev_b in present[1:]:
        if is_synchronous:
            claim = MatchClaim.from_events(
                event_a=ev_a,
                tl_a_id=tl_a_name,
                event_b=ev_b,
                tl_b_id=tl_b_name,
                end_coord_key="end",
                is_synchronous=True,
                metadata=metadata,
            )
            sync_claims.append(claim)
        else:
            claim = MatchClaim(
                timeline_a_id=tl_a_name,
                timeline_b_id=tl_b_name,
                is_synchronous=False,
                metadata=metadata,
            )
            conceptual_claims.append(claim)

all_claims = sync_claims + conceptual_claims + nomatch_claims
bundle.add_match_claims(all_claims)

{
    "synchronous": len(sync_claims),
    "conceptual": len(conceptual_claims),
    "nomatch": len(nomatch_claims),
    "total": len(all_claims),
}

# %% [markdown]
# ## 5. Inspect the Results
#
# ### Synchronous claims (with AlignmentAnchors)
#
# These claims carry coordinate pairs (start and end) that enable temporal
# alignment between versions.  Each interval match corresponds to a pair
# of section boundaries in seconds.
#
# The MatchClaim's rich display shows timelines, coordinates, events, and
# metadata — no need to compile info-dicts manually.

# %%
# Display an example synchronous claim (shows timeline IDs, coordinates, events)
sync_claims[0]

# %%
# Summary of all synchronous claims
{
    "synchronous_claims": len(sync_claims),
    "is_interval": all(c.is_interval for c in sync_claims),
}

# %% [markdown]
# ### Conceptual claims (no anchors)
#
# These record structural equivalence without temporal commitment — for
# instance, "both versions have an Intro" without asserting that the intros
# can be aligned beat-by-beat.

# %%
# Display an example conceptual claim (no coordinates, just timeline connection)
conceptual_claims[0] if conceptual_claims else "No conceptual claims"

# %%
{"conceptual_claims": len(conceptual_claims)}

# %% [markdown]
# ### NOMATCH sentinels
#
# These explicitly record that a section has no equivalent in the target
# version — a positive assertion of absence, not a mere gap in the data.
# For instance, the "Instrumental Part" in the studio recording has no
# equivalent in Demo1.

# %%
# Display an example NOMATCH claim
nomatch_claims[0] if nomatch_claims else "No NOMATCH claims"

# %%
{"nomatch_sentinels": len(nomatch_claims)}

# %% [markdown]
# ## Summary
#
# This notebook demonstrated how to encode heterogeneous musicological
# relationships in a single, queryable structure:
#
# | Pattern | API |
# |---------|-----|
# | Load TiLiA annotations | `TiliaJsonLoader.from_file()` |
# | Look up sections by name | `tl.get_events(name=...)` |
# | Synchronous alignment | `MatchClaim.from_events(..., is_synchronous=True)` |
# | Conceptual correspondence | `MatchClaim(..., is_synchronous=False)` |
# | Explicit absence | `MatchClaim.nomatch()` |
# | Collect in bundle | `bundle.add_match_claims(claims)` |

# %%
