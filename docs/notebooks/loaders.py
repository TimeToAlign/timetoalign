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
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
# Supplementary notebook: Loader comparison and exploration
# Note: This notebook is a work-in-progress for testing loader patterns

import importlib.util
from pathlib import Path

from timetoalign import AudioLoader, ContinuousLogicalTimeline, DiscreteLogicalTimeline

# Data directory - relative to notebook location
_notebook_dir = Path(__file__).resolve().parent
DATA_DIR = _notebook_dir.parent.parent / "tests" / "data"
assert DATA_DIR.is_dir(), f"Data dir not found: {DATA_DIR}"

# Check for optional audio dependencies
_HAS_MUTAGEN = importlib.util.find_spec("mutagen") is not None
_HAS_SOUNDFILE = importlib.util.find_spec("soundfile") is not None

if _HAS_MUTAGEN or _HAS_SOUNDFILE:
    mp3_path = DATA_DIR / "supra" / "midi" / "fd660zf8362.mp3"
    mp3 = AudioLoader().load(mp3_path)
    print(mp3)
else:
    print("Note: Audio loading requires mutagen or soundfile.")
    print("Install with: pip install mutagen  # for MP3/M4A")
    print("          or: pip install soundfile  # for WAV/FLAC/etc")
    mp3 = None

# %%
if mp3 is not None:
    tl = mp3.to_timeline()
    print(tl)

    # Get timestamps with conversion
    tl.get_timestamps(
        conversion_maps=[tl.get_conversion_map("seconds")], include_boundaries=True
    )
else:
    print("Skipping audio timeline creation (no audio dependencies)")

# %% [markdown]
# ### Notes for Future Development
#
# API improvements to consider:
# * `conversion_maps=True` should include all available conversion maps
# * `conversion_maps="seconds"` should call `get_conversion_map("seconds")`
# * `include_boundaries` should default to True
# * `get_timestamps` should have an option to get coordinates instead of floats

# %%
# Note: The sections below are incomplete and require additional setup
# They are kept here for reference/development purposes

# %%
# Basic timeline creation
T = ContinuousLogicalTimeline()
U = DiscreteLogicalTimeline()
T

# %%
# Further loader exploration is documented in:
# - 02_loading_data.ipynb (Score loaders)
# - 02a_tabular_loaders.ipynb (Custom tabular loaders)
