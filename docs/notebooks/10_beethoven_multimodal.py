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
# | ID | Description | Samples | Rate | Group |
# |----|-------------|---------|------|-------|
# | DPT1-5 | Normal: audio, tonal, lowlevel, rhythm, MoCap | 11,753,638 / 11,195 / 22,389 / 45,844 / 63,965 | 44,100 / 42 / 84 / 172 / 240 Hz | 1 |
# | DPT6-10 | Mechanical: same modalities | 12,426,696 / 11,836 / 23,671 / 48,469 / 67,628 | same rates | 2 |
# | DPT11-15 | Exaggerated: same modalities | 8,197,748 / 7,808 / 15,616 / 31,975 / 44,614 | same rates | 3 |
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
# ---
# # Part I: Three Recording Groups (Groups 1-3)
#
# Each EEP recording = 5 DPTs (audio + 3 feature types + MoCap) at different
# sampling rates, all sharing the same physical duration.

# %% [markdown]
# ## 2. Group 1: Normal Recording (DPT1-DPT5)
#
# The `SamplesToSeconds` C-map attached by `to_timeline()` carries the sample
# rate, so the timeline itself knows its temporal resolution.

# %%
dpt1 = AudioLoader.from_file(NORMAL_DIR / f"{NORMAL_PREFIX}_mono.mp3").to_timeline(
    uid="dpt1"
)
dpt2 = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PREFIX}_mono.wav.tonal.ChordsStrength.wav"
).to_timeline(uid="dpt2")
dpt3 = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PREFIX}_mono.wav.lowlevel.Dissonance.wav"
).to_timeline(uid="dpt3")
dpt4 = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PREFIX}_mono.wav.rhythm.BeatsLoudness.wav"
).to_timeline(uid="dpt4")
dpt5 = RepoVizzLoader.from_file(NORMAL_DIR / "vln1_bb_angle.csv").to_timeline(
    uid="dpt5"
)

{
    uid: (tl.length, tl.get_conversion_map("seconds").sample_rate)
    for uid, tl in [
        ("dpt1", dpt1),
        ("dpt2", dpt2),
        ("dpt3", dpt3),
        ("dpt4", dpt4),
        ("dpt5", dpt5),
    ]
}

# %% [markdown]
# EEP `.notes` files contain onset/offset/pitch per instrument.
# Staff is inferred from the filename suffix.

# %%
notes_normal = EepNotesLoader()
notes_normal.load(*sorted(NORMAL_DIR.glob("*_align_*.notes")))
notes_normal.events.to_pandas()["staff"].value_counts().sort_index()

# %% [markdown]
# All 5 timelines share the same physical duration at different sampling rates.
# The `TimelineGroup` makes them commensurable.

# %%
normal_group = TimelineGroup(
    id="normal", name="Normal Recording", timelines=[dpt1, dpt2, dpt3, dpt4, dpt5]
)
normal_group

# %% [markdown]
# ## 3. Group 2: Mechanical Recording (DPT6-DPT10)

# %%
dpt6 = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PREFIX}_mono.mp3"
).to_timeline(uid="dpt6")
dpt7 = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PREFIX}_mono.wav.tonal.ChordsStrength.wav"
).to_timeline(uid="dpt7")
dpt8 = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PREFIX}_mono.wav.lowlevel.Dissonance.wav"
).to_timeline(uid="dpt8")
dpt9 = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PREFIX}_mono.wav.rhythm.BeatsLoudness.wav"
).to_timeline(uid="dpt9")
dpt10 = RepoVizzLoader.from_file(MECHANICAL_DIR / "vln1_bb_angle.csv").to_timeline(
    uid="dpt10"
)

notes_mech = EepNotesLoader()
notes_mech.load(*sorted(MECHANICAL_DIR.glob("*_align_*.notes")))

mechanical_group = TimelineGroup(
    id="mechanical",
    name="Mechanical Recording",
    timelines=[dpt6, dpt7, dpt8, dpt9, dpt10],
)
mechanical_group

# %% [markdown]
# ## 4. Group 3: Exaggerated Recording (DPT11-DPT15)
#
# Shorter recording (~186s) — stops after measure 131.

# %%
dpt11 = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PREFIX}_mono.mp3"
).to_timeline(uid="dpt11")
dpt12 = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PREFIX}_mono.wav.tonal.ChordsStrength.wav"
).to_timeline(uid="dpt12")
dpt13 = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PREFIX}_mono.wav.lowlevel.Dissonance.wav"
).to_timeline(uid="dpt13")
dpt14 = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PREFIX}_mono.wav.rhythm.BeatsLoudness.wav"
).to_timeline(uid="dpt14")
dpt15 = RepoVizzLoader.from_file(EXAGGERATED_DIR / "vln1_bb_angle.csv").to_timeline(
    uid="dpt15"
)

notes_exag = EepNotesLoader()
notes_exag.load(*sorted(EXAGGERATED_DIR.glob("*_align_*.notes")))

exaggerated_group = TimelineGroup(
    id="exaggerated",
    name="Exaggerated Recording",
    timelines=[dpt11, dpt12, dpt13, dpt14, dpt15],
)
exaggerated_group

# %% [markdown]
# ## 5. Part I Summary
#
# 3 groups, 15 timelines. Each group's diagram above shows all
# timelines with their sample counts and units.
#
# **Next:** Part II builds the Score group and aligns each recording via note matching.
