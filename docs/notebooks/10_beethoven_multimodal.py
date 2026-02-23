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
from PIL import Image

from timetoalign import (
    AudioLoader,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    NumberType,
    RepoVizzLoader,
    TableMap,
    TimeUnit,
)
from timetoalign.alignment import AlignmentBundle, TimelineGroup
from timetoalign.alignment.matching import (
    match_notes_by_attributes,
    prepare_abc_notes_for_matching,
    prepare_eep_notes_for_matching,
)
from timetoalign.loader.physical.eep_notes import EepNotesLoader
from timetoalign.loader.score import TSVLoader
from timetoalign.timelines.flow import (
    FlowMode,
    ScoreFlowController,
    create_unfolded_timeline,
)
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
clt1 = abc_loader.create_timeline(uid="clt1")
clt1

# %% [markdown]
# ## 7. DGT1: OMR Ground Truth
#
# The OMR data contains 3,190 note head bounding boxes across 22 score pages.
# Each page has 2 systems (except the last which has 1), giving 43 system
# segments in reading order. Note events use `Left` (start) and `Width`
# (duration) as pixel coordinates. Each system's `onset_beats` values
# provide a c-map from pixels to quarters.
#
# **Architecture:** `SegmentLine[SegmentLine[DiscreteGraphicalTimeline]]` →
# 22 page `SegmentLine[DiscreteGraphicalTimeline]` segments → 2 system sub-segments each.

# %%
OMR_CSV = DATA_DIR / "OMR_groundtruth" / "OMR_xml_by_score" / "omr_note_heads.csv"
OMR_IMAGES = DATA_DIR / "OMR_groundtruth" / "Images"
omr_df = pd.read_csv(OMR_CSV)
IMAGE_WIDTH = Image.open(next(OMR_IMAGES.glob("*.png"))).size[0]

# %% [markdown]
# Build the DGT1 bottom-up: system segments →
# page `SegmentLine[DiscreteGraphicalTimeline]` →
# top-level `SegmentLine[SegmentLine[DiscreteGraphicalTimeline]]`.
# Events and c-maps must be added **before** a timeline is locked as a child.

# %%
noteheads = pd.DataFrame(
    {
        "start": omr_df["Nodes.Node.Left"].astype(int),
        "end": (omr_df["Nodes.Node.Left"] + omr_df["Nodes.Node.Width"]).astype(int),
        "onset_beats": omr_df["onset_beats"].astype(float),
        "pitch": omr_df["pitch"],
        "staff_id": omr_df["staff_id"].astype(int),
        "midi_pitch": omr_df["midi_pitch_code"].astype(int),
        "top": omr_df["Nodes.Node.Top"].astype(int),
        "page": omr_df["@pageIndex"],
        "spacing_run_id": omr_df["spacing_run_id"],
    }
)

dgt1 = SegmentLine(
    length=0,
    unit=TimeUnit.pixels,
    number_type=NumberType.int,
    segment_type=SegmentLine,
    inner_segment_type=DiscreteGraphicalTimeline,
)

for page_idx, page_data in noteheads.groupby("page", sort=True):
    # Systems ordered by vertical position (top first = reading order)
    sys_top = page_data.groupby("spacing_run_id")["top"].min()
    sys_order = sys_top.sort_values().index

    page = SegmentLine(
        length=0,
        unit=TimeUnit.pixels,
        number_type=NumberType.int,
        segment_type=DiscreteGraphicalTimeline,
    )

    for sys_rank, sys_id in enumerate(sys_order):
        sys_data = page_data[page_data["spacing_run_id"] == sys_id]

        system = DiscreteGraphicalTimeline(
            length=IMAGE_WIDTH,
            uid=f"p{page_idx}_s{sys_rank}",
            name=f"Page {page_idx + 1}, System {sys_rank + 1}",
        )

        events = sys_data.drop(columns=["page", "spacing_run_id"])
        system.add_events(events.assign(event_type="Notehead").to_dict("records"))

        # C-map: pixels → quarters (deduplicated for chords at the same x)
        pairs = (
            events[["start", "onset_beats"]]
            .drop_duplicates("start")
            .sort_values("start")
        )
        if len(pairs) >= 2:
            system.add_conversion_map(
                TableMap(
                    x_values=pairs["start"].tolist(),
                    y_values=pairs["onset_beats"].tolist(),
                    source_unit="pixels",
                    target_unit="quarters",
                    uid=f"p{page_idx}_s{sys_rank}_px_to_qb",
                )
            )

        page.append_segment(system)

    dgt1.append_segment(page, name=f"page_{page_idx}")

