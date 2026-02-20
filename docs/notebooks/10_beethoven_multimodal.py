# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.3
#   kernelspec:
#     display_name: TimeToAlign
#     language: python
#     name: tta
# ---

# %% [markdown]
# # 10: Multimodal Alignment — From 5 Groups to Cross-Domain Coordinate Transfer
#
# **Figure 3 acid test** for TimeToAlign! — 16+ timelines across all 3 domains
# (Physical, Logical, Graphical) in 5 `TimelineGroups` within one `AlignmentBundle`.
#
# **Structure:**
# 1. **Part I**: Build 3 recording groups (Groups 1-3) — 15 DPTs
# 2. **Part II**: Build Score group (Group 4) + align with recordings
# 3. **Part III**: Build Emerson group (Group 5) + cross-group coordinate transfer

# %% [markdown]
# ## 0. Gold Standard Reference Values
#
# | ID | Description | Samples | Rate | Grp |
# |----|-------------|---------|------|-----|
# | DPT1-5 | Normal | 11,753,638 / 11,195 / 22,389 / 45,844 / 63,965 | 44.1k / 42 / 84 / 172 / 240 | 1 |
# | DPT6-10 | Mechanical | 12,426,696 / 11,836 / 23,671 / 48,469 / 67,628 | same rates | 2 |
# | DPT11-15 | Exaggerated | 8,197,748 / 7,808 / 15,616 / 31,975 / 44,614 | same rates | 3 |
#
# | Recording | Notes | Matched | Unmatched EEP | Unmatched ABC |
# |-----------|-------|---------|---------------|---------------|
# | Normal | 4,026 | 3,740 | 16 | 10 |
# | Mechanical | 4,026 | 3,741 | 15 | 9 |
# | Exaggerated | 2,820 | 2,650 | 4 | 1,100 |

# %% [markdown]
# ## 1. Setup

# %%
from pathlib import Path

import pandas as pd

from timetoalign import (
    AudioLoader,
    DiscreteGraphicalTimeline,
    NumberType,
    RepoVizzLoader,
    TableMap,
    TimeUnit,
)
from timetoalign.alignment import TimelineGroup
from timetoalign.alignment.matching import (
    match_notes_by_attributes,
    prepare_abc_notes_for_matching,
    prepare_eep_notes_for_matching,
)
from timetoalign.loader.physical.eep_notes import EepNotesLoader
from timetoalign.loader.score import TSVLoader
from timetoalign.timelines.types import SegmentLine

_notebook_dir = Path(".").resolve()
DATA_DIR = (
    _notebook_dir.parent.parent
    / "tests"
    / "data"
    / "score"
    / "beethoven_op18-4iv_multimodal"
)

NORMAL_DIR = DATA_DIR / "StringQuartetEEP_I_Normal"
MECHANICAL_DIR = DATA_DIR / "StringQuartetEEP_I_Mechanical"
EXAGGERATED_DIR = DATA_DIR / "StringQuartetEEP_I_Exaggerated"

NORMAL_PREFIX = "StringQuartetEEP_I_Normal"
MECHANICAL_PREFIX = "StringQuartetEEP_I_Mechanical"
EXAGGERATED_PREFIX = "StringQuartetEEP_I_Exaggerated"


# %% [markdown]
# Each EEP recording directory contains 5 modalities (audio, 3 feature types,
# MoCap) plus `.notes` files with annotated note events. The function below
# builds a `TimelineGroup` from one such directory, adding the note events as
# a child of the audio timeline via `use_conversion_map=True` (notes are in
# seconds, audio in samples — the C-map handles the conversion automatically).


