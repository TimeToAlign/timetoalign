from __future__ import annotations

from typing import Optional, Tuple
from dataclasses import dataclass
import math

from timetoalign.core.enums import TimeUnit
from timetoalign.coordinates.coordinate import Coordinate
from timetoalign.maps.base import ConversionMap

@dataclass
class StraightLineMap(ConversionMap):
    """Maps a 1D scalar (distance along line) to a 2D spatial coordinate (x, y)."""
    
    source_unit: TimeUnit
    target_unit: TimeUnit
    
    start_x: float
    start_y: float
    angle_rad: float
    
    @classmethod
    def from_endpoints(cls, start: Tuple[float, float], end: Tuple[float, float], 
                       source_unit: TimeUnit, target_unit: TimeUnit) -> StraightLineMap:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        angle = math.atan2(dy, dx)
        return cls(source_unit, target_unit, start[0], start[1], angle)
        
    def convert(self, coordinate: Coordinate) -> Coordinate:
        # Input: distance along the line
        dist = float(coordinate.value)  # Force float for math
        
        x = self.start_x + dist * math.cos(self.angle_rad)
        y = self.start_y + dist * math.sin(self.angle_rad)
        
        return Coordinate((x, y), self.target_unit)
        
    def inverse(self) -> Optional[ConversionMap]:
        # Inverse logic would be complex (projecting 2D point back to line).
        # Leaving as None for now for Phase 2.
        return None
