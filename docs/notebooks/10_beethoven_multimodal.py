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
# This tutorial is the **Figure 3 acid test** for the TimeToAlign! library.
# We model the multimodal alignment of Beethoven's *String Quartet No. 4*,
# Op. 18/4, movement IV with **16+ timelines** across all 3 domains
# (Physical, Logical, Graphical) organized into **5 TimelineGroups** within
# a single `AlignmentBundle`.
#
# **Learning Objectives:**
# - Build recording groups from heterogeneous sensor data (audio, features, MoCap, notes)
# - Load and unfold score data with `FlowController` and `TraversalMap`
# - Create cross-group `MatchClaim` objects via note matching
# - Transfer coordinates across all 5 groups using `AlignmentBundle.get_timestamp_at()`
#
# **Prerequisites:** Notebooks 07, 08, 09
#
# **Data Source:** Beethoven String Quartet No. 4 Op. 18/4, movement IV
# - 3 EEP recordings (Normal, Mechanical, Exaggerated) with multimodal sensor data
# - ABC v2.6 score + OMR ground truth + OpenScore encoding
# - Emerson Quartet commercial recording with measure-level alignment
#
# **Structure:**
# 1. **Part I** (this notebook section): Build 3 recording groups (Groups 1-3)
# 2. **Part II**: Build Score group (Group 4) + align with recordings
# 3. **Part III**: Build Emerson group (Group 5) + cross-group coordinate transfer

# %% [markdown]
# ## 0. Gold Standard Reference Values
#
# Per the ZERO TOLERANCE policy, all assertions use exact counts verified
# against the actual data files.
#
# ### Recording Groups (Physical Domain)
#
# | ID | Description | Samples | Rate | Group |
# |----|-------------|---------|------|-------|
# | **DPT1** | Normal audio (mono) | 11,753,638 | 44,100 Hz | 1 |
# | **DPT2** | Normal tonal features | 11,195 | 42 Hz | 1 |
# | **DPT3** | Normal lowlevel features | 22,389 | 84 Hz | 1 |
# | **DPT4** | Normal rhythm features | 45,844 | 172 Hz | 1 |
# | **DPT5** | Normal MoCap | 63,965 | 240 Hz | 1 |
# | **DPT6** | Mechanical audio (mono) | 12,426,696 | 44,100 Hz | 2 |
# | **DPT7** | Mechanical tonal features | 11,836 | 42 Hz | 2 |
# | **DPT8** | Mechanical lowlevel features | 23,671 | 84 Hz | 2 |
# | **DPT9** | Mechanical rhythm features | 48,469 | 172 Hz | 2 |
# | **DPT10** | Mechanical MoCap | 67,628 | 240 Hz | 2 |
# | **DPT11** | Exaggerated audio (mono) | 8,197,748 | 44,100 Hz | 3 |
# | **DPT12** | Exaggerated tonal features | 7,808 | 42 Hz | 3 |
# | **DPT13** | Exaggerated lowlevel features | 15,616 | 84 Hz | 3 |
# | **DPT14** | Exaggerated rhythm features | 31,975 | 172 Hz | 3 |
# | **DPT15** | Exaggerated MoCap | 44,614 | 240 Hz | 3 |
#
# ### EEP Note Events
#
# | Recording | Total | vln1 | vln2 | vla | cello |
# |-----------|-------|------|------|-----|-------|
# | Normal | 4,026 | 1,266 | 1,015 | 928 | 817 |
# | Mechanical | 4,026 | 1,266 | 1,015 | 928 | 817 |
# | Exaggerated | 2,820 | 863 | 707 | 659 | 591 |
#
# ### Note Matching (Part II)
#
# | Recording | Matched | Unmatched EEP | Unmatched ABC |
# |-----------|---------|---------------|---------------|
# | Normal | 3,740 | 16 | 10 |
# | Mechanical | 3,741 | 15 | 9 |
# | Exaggerated | 2,650 | 4 | 1,100 |
#
# | Score Item | Value |
# |------------|-------|
# | ABC unfolded note onsets (after dropping tied) | 3,750 |

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
assert DATA_DIR.is_dir(), f"Data directory not found: {DATA_DIR}"

# Recording directories
NORMAL_DIR = DATA_DIR / "StringQuartetEEP_I_Normal"
MECHANICAL_DIR = DATA_DIR / "StringQuartetEEP_I_Mechanical"
EXAGGERATED_DIR = DATA_DIR / "StringQuartetEEP_I_Exaggerated"

