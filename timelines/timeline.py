from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import pyarrow as pa
import pandas as pd # Used for interaction and display, easier than raw PA

from timetoalign.core.enums import TimeUnit, NumberType, Domain
from timetoalign.coordinates.coordinate import Coordinate
from timetoalign.maps.base import ConversionMap

module_logger = logging.getLogger(__name__)

@dataclass
class Timeline:
    """A timeline is a coordinate axis with events and nested segments.
    
    Attributes:
        id: Unique identifier for this timeline (scoped).
        length: The total length of the timeline (Coordinate).
        domain: The temporal domain (Physical, Logical, Graphical).
    """
    
    id: str
    length: Coordinate
    domain: Domain
    
    # Configuration
    unit: TimeUnit
    number_type: NumberType
    
    # Storage (PyArrow Tables)
    # _instants schema: [coordinate (float), event_id (str), category (str)]
    _instants: pa.Table = field(default_factory=lambda: pa.Table.from_pydict({
        "coordinate": [], "event_id": [], "category": []
    }))
    
    # _intervals schema: [start (float), end (float), event_id (str), category (str)]
    _intervals: pa.Table = field(default_factory=lambda: pa.Table.from_pydict({
        "start": [], "end": [], "event_id": [], "category": []
    }))
    
    # _events schema: [id (str), ... full event columns ...]
    _events: pa.Table = field(default_factory=lambda: pa.Table.from_pydict({"id": []}))
    
    # Connected objects
    _cmaps: List[ConversionMap] = field(default_factory=list)
    _segments: List["Timeline"] = field(default_factory=list) # Nested timelines
    
    def __post_init__(self):
        # Validate that length unit matches timeline unit
        if self.length.unit != self.unit:
            raise ValueError(f"Timeline unit {self.unit} does not match length unit {self.length.unit}")

    def add_conversion_map(self, cmap: ConversionMap):
        """Attaches a conversion map to this timeline."""
        # Validate map source matches timeline
        # Note: A map might convert FROM this timeline (source=self.unit)
        # OR TO this timeline (target=self.unit, inverse).
        # We store all maps that touch this unit.
        if cmap.source_unit != self.unit and cmap.target_unit != self.unit:
             # Just a warning or permissive?
             # Strictly, a cmap attached to a timeline should relate to its unit.
             module_logger.warning(f"Attaching map {cmap} to timeline {self.id} with unit {self.unit} but map unconnected.")
             
        self._cmaps.append(cmap)

    def add_segment(self, segment: "Timeline", start_coordinate: Coordinate):
        """Adds a child timeline (Segment) at a specific coordinate."""
        if segment.unit != self.unit:
             raise ValueError("Segment unit must match parent unit.")
             
        # In a full implementation, we would add this to the _intervals table 
        # as a special event type, or keep it in _segments and index it.
        # For Phase 3 basic verification, list storage is fine.
        self._segments.append(segment)
        
    def get_event_count(self) -> int:
        return len(self._events)
        
    def events_to_pandas(self) -> pd.DataFrame:
        """Returns the full event table as a Pandas DataFrame."""
        return self._events.to_pandas()

    @classmethod
    def create_empty(cls, id: str, domain: Domain, unit: TimeUnit, length: float = 0.0) -> Timeline:
        return cls(
            id=id,
            domain=domain,
            unit=unit,
            length=Coordinate(length, unit),
            number_type=NumberType.FLOAT # Default
        )