dgt1

# %% [markdown]
# ## 8. OpenScore (4th Movement Only)
#
# The OpenScore edition covers all 4 movements. We use the flow controller
# to identify section breaks (movement boundaries) and extract the 4th
# movement as a child timeline.

# %%
OPENSCORE_DIR = DATA_DIR / "OpenScoreSQ"
os_loader = TSVLoader.from_file(
    OPENSCORE_DIR / "sq8913219.notes.tsv",
    OPENSCORE_DIR / "sq8913219.measures.tsv",
)
os_full = os_loader.create_timeline(uid="openscore_full")
os_full

# %% [markdown]
# The `ScoreFlowController` derives section boundaries from the score's
# flow control markup. Splitting at those coordinates creates one region
# per movement.

# %%
flow = ScoreFlowController(os_loader.store.measures)
boundaries = flow.get_section_boundary_coordinates()
os_full.create_regions_from_boundaries(
    [0, *[float(b) for b in boundaries], float(os_full.length.value)], prefix="movement"
)
openscore = os_full.create_child_from_region("movement_4", uid="openscore")
openscore

# %% [markdown]
# The four movement regions and the extracted child timeline:

# %%
os_full.diagram(show={"regions", "children"})

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
len(abc_prepared)  # note onsets after dropping tied notes

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

# %% [markdown]
# ---
# # Part III: Emerson Group + Cross-Group Transfer (Group 5)
#
# The Emerson group connects a commercial recording to a second score
# edition via segment-level alignment. Unlike the EEP groups (per-note
# alignment), the Emerson recording is aligned at the level of 10
# structural sections (alpha through kappa), derived from the score's
# repeat structure.
#
# - **CLT2**: ABC v1.0 ("recordings edition") score — `ContinuousLogicalTimeline`
# - **DPT16**: Emerson String Quartet recording (DG 1997) — `ContinuousPhysicalTimeline`

# %% [markdown]
# ## 11. Building Group 5: Emerson Recording

# %% [markdown]
# ### 11.1 CLT2: Recordings Edition Score
#
# The recordings edition uses the same measure/repeat structure as CLT1 but
# was encoded independently (ABC v1.0). We load it via TSVLoader and use its
# flow controller to compute the traversal map.

# %%
REC_DIR = DATA_DIR / "recordings"
rec_loader = TSVLoader.from_file(
    REC_DIR / "Beethoven_Op018No4-04.notes.tsv",
    REC_DIR / "Beethoven_Op018No4-04.measures.tsv",
    REC_DIR / "Beethoven_Op018No4-04.harmonies.tsv",
)
clt2 = rec_loader.create_timeline(uid="clt2")
clt2

# %% [markdown]
# ### 11.2 Flow Control: Inspect the Score's Repeat Structure
#
# The `ScoreFlowController` identifies atomic sections and flow control
# events (repeats, voltas) from the measure data.

# %%
rec_controller = ScoreFlowController(rec_loader.store.measures)
rec_controller

# %% [markdown]
# Compute the default flow (all repeats taken) and a single-pass flow
# (no repeats, last volta only) for comparison:

# %%
default_flow = rec_controller.compute_flow(FlowMode.DEFAULT)
default_flow

# %%
single_flow = rec_controller.compute_flow(FlowMode.SINGLE_PASS)
single_flow

# %% [markdown]
# ### 11.3 Unfolded Timeline via TraversalMap 2
#
# Unfolding CLT2 via the default flow creates a new timeline with events
# reordered and duplicated according to the repeat structure. The unfolded
# timeline carries a reverse `FlowMap` for tracing back to the original.