# %%
def build_recording_group(recording_dir, prefix, group_id, group_name, dpt_base):
    """Build a TimelineGroup from one EEP recording directory.

    Creates 5 DPTs (audio, tonal, lowlevel, rhythm, MoCap) and loads the
    EEP note annotations. The notes timeline is added as a child of the
    audio DPT via automatic unit conversion (seconds -> samples).

    Args:
        recording_dir: Path to the recording directory.
        prefix: Filename prefix (e.g. "StringQuartetEEP_I_Normal").
        group_id: ID for the TimelineGroup.
        group_name: Human-readable name for the group.
        dpt_base: Starting DPT number (e.g. 1 for dpt1-dpt5).

    Returns:
        TimelineGroup with 5 DPTs, audio DPT containing notes as a child.
    """
    n = dpt_base
    audio = AudioLoader.from_file(recording_dir / f"{prefix}_mono.mp3").to_timeline(
        uid=f"dpt{n}"
    )
    tonal = AudioLoader.from_file(
        recording_dir / f"{prefix}_mono.wav.tonal.ChordsStrength.wav"
    ).to_timeline(uid=f"dpt{n + 1}")
    lowlevel = AudioLoader.from_file(
        recording_dir / f"{prefix}_mono.wav.lowlevel.Dissonance.wav"
    ).to_timeline(uid=f"dpt{n + 2}")
    rhythm = AudioLoader.from_file(
        recording_dir / f"{prefix}_mono.wav.rhythm.BeatsLoudness.wav"
    ).to_timeline(uid=f"dpt{n + 3}")
    mocap = RepoVizzLoader.from_file(recording_dir / "vln1_bb_angle.csv").to_timeline(
        uid=f"dpt{n + 4}"
    )

    # Load EEP notes and add as child of the audio timeline
    notes = EepNotesLoader()
    notes.load(*sorted(recording_dir.glob("*_align_*.notes")))
    notes_tl = notes.create_timeline(uid=f"{group_id}_notes")
    audio.add_child(notes_tl, offset=0, use_conversion_map=True)

    return TimelineGroup(
        id=group_id,
        name=group_name,
        timelines=[audio, tonal, lowlevel, rhythm, mocap],
    )


# %% [markdown]
# ---
# # Part I: Three Recording Groups (Groups 1-3)
#
# Each EEP recording = 5 DPTs (audio + 3 feature types + MoCap) at different
# sampling rates, all sharing the same physical duration. Note events live
# as a child of the audio DPT.

# %% [markdown]
# ## 2. Group 1: Normal Recording (DPT1-DPT5)

# %%
normal_group = build_recording_group(
    NORMAL_DIR, NORMAL_PREFIX, "normal", "Normal Recording", dpt_base=1
)
normal_group

# %% [markdown]
# The audio timeline now carries the note annotations as a child:

# %%
normal_group.get_timeline("dpt1")

# %% [markdown]
# ## 3. Group 2: Mechanical Recording (DPT6-DPT10)

# %%
mechanical_group = build_recording_group(
    MECHANICAL_DIR, MECHANICAL_PREFIX, "mechanical", "Mechanical Recording", dpt_base=6
)
mechanical_group

# %% [markdown]
# ## 4. Group 3: Exaggerated Recording (DPT11-DPT15)
#
# Shorter recording (~186s) — stops after measure 131.

# %%
exaggerated_group = build_recording_group(
    EXAGGERATED_DIR,
    EXAGGERATED_PREFIX,
    "exaggerated",
    "Exaggerated Recording",
    dpt_base=11,
)
exaggerated_group

# %% [markdown]
# ## 5. Part I Summary
#
# 3 groups, 15 timelines. Each audio DPT carries note events as a child
# timeline, making them accessible for matching in Part II.
#
# **Next:** Part II builds the Score group and aligns each recording via note matching.

# %% [markdown]
# ---
# # Part II: Score Group + Alignment to Recordings (Group 4)
#
# The score group brings together three representations of the same music:
#
# - **CLT1**: ABC v2.6 score (notes, measures, harmonies) — `ContinuousLogicalTimeline`
# - **DGT1**: OMR ground truth (3,190 note heads across 22 pages) — `DiscreteGraphicalTimeline`
# - **OpenScore**: OpenScore String Quartet edition (4th movement) — `ContinuousLogicalTimeline`
#
# All three go into one `TimelineGroup`. Cross-domain coordinate transfer
# (pixels ↔ quarters ↔ seconds) works automatically via linear interpolation.

# %% [markdown]
# ## 6. CLT1: ABC v2.6 Score

# %%
ABC_DIR = DATA_DIR / "ABC"
abc_loader = TSVLoader.from_file(
    ABC_DIR / "n04op18-4_04.notes.tsv",
    ABC_DIR / "n04op18-4_04.measures.tsv",
    ABC_DIR / "n04op18-4_04.harmonies.tsv",
)
abc_loader.store.summary()

# %%
clt1 = abc_loader.create_timeline(uid="clt1")
clt1

