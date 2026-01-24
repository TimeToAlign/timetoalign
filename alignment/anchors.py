from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from timetoalign.coordinates.coordinate import Coordinate
from timetoalign.timelines.timeline import Timeline

@dataclass
class TimeStamp:
    """A cross-section through a timeline hierarchy.
    
    Equivalent to the definition in the manuscript:
    'A set of values reflecting the coordinate of a root timeline,
    the synchronous coordinates of all Children, and the conversion results...'
    """
    
    root_coordinate: Coordinate
    root_timeline_id: str
    
    # Synchronous coordinates in other timelines (e.g. segments)
    # Key: TimelineID (scoped), Value: Coordinate
    child_coordinates: Dict[str, Coordinate] = field(default_factory=dict)
    
    # Conversion results at this timestamp
    # Key: ConversionMap Key (str), Value: Result (Coordinate or other)
    conversion_results: Dict[str, Coordinate] = field(default_factory=dict)
    
    def add_child_coordinate(self, timeline_id: str, coord: Coordinate):
        self.child_coordinates[timeline_id] = coord

@dataclass
class AlignmentAnchor:
    """A set of matched TimeStamps across different timelines.
    
    Represents a synchronization point.
    """
    
    # Key: TimelineID, Value: TimeStamp
    timestamps: Dict[str, TimeStamp] = field(default_factory=dict)
    
    def add_timestamp(self, timeline_id: str, timestamp: TimeStamp):
        self.timestamps[timeline_id] = timestamp
