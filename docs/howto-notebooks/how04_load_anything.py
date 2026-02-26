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

# %%
from timetoalign import Coordinate
from timetoalign.loader.score import TSVLoader

FOLDER = Path("...")
file = FOLDER / "file.ext"
more_files = file.glob("**/*.ext")
dict_or_callable = {"original_id": "new_id"}

# %%
loader = TSVLoader.from_file(file, uid="loadername", id_map=dict_or_callable)
loader  # prints metadata such as loaded filenames as well as the number of timelines and as how many groups with how many timelines containing how many children they will be returned by default; plus the output of loader.store.summary()

# %%
loader.load(
    more_files, id_map="auto"
)  # loads additional files while using the IdGenerator, scoped by the loader's ID; yields no return value; every loader needs to define behaviour for loading multiple files
loader.store  # prints output of loader.store.summary(), displaying the IDs of the tables in the event store and, for each, the coordinate range (including the unit), or ranges (if multiple units available for choice), and number of events; if the store has properties for specific table types, then the IDs are printed grouped according to them

# %%
type_table = (
    loader.store.type_property
)  # if store has properties for specific table types, demonstrate the output for one of them:
type_table  # the relevant pa.Table which, if several tables are available for a type, will be a concatenation of them

# %%
type_table.schema  # display the table schema

# %%
loader.create_timeline(
    "part_of_id"
)  # a partial string or regex that matches multiple IDs will return the timeline for the first one and throw a warning about the remaining matches

# %%
loader[
    "id"
].to_dataframe().head()  # gets the pa.Table "id" from the store and displays it; shorthand for loader.get_table("id") which delegates to loader.store.get_table("id"); NO LOADER HAS loader._tables because ALL TABLES LIVE IN A STORE

# %%
tls = loader.create_timelines()
{tl.id: (tl.n_children, tl.n_events) for tl in tls}

# %%
loader.create_timelines(
    "part_of_id"
)  # a partial string or regex that subselects multiple IDs

# %%
tl1 = loader.create_timeline(
    "first_id"
)  # it depends on the loader what type of IDs can be picked here;
assert tl1 is tls["first_id"]  # True because timelines are cached
tl1  # display a timeline, its conversion maps, and the count for each included event type (including all events from all children)

# %%
combined_tl = (
    loader.create_timeline()
)  # for loaders that can return a single timeline, including one that contains all others as children

# %%
nested_tl = loader.create_timeline("some_id", children=["other_ids"])

# %%
tl1.get_events().schema

# %%
tl2 = loader.create_timeline(
    "part_of_id"
)  # a partial string or regex that matches multiple IDs will return the timeline for the first one and throw a warning about the remaining matches
tl2.get_events(
    temporal_type="interval", min_coord=13, max_coord=20
)  # pick coordinates so that a few are selected

# %%
tl2.get_events(
    event_type="Note",
    min_coord=Coordinate(20, "convertible_unit"),
    max_coord=Coordinate(40, "convertible_unit"),
)  # pick a relevant event type and a coordinate to which a cmap exists so that the inverse conversion to the timeline's unit is demonstrated and tested

# %%
tl2.get_events(
    kwarg_filter="value", kwarg_name=["either_this", "or_this"]
)  # demonstrate custom filtering based on the event properties (columns of the schema shown above)

# %%
evt = tl2.get_event("event_id")
evt

# %%
evt_ts = evt.timestamp()
evt_ts is tl2.get_timestamp_of(evt.id)  # True
evt_ts  # event timestamps always display their axis coordinate plus c-map conversion; timestamps are always shown as a table with name, id, cmap/axis, unit, coordinate; for IntervalEvents, the end timestamp is shown underneath

# %%
tl2.get_timestamp_at(13)  # some meaningful coordinate (but not the first or last one)

# %%
tl2.get_timestamp(
    25, children=False
)  # exclude children and their cmaps (skip if no children present)

# %%
events = tl2.get_events_at(59)
events.to_dataframe()

# %%
tl2.get_timestamps(
    events.column("start")
)  # same API as .get_timestamp_table() which it calls under the hood and converts to dataframe

# %%
tl2.get_timestamps_of(
    events
)  # has one column more to differentiate between start/end/instant

# %%
tl2.get_timestamp_table(event_type="some_type")

# %% [markdown]
# ### Groups (if applicable)

# %%
full_group = loader.create_group()
assert len(full_group) == len(tls)  # True

# %%
phys_group = loader.create_group(
    domain="physical"
)  # demonstrate with whatever domain is relevant for the given loader

# %%
full_group = loader.create_group()
assert len(full_group) == len(tls)  # True

# %%
loader.create_group(
    domain="physical"
)  # demonstrate with whatever domain is relevant for the given loader

# %%
full_group.get_timeline("part_of_id")

# %%
full_group[
    "tl_id"
]  # show timeline, shorthand for full_group.get_timeline() but with full ID (not partial)

# %%
full_group.get_timestamp_at(24, "tl_id")

# %%
full_group.get_timestamp_of(
    evt.id
)  # selects the appropriate timeline but yields timestamp (or timeintervalstamp) for the entire group

# %%
full_group.get_timestamps(
    temporal_type="instant", domain="logical"
)  # same API as .get_timestamp_table() which it calls under the hood and converts to dataframe

# %%
full_group.get_timestamps_of(full_group.get_events(event_type="Note").column("id"))

# %%
full_group.get_timestamp_table()  # without filter, all timestamps are being retrieved

# %% [markdown]
# ### AlignmentBundle

# %%
bundle = loader.create_bundle()
bundle  # combines the information about all included groups and timelines, as well as matchClaims

# %%
bundle.get_match_claims()  # retrieve all (skip if empty list)

# %%
bundle.get_matchstamp_table()  # analogous to get_timestamp_table()

# %%
tl1, tl2 = bundle.get_timelines(["id1", "id2"])
evts1, evts2 = tl1.get_events(), tl2.get_events()
new_match = bundle.create_match_claims(
    evts1.slice(0, 1), evts2.slice(0, 1), synchronous=True
)
new_match.get_graph()  # created and cached by the AlignmentBundle

# %%
new_match.get_matchstamp()  # uses .get_graph() under the hood

# %%
new_match_claims = bundle.create_match_claims(
    evts1, evts2, synchronous=True
)  # skips the existing one
bundle.get_matchstamps(new_match_claims)