# %%
{
    "CLT1 notes": len(abc_loader.store.notes),
    "CLT1 measures": len(abc_loader.store.measures),
    "CLT1 annotations": len(abc_loader.store.annotations),
    "CLT1 length": clt1.length,
}

# %% [markdown]
# ## 7. DGT1: OMR Ground Truth
#
# The OMR data contains 3,190 note head bounding boxes across 22 score pages.
# Each page has 2 systems (except the last which has 1), giving 43 system
# segments in reading order. Note events use `Left` (start) and `Width`
# (duration) as pixel coordinates. Each system's `onset_beats` values
# provide a c-map from pixels to quarters.
#
# **Architecture:** `SegmentLine` → 22 page segments → 2 system sub-segments each.

# %%
OMR_CSV = DATA_DIR / "OMR_groundtruth" / "OMR_xml_by_score" / "omr_note_heads.csv"
omr_df = pd.read_csv(OMR_CSV)

IMAGE_WIDTH = 2475  # pixels (all pages from the same PDF)

{
    "Total note heads": len(omr_df),
    "Pages": omr_df["@pageIndex"].nunique(),
    "Image width": f"{IMAGE_WIDTH} px",
}

# %% [markdown]
# Build the DGT1 bottom-up: system segments → page segments → SegmentLine.
# Events and c-maps must be added **before** a timeline is locked as a child.

# %%
dgt1 = SegmentLine(length=0, unit=TimeUnit.pixels, number_type=NumberType.int)

for page_idx in range(22):
    page_data = omr_df[omr_df["@pageIndex"] == page_idx]

    # Identify systems by vertical position (top system first = reading order)
    sys_top = page_data.groupby("spacing_run_id")["Nodes.Node.Top"].min()
    sys_ids_sorted = sys_top.sort_values().index.tolist()

    # Page is a SegmentLine of system sub-segments
    page = SegmentLine(length=0, unit=TimeUnit.pixels, number_type=NumberType.int)

    for sys_rank, sys_id in enumerate(sys_ids_sorted):
        sys_data = page_data[page_data["spacing_run_id"] == sys_id]

        # System segment spans the full image width
        system = DiscreteGraphicalTimeline(
            length=IMAGE_WIDTH,
            uid=f"p{page_idx}_s{sys_rank}",
            name=f"Page {page_idx + 1}, System {sys_rank + 1}",
        )

        # Add notehead interval events: Left=start, Left+Width=end
        events = []
        for _, row in sys_data.iterrows():
            events.append(
                {
                    "event_type": "Notehead",
                    "start": int(row["Nodes.Node.Left"]),
                    "end": int(row["Nodes.Node.Left"] + row["Nodes.Node.Width"]),
                    "pitch": row["pitch"],
                    "staff_id": int(row["staff_id"]),
                    "onset_beats": float(row["onset_beats"]),
                    "midi_pitch": int(row["midi_pitch_code"]),
                    "top": int(row["Nodes.Node.Top"]),
                }
            )
        system.add_events(events)

        # C-map: Left pixels → onset_beats (quarters)
        # Deduplicate by Left (chords at the same x share the same onset)
        pairs = sorted(
            {(e["start"], e["onset_beats"]) for e in events},
            key=lambda p: p[0],
        )
        if len(pairs) >= 2:
            system.add_conversion_map(
                TableMap(
                    x_values=[p[0] for p in pairs],
                    y_values=[p[1] for p in pairs],
                    source_unit="pixels",
                    target_unit="quarters",
                    uid=f"p{page_idx}_s{sys_rank}_px_to_qb",
                )
            )

        page.append_segment(system)

    dgt1.append_segment(page, name=f"page_{page_idx}")

dgt1

# %%
{
    "DGT1 total length": f"{int(dgt1.length.value):,} px",
    "Page segments": dgt1.n_segments,
    "System segments": sum(
        child.n_segments
        for _, _, child in dgt1.iter_segments()
        if hasattr(child, "n_segments")
    ),
}

# %% [markdown]
# ## 8. OpenScore (4th Movement Only)
#
# The OpenScore edition covers all 4 movements. Only the 4th movement
# (mc ≥ 584, *Presto* in 2/2) participates in the score group.

