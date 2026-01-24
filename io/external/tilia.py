from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow as pa
import pandas as pd

from timetoalign.core.ids import IdGenerator
from timetoalign.core.enums import TimeUnit, Domain, NumberType
from timetoalign.alignment.container import Alignment
from timetoalign.timelines.timeline import Timeline
from timetoalign.io.external.stores import EventStore

# Tilia JSON structure:
# { "timelines": [ { "kind": "...", "components": [ { "start": ... } ] } ] }

class TiliaEventStore(EventStore):
    """Reads a specific TiLiA timeline entry."""
    
    def __init__(self, timeline_data: Dict[str, Any], scope: str):
        self._data = timeline_data
        self._scope = scope
        self._id_gen = IdGenerator(scope)
        
        # Pre-process into simple list of dicts with scoped IDs
        self._events = []
        for i, comp in enumerate(timeline_data.get("components", [])):
            clean = comp.copy()
            # Generate ID
            # Use 'label' or index?
            # TiLiA doesn't seem to have stable IDs in the JSON.
            # We use index-based ID: tilia_layer_N:evt_M
            clean["id"] = self._id_gen.get_or_create(None, "evt")
            
            # Normalize times
            if "time" in clean: # Marker
                clean["start"] = clean["time"]
                clean["end"] = clean["time"] # Instant
            # Interval/Hierarchy has start/end
            
            self._events.append(clean)
            
    @property
    def source_name(self) -> str:
        return self._scope
        
    def to_table(self) -> pa.Table:
        # Convert list of dicts to PyArrow table
        # We enforce strings for text columns to avoid PA inference issues with mixed types
        df = pd.DataFrame(self._events)
        if "label" not in df.columns:
            df["label"] = ""
        df["label"] = df["label"].astype(str)
        return pa.Table.from_pandas(df)
        
    def get_instants(self) -> pa.Table:
        # Filter where start == end or kind == MARKER
        # For simple mapping, we just return 'start' as coordinate
        # But wait, logic:
        # If kind==MARKER, it is an instant.
        # If kind==HIERARCHY, it is an interval.
        data = []
        for evt in self._events:
            if evt.get("kind") == "MARKER":
                data.append({"coordinate": evt["start"], "event_id": evt["id"], "category": evt.get("kind")})
        
        if not data:
             return pa.Table.from_pydict({"coordinate": [], "event_id": [], "category": []})
             
        return pa.Table.from_pydict({
            k: [d[k] for d in data] for k in data[0].keys()
        })
        
    def get_intervals(self) -> pa.Table:
        data = []
        for evt in self._events:
            if evt.get("kind") == "HIERARCHY":
                data.append({
                    "start": evt["start"], 
                    "end": evt["end"], 
                    "event_id": evt["id"], 
                    "category": evt.get("kind")
                })
                
        if not data:
             return pa.Table.from_pydict({"start": [], "end": [], "event_id": [], "category": []})

        return pa.Table.from_pydict({
            k: [d[k] for d in data] for k in data[0].keys()
        })


def load_alignment_from_tilia(json_path: str, project_id: str) -> Alignment:
    """Loads a TiLiA JSON export as an Alignment."""
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    container = Alignment(id=project_id)
    
    # Each timeline in 'timelines' becomes a Timeline in our container
    # They usually share the same physical time axis.
    
    for i, tl_data in enumerate(data.get("timelines", [])):
        name = tl_data.get("name", f"layer_{i}")
        # Sanitize name for ID
        safe_name = "".join(c if c.isalnum() else "_" for c in name)
        tl_id = f"{project_id}_{safe_name}"
        
        # Create Store
        store = TiliaEventStore(tl_data, scope=safe_name)
        
        # Create Timeline
        # TiLiA is physical (seconds)
        tl = Timeline.create_empty(tl_id, Domain.PHYSICAL, TimeUnit.SECONDS)
        
        # Populate
        tl._events = store.to_table()
        tl._instants = store.get_instants()
        tl._intervals = store.get_intervals()
        
        container.add_timeline(tl)
        
    return container