# Prefix patterns for file discovery
NORMAL_PFX = "StringQuartetEEP_I_Normal"
MECHANICAL_PFX = "StringQuartetEEP_I_Mechanical"
EXAGGERATED_PFX = "StringQuartetEEP_I_Exaggerated"

{
    "Data directory": str(DATA_DIR),
    "Recordings": [d.name for d in [NORMAL_DIR, MECHANICAL_DIR, EXAGGERATED_DIR]],
}

# %% [markdown]
# ---
#
# # Part I: Three Recording Groups (Groups 1-3)
#
# Each EEP recording contains 5 discrete physical timelines sharing the same
# physical time span but at different sampling rates:
#
# | Timeline | Source | Unit |
# |----------|--------|------|
# | Audio (mono MP3) | 6-channel recording, mono mix | samples @ 44,100 Hz |
# | Tonal features | Essentia extraction | samples @ 42 Hz |
# | Lowlevel features | Essentia extraction | samples @ 84 Hz |
# | Rhythm features | Essentia extraction | samples @ 172 Hz |
# | Motion capture | RepoVizz sensor data | samples @ 240 Hz |
#
# All timelines within a group are **commensurable** because they represent
# the same physical duration at different sampling rates.

# %% [markdown]
# ## 2. Group 1: Normal Recording (DPT1-DPT5)
#
# ### 2.1 Audio Timeline (DPT1)

# %%
audio_normal = AudioLoader.from_file(NORMAL_DIR / f"{NORMAL_PFX}_mono.mp3")
dpt1 = audio_normal.to_timeline(uid="dpt1")

assert audio_normal.n_samples == 11753638
assert audio_normal.sample_rate == 44100

{
    "DPT1 (Audio)": f"{audio_normal.n_samples:,} samples @ {audio_normal.sample_rate:,} Hz",
    "Duration": f"{audio_normal.duration_seconds:.2f}s",
}

# %% [markdown]
# ### 2.2 Feature Timelines (DPT2-DPT4)
#
# Feature WAV files use IEEE float format (handled automatically by `AudioLoader`).
# We pick one representative file per feature category — all files within a
# category share the same sampling rate and sample count.

# %%
# DPT2: Tonal features (sr=42)
tonal_normal = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PFX}_mono.wav.tonal.ChordsStrength.wav"
)
dpt2 = tonal_normal.to_timeline(uid="dpt2")

# DPT3: Lowlevel features (sr=84)
lowlevel_normal = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PFX}_mono.wav.lowlevel.Dissonance.wav"
)
dpt3 = lowlevel_normal.to_timeline(uid="dpt3")

# DPT4: Rhythm features (sr=172)
rhythm_normal = AudioLoader.from_file(
    NORMAL_DIR / f"{NORMAL_PFX}_mono.wav.rhythm.BeatsLoudness.wav"
)
dpt4 = rhythm_normal.to_timeline(uid="dpt4")

assert tonal_normal.n_samples == 11195 and tonal_normal.sample_rate == 42
assert lowlevel_normal.n_samples == 22389 and lowlevel_normal.sample_rate == 84
assert rhythm_normal.n_samples == 45844 and rhythm_normal.sample_rate == 172

{
    "DPT2 (Tonal)": f"{tonal_normal.n_samples:,} @ sr={tonal_normal.sample_rate}",
    "DPT3 (Lowlevel)": f"{lowlevel_normal.n_samples:,} @ sr={lowlevel_normal.sample_rate}",
    "DPT4 (Rhythm)": f"{rhythm_normal.n_samples:,} @ sr={rhythm_normal.sample_rate}",
}

# %% [markdown]
# ### 2.3 Motion Capture Timeline (DPT5)
#
# MoCap data is stored in RepoVizz 2-line CSV format (metadata header + data row).

# %%
mocap_normal = RepoVizzLoader.from_file(NORMAL_DIR / "vln1_bb_angle.csv")
dpt5 = mocap_normal.to_timeline(uid="dpt5")

assert mocap_normal.n_samples == 63965
assert mocap_normal.frame_rate == 240

{
    "DPT5 (MoCap)": f"{mocap_normal.n_samples:,} samples @ {mocap_normal.frame_rate} Hz",
    "Duration": f"{mocap_normal.duration_seconds:.2f}s",
}