# %%
clt2_unfolded = create_unfolded_timeline(clt2, default_flow, rec_controller)
clt2_unfolded

# %% [markdown]
# ### 11.4 DPT16: Emerson Recording Alignment
#
# The `measureMapAudio.csv` provides a 10-segment alignment between the
# unfolded score (floating measures) and the Emerson recording (seconds).
# Each segment is labeled with a Greek letter (alpha through kappa).

# %%
ema_df = pd.read_csv(
    REC_DIR / "Beethoven_Op018No4-04_EmersonStringQuartet_DG_measureMapAudio.csv",
    sep="\t",
    index_col=0,
)
ema_df

# %% [markdown]
# Create DPT16 as a `ContinuousPhysicalTimeline` in seconds, with a
# `TableMap` linking the unfolded measure boundaries to audio timestamps:

# %%
dpt16_duration = float(ema_df["seconds_end"].iloc[-1])
dpt16 = ContinuousPhysicalTimeline(length=dpt16_duration, uid="dpt16")

# TableMap: unfolded floating measures -> seconds (boundary correspondences)
unfold_coords = ema_df["measure_unfold_start"].tolist() + [
    ema_df["measure_unfold_end"].iloc[-1]
]
seconds_coords = ema_df["seconds_start"].tolist() + [ema_df["seconds_end"].iloc[-1]]
dpt16.add_conversion_map(
    TableMap(
        x_values=seconds_coords,
        y_values=unfold_coords,
        source_unit="seconds",
        target_unit="measures",
        uid="dpt16_sec_to_fm",
    )
)
dpt16

# %% [markdown]
# ### 11.5 Emerson Group
#
# Both timelines go into one group. The group uses the DPT16 c-map
# boundaries as alignment anchors (seconds <-> unfolded floating measures).

# %%
emerson_group = TimelineGroup(
    id="emerson",
    name="Emerson Recording (DG 1997)",
    timelines=[clt2, dpt16],
)
emerson_group

# %% [markdown]
# ## 12. The AlignmentBundle
#
# The bundle collects all 5 groups and connects them via MatchClaims.
# Within each group, coordinate transfer uses linear interpolation.
# Between groups, WarpMaps (built from MatchClaims) enable cross-domain
# transfer.

# %%
bundle = AlignmentBundle(name="Beethoven Op.18/4 — Multimodal Alignment")

bundle.add_group(score_group)
bundle.add_group(normal_group)
bundle.add_group(mechanical_group)
bundle.add_group(exaggerated_group)
bundle.add_group(emerson_group)

for dpt_id in ["dpt1", "dpt6", "dpt11"]:
    bundle.add_match_claims(match_results[dpt_id].match_claims)

bundle

# %% [markdown]
# Match claims per connection:

# %%
pd.DataFrame(
    [
        {
            "recording": name,
            "source": dpt_id,
            "target": "clt1",
            "matched": match_results[dpt_id].n_matched,
            "unmatched_source": match_results[dpt_id].n_unmatched_source,
            "unmatched_target": match_results[dpt_id].n_unmatched_target,
        }
        for name, dpt_id in [
            ("Normal", "dpt1"),
            ("Mechanical", "dpt6"),
            ("Exaggerated", "dpt11"),
        ]
    ]
).set_index("recording")

# %% [markdown]
# ## 13. Cross-Group Coordinate Transfer
#
# The bundle's `get_timestamp_at()` method is the primary interface for
# cross-domain coordinate transfer. Given a coordinate on any timeline,
# it returns corresponding coordinates on all connected timelines —
# regardless of domain.

# %% [markdown]
# ### 13.1 Inspecting CLT1's Harmony Annotations
#
# Before transferring coordinates, let's see what harmonic events live
# on CLT1. The annotations child carries all harmony labels from the
# ABC score:

# %%
annotations_df = clt1.get_child("annotations").get_events().to_pandas()
annotations_df[["start", "name"]].head(15)

