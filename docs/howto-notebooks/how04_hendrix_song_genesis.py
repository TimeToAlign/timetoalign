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

from pathlib import Path

# %%
from timetoalign import AlignmentBundle
from timetoalign.loader.alignment import TiliaJsonLoader

base_path = Path("hendrix-tilia-files")
names = ["Studio", "Demo1", "Demo2"]

loaders = {}
filenames = [
    "Hendrix_Merman_Studio.json",
    "Hendrix_Merman_Demo1.json",
    "Hendrix_Merman_Demo2.json",
]
paths = [base_path / f"Hendrix_Merman_{name}.json" for name in names]

for name in names:
    loader = TiliaJsonLoader()
    loader.load(base_path / f"Hendrix_Merman_{name}.json")
    loader.create_group()
    loaders[name] = loader

loaders

# %%
timelines = {
    name: loader.create_alignment_bundle().get_timeline("HIERARCHY_TIMELINE_0")
    for name, loader in loaders.items()
}
timelines

# %%
from pathlib import Path

import pandas as pd

path = Path("hendrix-tilia-files") / "match_data.csv"
df = pd.read_csv(path, sep="\t")

df

# %%
tl_names = [c for c in df.columns if c != "match"]

df["match"] = df["match"].astype(str).str.strip()
df = df[df["match"].ne("")]

match_data = df.set_index("match")[tl_names].to_dict(orient="dict")
match_data


# %%
bundle = AlignmentBundle()
for name, timeline in timelines.items():
    bundle.add_timeline(timeline, uid=name)

# 1) Map the names used in match_data.csv columns -> your Timeline objects
timelines_by_name = {
    "Studio": bundle.get_timeline("Studio"),
    "Demo1": bundle.get_timeline("Demo1"),
    "Demo2": bundle.get_timeline("Demo2"),
}


def _get_single_event_by_name(tl, event_name: str):
    """Return exactly one event dict for tl.get_events(name=event_name)."""
    evs = tl.get_events(name=event_name)
    n = len(evs)
    if n == 0:
        return None
        raise ValueError(
            f"No event found on timeline '{tl.id}' with name={event_name!r}"
        )
    if n > 1:
        return None
        raise ValueError(
            f"Expected exactly 1 event on timeline '{tl.id}' with name={event_name!r}, got {n}"
        )
    event_id = str(evs.table[0][0])  # first column is 'id' in your EventData schema
    event = tl.get_event(event_id)
    if event is None:
        raise RuntimeError(
            f"Event with id={event_id!r} not found on timeline '{tl.id}'"
        )
    return event


# 2) Build all event pairs (claims are pairwise; for 3+ timelines we create a "star"
#    by pairing the first available timeline with each of the others)
event_pairs = []
all_match_ids = sorted(
    {
        match_id
        for tl_name, by_match in match_data.items()
        for match_id in by_match.keys()
    }
)

for match_id in all_match_ids:
    present = []
    for tl_name, tl in timelines_by_name.items():
        val = match_data.get(tl_name, {}).get(match_id, None)

        if val is None:
            continue
        if isinstance(val, str) and val.strip().upper() == "NOMATCH":
            continue

        event_name = val
        present.append((tl, event_name))

    # Need at least 2 timelines to make a match claim
    if len(present) < 2:
        continue

    tl0, name0 = present[0]
    ev0 = _get_single_event_by_name(tl0, name0)
    if not ev0:
        continue

    for tl1, name1 in present[1:]:
        ev1 = _get_single_event_by_name(tl1, name1)
        if not ev1:
            continue
        event_pairs.append((ev0, tl0.id, ev1, tl1.id))

# 3) Create the claims (may be 0 if everything was NOMATCH/None)
claims = bundle.create_match_claims(
    event_pairs,
    synchronous=True,  # keep anchors; set False only if you explicitly want non-synchronous claims
    agent="user",
    decision_criteria="match_data.csv",
)

for claim in claims:
    display(claim)
