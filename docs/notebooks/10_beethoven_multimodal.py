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

from timetoalign import AudioLoader, RepoVizzLoader
from timetoalign.alignment import TimelineGroup
from timetoalign.loader.physical.eep_notes import EepNotesLoader

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