# %% [markdown]
# ### 13.2 USE CASE A — Transfer a Harmony Across All Groups
#
# The `V7` at quarterbeat 79 (m. 20) is a dominant seventh — one of the
# most recognizable sonorities. Where does this moment land across all
# 5 groups, in every domain?

# %%
bundle.get_timestamp_at(79.0, "clt1", format="prefix")

# %% [markdown]
# The nested format groups results by `TimelineGroup`, making it easy
# to see the cross-domain correspondences. Note that sample-based
# coordinates (DPT1–DPT15) are integers — as they must be:

# %%
bundle.get_timestamp_at(79.0, "clt1", format="nested")

# %% [markdown]
# ### 13.3 Verification: Listening to the Transferred Timestamps
#
# The timestamps above give sample counts.  Converting to seconds via
# each audio timeline's `SamplesToSeconds` C-map yields seek positions
# you can verify in any audio player:

# %%
v7_ts = bundle.get_timestamp_at(79.0, "clt1", format="flat")
pd.Series(
    {
        name: f"{float(bundle.timelines[uid].convert_to(v7_ts[k], 'seconds').value):.3f}s"
        for name, uid, k in (
            (n, u, next(k for k in v7_ts if k.startswith(u)))
            for n, u in [
                ("Normal", "dpt1"),
                ("Mechanical", "dpt6"),
                ("Exaggerated", "dpt11"),
            ]
        )
    },
    name="V7 at qb 79 — seek to",
)

# %% [markdown]
# ### 13.4 USE CASE B — Transfer Atomic Section Boundaries Across Groups
#
# The score's repeat structure defines atomic sections (A through M).
# The `ScoreFlowController` computes each section's **unfolded**
# quarterbeat start coordinate — the position in the playthrough
# order, which is what the bundle's WarpMaps expect:

# %%
abc_controller = ScoreFlowController(abc_loader.store.measures)
abc_flow = abc_controller.compute_flow(FlowMode.DEFAULT)
section_coords = abc_controller.get_atomic_section_coordinates(flow=abc_flow)
section_coords

# %% [markdown]
# Transfer every section boundary to all connected timelines:

# %%
boundary_df = pd.DataFrame(
    [
        bundle.get_timestamp_at(float(qb), "clt1", format="flat")
        for qb in section_coords.values()
    ],
    index=list(section_coords.keys()),
)
boundary_df.index.name = "section"
boundary_df

# %% [markdown]
# Each row gives the exact coordinate of a section boundary in every
# timeline and domain. The sample counts are integers; the seconds and
# quarterbeats are floats — matching each timeline's native type.

# %% [markdown]
# ## 14. Summary & Key Takeaways
#
# > *"Any two events in the bundle can be related with each other — regardless of whether
# > they live on the same timeline, in the same group, or even in the
# > same domain — as long as a path of MatchClaims or ConversionMaps
# > connects them."*
#
# ### Patterns Demonstrated
#
# | Pattern | Example | Section |
# |---------|---------|---------|
# | `build_recording_group()` | Reusable factory for EEP recordings | 2-4 |
# | `TSVLoader.from_file()` | Load ABC score with notes, measures, annotations | 6 |
# | `SegmentLine` nesting | OMR pages → systems → noteheads | 7 |
# | Region extraction | OpenScore 4-movement → movement 4 child | 8 |
# | `match_notes_by_attributes()` | EEP ↔ ABC note matching | 10 |
# | `ScoreFlowController.diagram()` | ASCII flow control visualization | 11 |
# | `create_unfolded_timeline()` | Repeat expansion via `FlowMap` | 11 |
# | `Flow.diagram()` | Flow inspection | 11 |
# | `get_atomic_section_coordinates()` | Section boundaries in one call | 13 |
# | `AlignmentBundle` | Multi-group cross-domain transfer | 12-13 |
# | `get_timestamp_at()` | Universal coordinate transfer | 13 |
#
# **5 groups, 23 timelines, 3 domains, 1 bundle.**

# %%
