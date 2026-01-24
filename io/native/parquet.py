from __future__ import annotations

import os
import logging
from pathlib import Path
import json

import pyarrow as pa
import pyarrow.parquet as pq

from timetoalign.alignment.container import Alignment
from timetoalign.timelines.timeline import Timeline
from timetoalign.core.enums import Domain, TimeUnit, NumberType
from timetoalign.coordinates.coordinate import Coordinate

module_logger = logging.getLogger(__name__)

# Basic schema implementation for Phase 5 verification
# Full archival implementation would handle Map config and full event columns normalization.

def save_alignment_parquet(alignment: Alignment, directory: str):
    """Saves an Alignment to a directory/dataset structure."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    
    # 1. Metadata
    meta = {
        "id": alignment.id,
        "timelines": {}
    }
    
    events_dir = base / "events"
    events_dir.mkdir(exist_ok=True)
    
    # Write Timelines
    for tl in alignment.timelines:
        meta["timelines"][tl.id] = {
            "domain": str(tl.domain),
            "unit": str(tl.unit),
            "length": tl.length.to_float(),
            "number_type": str(tl.number_type)
        }
        
        # Write events table if not empty
        if len(tl._events) > 0:
            # We add a 'timeline_id' column for partitioning or safety?
            # Or just save as {timeline_id}.parquet?
            # Convention: events/{timeline_id}.parquet
            pq.write_table(tl._events, events_dir / f"{tl.id}.parquet")
            
    # Save Metadata JSON
    with open(base / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
        
    # TODO: Matches and Maps tables

def load_alignment_parquet(directory: str) -> Alignment:
    base = Path(directory)
    with open(base / "metadata.json", "r") as f:
        meta = json.load(f)
        
    align = Alignment(id=meta["id"])
    
    events_dir = base / "events"
    
    for tl_id, tl_meta in meta["timelines"].items():
        tl = Timeline.create_empty(
            id=tl_id,
            domain=Domain(tl_meta["domain"]),
            unit=TimeUnit(tl_meta["unit"]),
            length=tl_meta["length"]
        )
        
        # Load events if exist
        event_path = events_dir / f"{tl_id}.parquet"
        if event_path.exists():
            table = pq.read_table(event_path)
            tl._events = table
            # NOTE: We need to reconstruct _instants/_intervals from _events 
            # if we didn't save them separately. 
            # For this basic impl, we assume _events IS the source of truth.
            
        align.add_timeline(tl)
        
    return align