# %% [markdown]
# ### 2.4 Note Events
#
# EEP `.notes` files contain onset/offset/pitch for each instrument.
# We load all 4 parts into a single loader — staff is inferred from the filename.

# %%
notes_normal = EepNotesLoader()
notes_normal.load(*sorted(NORMAL_DIR.glob("*_align_*.notes")))

assert len(notes_normal) == 4026

# Per-staff verification
normal_staff = notes_normal.events.to_pandas()["staff"].value_counts().sort_index()
assert normal_staff[1] == 1266  # vln1
assert normal_staff[2] == 1015  # vln2
assert normal_staff[3] == 928  # vla
assert normal_staff[4] == 817  # cello

{"Normal notes": len(notes_normal), "Per staff": dict(normal_staff)}

# %% [markdown]
# ### 2.5 Assemble Group 1
#
# All 5 timelines share the same physical duration (~266.5 seconds) at different
# sampling rates. The `TimelineGroup` establishes commensurability between them.

# %%
normal_group = TimelineGroup(
    id="normal",
    name="Normal Recording (EEP)",
    timelines=[dpt1, dpt2, dpt3, dpt4, dpt5],
)

assert normal_group.n_timelines == 5

normal_group

# %%
normal_group.get_timestamps_df()

# %% [markdown]
# ---
#
# ## 3. Group 2: Mechanical Recording (DPT6-DPT10)
#
# Same structure as the Normal recording — different performance interpretation.

# %%
# DPT6: Audio
audio_mech = AudioLoader.from_file(MECHANICAL_DIR / f"{MECHANICAL_PFX}_mono.mp3")
dpt6 = audio_mech.to_timeline(uid="dpt6")

# DPT7: Tonal features
tonal_mech = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PFX}_mono.wav.tonal.ChordsStrength.wav"
)
dpt7 = tonal_mech.to_timeline(uid="dpt7")

# DPT8: Lowlevel features
lowlevel_mech = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PFX}_mono.wav.lowlevel.Dissonance.wav"
)
dpt8 = lowlevel_mech.to_timeline(uid="dpt8")

# DPT9: Rhythm features
rhythm_mech = AudioLoader.from_file(
    MECHANICAL_DIR / f"{MECHANICAL_PFX}_mono.wav.rhythm.BeatsLoudness.wav"
)
dpt9 = rhythm_mech.to_timeline(uid="dpt9")

# DPT10: MoCap
mocap_mech = RepoVizzLoader.from_file(MECHANICAL_DIR / "vln1_bb_angle.csv")
dpt10 = mocap_mech.to_timeline(uid="dpt10")

# Assertions
assert audio_mech.n_samples == 12426696
assert tonal_mech.n_samples == 11836 and tonal_mech.sample_rate == 42
assert lowlevel_mech.n_samples == 23671 and lowlevel_mech.sample_rate == 84
assert rhythm_mech.n_samples == 48469 and rhythm_mech.sample_rate == 172
assert mocap_mech.n_samples == 67628 and mocap_mech.frame_rate == 240

{
    "DPT6 (Audio)": f"{audio_mech.n_samples:,} @ {audio_mech.sample_rate:,} Hz",
    "DPT7 (Tonal)": f"{tonal_mech.n_samples:,} @ sr={tonal_mech.sample_rate}",
    "DPT8 (Lowlevel)": f"{lowlevel_mech.n_samples:,} @ sr={lowlevel_mech.sample_rate}",
    "DPT9 (Rhythm)": f"{rhythm_mech.n_samples:,} @ sr={rhythm_mech.sample_rate}",
    "DPT10 (MoCap)": f"{mocap_mech.n_samples:,} @ {mocap_mech.frame_rate} Hz",
}

# %%
# Mechanical note events
notes_mech = EepNotesLoader()
notes_mech.load(*sorted(MECHANICAL_DIR.glob("*_align_*.notes")))
assert len(notes_mech) == 4026

{"Mechanical notes": len(notes_mech)}

# %%
mechanical_group = TimelineGroup(
    id="mechanical",
    name="Mechanical Recording (EEP)",
    timelines=[dpt6, dpt7, dpt8, dpt9, dpt10],
)

assert mechanical_group.n_timelines == 5
mechanical_group

# %% [markdown]
# ---
#
# ## 4. Group 3: Exaggerated Recording (DPT11-DPT15)
#
# The Exaggerated recording is shorter (~186s vs ~267s) because it stops after
# measure 131 (the note lists end after measure 130).