# %%
OPENSCORE_DIR = DATA_DIR / "OpenScoreSQ"
os_loader = TSVLoader.from_file(
    OPENSCORE_DIR / "sq8913219.notes.tsv",
    OPENSCORE_DIR / "sq8913219.measures.tsv",
)

# Full quartet timeline (all 4 movements)
os_full = os_loader.create_timeline(uid="openscore_full")

{
    "Full quartet": os_full.length,
    "Total notes": len(os_loader.store.notes),
    "Total measures": len(os_loader.store.measures),
}

# %% [markdown]
# Extract movement 4 as a region, then create a child timeline from it.
# Movement 4 starts at mc 584 (quarterbeat 3125/2 = 1562.5).

# %%
# Movement 4 boundary in the full score
os_measures_df = os_loader.store.measures.to_pandas()
mov4_start_qb = float(os_measures_df[os_measures_df["mc"] == 584]["start"].iloc[0])
mov4_end_qb = float(os_full.length.value)

os_full.create_regions_from_boundaries(
    [mov4_start_qb, mov4_end_qb], names=["movement_4"]
)
openscore = os_full.create_child_from_region("movement_4", uid="openscore")

openscore

# %%
{
    "Movement 4 start": f"{mov4_start_qb} qb (mc 584)",
    "Movement 4 length": openscore.length,
}

# %% [markdown]
# ## 9. Score Group (Group 4)
#
# All three score representations in one `TimelineGroup`. Cross-domain
# coordinate transfer (pixels ↔ quarters) works via linear interpolation.

# %%
score_group = TimelineGroup(
    id="score",
    name="Score (ABC + OMR + OpenScore)",
    timelines=[clt1, dgt1, openscore],
)
score_group

# %% [markdown]
# ## 10. Aligning Recordings with the Score via Note Matching
#
# Each EEP recording's note events (seconds, pitch, staff) are matched
# against the ABC unfolded score notes (quarterbeats, pitch, staff) using
# greedy sequential matching. The result: `MatchClaim` objects that
# connect recording coordinates to score coordinates.

# %%
# Load unfolded ABC notes (the target for all three recordings)
abc_unfolded_df = pd.read_csv(ABC_DIR / "n04op18-4_04_unfolded.notes.tsv", sep="\t")
abc_prepared = prepare_abc_notes_for_matching(abc_unfolded_df)

{
    "ABC unfolded rows": len(abc_unfolded_df),
    "ABC note onsets (after dropping tied)": len(abc_prepared),
}

# %% [markdown]
# Match each recording against the score. The `source_timeline_id` and
# `target_timeline_id` are the audio DPT and CLT1 respectively — these
# appear in the resulting `MatchClaim` anchors.

# %%
match_results = {}
for rec_dir, dpt_id in [
    (NORMAL_DIR, "dpt1"),
    (MECHANICAL_DIR, "dpt6"),
    (EXAGGERATED_DIR, "dpt11"),
]:
    eep = EepNotesLoader()
    eep.load(*sorted(rec_dir.glob("*_align_*.notes")))
    eep_prepared = prepare_eep_notes_for_matching(eep.events.to_pandas())
    match_results[dpt_id] = match_notes_by_attributes(
        eep_prepared,
        abc_prepared,
        match_columns=["pitch", "staff"],
        source_coord_column="start",
        target_coord_column="quarterbeats_playthrough",
        source_timeline_id=dpt_id,
        target_timeline_id="clt1",
    )

normal_match = match_results["dpt1"]
mechanical_match = match_results["dpt6"]
exaggerated_match = match_results["dpt11"]

# %%
{
    "Normal": normal_match.summary(),
    "Mechanical": mechanical_match.summary(),
    "Exaggerated": exaggerated_match.summary(),
}

# %% [markdown]
# ## Part II Summary
#
# The score group unites 3 score representations across 2 domains (Logical +
# Graphical). Note matching produced MatchClaims connecting each recording
# group's audio timeline to CLT1:
#
# | Recording | Matched | Unmatched EEP | Unmatched ABC |
# |-----------|---------|---------------|---------------|
# | Normal | 3,740 | 16 | 10 |
# | Mechanical | 3,741 | 15 | 9 |
# | Exaggerated | 2,650 | 4 | 1,100 |
#
# **Next:** Part III adds the Emerson group and demonstrates cross-group
# coordinate transfer using an `AlignmentBundle`.
