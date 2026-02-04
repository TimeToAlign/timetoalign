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
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%

from pathlib import Path

from timetoalign import AudioLoader, ContinuousLogicalTimeline, DiscreteLogicalTimeline

DATA_DIR = Path("../../tests/data").resolve()
assert DATA_DIR.is_dir(), f"Data dir not found: {DATA_DIR}"
mp3_path = DATA_DIR / "supra" / "midi" / "fd660zf8362.mp3"
mp3 = AudioLoader().load(mp3_path)
mp3

# %%
tl = mp3.to_timeline()
tl

# %%

# %% [markdown]
# Including conversion maps fucking sucks rn:
# * conversion_maps=True should include all available conversion maps
# * conversion_maps="seconds" should call get_conversion_map("seconds")
# * conversion_maps=SamplesToSeconds should not try to iterate
# * include_boundaries should default to True
# * get_timestamps should with an option to get coordinates instead of floats

# %%
tl.get_timestamps(
    conversion_maps=[tl.get_conversion_map("seconds")], include_boundaries=True
)

# %%
tl.add_conversion_map()

# %%
tsv_df

# %%
pt_df

# %%
m21_df

# %%
T = ContinuousLogicalTimeline()
U = DiscreteLogicalTimeline()
T

# %%

for store in tsv_bundle:
    T.add_child(ContinuousLogicalTimeline.from_event_store(store), 0)
T

# %%
T.events.table.to_pandas()