# %%
# DPT11: Audio
audio_exag = AudioLoader.from_file(EXAGGERATED_DIR / f"{EXAGGERATED_PFX}_mono.mp3")
dpt11 = audio_exag.to_timeline(uid="dpt11")

# DPT12: Tonal features
tonal_exag = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PFX}_mono.wav.tonal.ChordsStrength.wav"
)
dpt12 = tonal_exag.to_timeline(uid="dpt12")

# DPT13: Lowlevel features
lowlevel_exag = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PFX}_mono.wav.lowlevel.Dissonance.wav"
)
dpt13 = lowlevel_exag.to_timeline(uid="dpt13")

# DPT14: Rhythm features
rhythm_exag = AudioLoader.from_file(
    EXAGGERATED_DIR / f"{EXAGGERATED_PFX}_mono.wav.rhythm.BeatsLoudness.wav"
)
dpt14 = rhythm_exag.to_timeline(uid="dpt14")

# DPT15: MoCap
mocap_exag = RepoVizzLoader.from_file(EXAGGERATED_DIR / "vln1_bb_angle.csv")
dpt15 = mocap_exag.to_timeline(uid="dpt15")

# Assertions
assert audio_exag.n_samples == 8197748
assert tonal_exag.n_samples == 7808 and tonal_exag.sample_rate == 42
assert lowlevel_exag.n_samples == 15616 and lowlevel_exag.sample_rate == 84
assert rhythm_exag.n_samples == 31975 and rhythm_exag.sample_rate == 172
assert mocap_exag.n_samples == 44614 and mocap_exag.frame_rate == 240

{
    "DPT11 (Audio)": f"{audio_exag.n_samples:,} @ {audio_exag.sample_rate:,} Hz",
    "DPT12 (Tonal)": f"{tonal_exag.n_samples:,} @ sr={tonal_exag.sample_rate}",
    "DPT13 (Lowlevel)": f"{lowlevel_exag.n_samples:,} @ sr={lowlevel_exag.sample_rate}",
    "DPT14 (Rhythm)": f"{rhythm_exag.n_samples:,} @ sr={rhythm_exag.sample_rate}",
    "DPT15 (MoCap)": f"{mocap_exag.n_samples:,} @ {mocap_exag.frame_rate} Hz",
}

# %%
# Exaggerated note events
notes_exag = EepNotesLoader()
notes_exag.load(*sorted(EXAGGERATED_DIR.glob("*_align_*.notes")))
assert len(notes_exag) == 2820

exag_staff = notes_exag.events.to_pandas()["staff"].value_counts().sort_index()
assert exag_staff[1] == 863  # vln1
assert exag_staff[2] == 707  # vln2
assert exag_staff[3] == 659  # vla
assert exag_staff[4] == 591  # cello

{"Exaggerated notes": len(notes_exag), "Per staff": dict(exag_staff)}

# %%
exaggerated_group = TimelineGroup(
    id="exaggerated",
    name="Exaggerated Recording (EEP)",
    timelines=[dpt11, dpt12, dpt13, dpt14, dpt15],
)

assert exaggerated_group.n_timelines == 5
exaggerated_group

# %% [markdown]
# ---
#
# ## 5. Part I Summary: Three Recording Groups
#
# We have built 3 recording groups, each containing 5 commensurable discrete
# physical timelines. All gold standard sample counts are verified.

# %%
{
    "Groups built": 3,
    "Total timelines": normal_group.n_timelines
    + mechanical_group.n_timelines
    + exaggerated_group.n_timelines,
    "Normal": {
        "timelines": normal_group.n_timelines,
        "notes": len(notes_normal),
        "duration": f"{audio_normal.duration_seconds:.1f}s",
    },
    "Mechanical": {
        "timelines": mechanical_group.n_timelines,
        "notes": len(notes_mech),
        "duration": f"{audio_mech.duration_seconds:.1f}s",
    },
    "Exaggerated": {
        "timelines": exaggerated_group.n_timelines,
        "notes": len(notes_exag),
        "duration": f"{audio_exag.duration_seconds:.1f}s",
    },
}

# %% [markdown]
# ---
#
# **Next:** Part II builds the Score group (CLT1 + DGT1 + OpenScore) and
# aligns each recording group to the score via note matching.
