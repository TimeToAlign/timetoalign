from __future__ import annotations

import json
from typing import Any, Dict

from timetoalign.alignment.container import Alignment
from timetoalign.alignment.match import Match
from timetoalign.timelines.timeline import Timeline
from timetoalign.core.enums import TimeUnit, Domain, NumberType
from timetoalign.coordinates.coordinate import Coordinate

# TODO: Add full serialization/deserialization logic.
# For now, implementing basic structure export for visualization/debug.

def alignment_to_json_dict(alignment: Alignment) -> Dict[str, Any]:
    """Converts an Alignment to a JSON-compatible dictionary."""
    data = {
        "id": alignment.id,
        "timelines": [],
        "matches": []
    }
    
    for tl in alignment.timelines:
        tl_data = {
            "id": tl.id,
            "domain": str(tl.domain),
            "unit": str(tl.unit),
            "length": tl.length.to_float(),
            # For JSON, we might want to export a summary or full events?
            # User story says "Slim export for plotting"
            # We'll export basic metadata for now.
             "event_count": tl.get_event_count()
        }
        data["timelines"].append(tl_data)
        
    for m in alignment._matches.values():
        m_data = {
            "id": m.id,
            "certainty": m.certainty,
            "event_ids": list(m.event_ids)
        }
        if m.comment:
            m_data["comment"] = m.comment
        data["matches"].append(m_data)
        
    return data

def save_alignment_json(alignment: Alignment, path: str):
    data = alignment_to_json_dict(alignment)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_alignment_json(path: str) -> Alignment:
    with open(path, 'r') as f:
        data = json.load(f)
        
    align = Alignment(id=data["id"])
    
    # Reconstruct empty timelines (events loading skipped in simplified JSON loader)
    for tl_data in data["timelines"]:
        tl = Timeline.create_empty(
            id=tl_data["id"],
            domain=Domain(tl_data["domain"]),
            unit=TimeUnit(tl_data["unit"]),
            length=tl_data["length"]
        )
        align.add_timeline(tl)
        
    # Reconstruct matches
    for m_data in data["matches"]:
        m = Match(id=m_data["id"], certainty=m_data.get("certainty", 1.0))
        for eid in m_data["event_ids"]:
            m.add_event(eid)
        m.comment = m_data.get("comment")
        align.add_match(m)
        
    return align
