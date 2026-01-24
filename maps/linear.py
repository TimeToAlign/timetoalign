from __future__ import annotations

from typing import Optional
from dataclasses import dataclass

from timetoalign.core.enums import TimeUnit
from timetoalign.coordinates.coordinate import Coordinate
from timetoalign.maps.base import ConversionMap

@dataclass
class LinearMap(ConversionMap):
    """f(x) = slope * x + intercept"""
    
    source_unit: TimeUnit
    target_unit: TimeUnit
    slope: float
    intercept: float
    
    def convert(self, coordinate: Coordinate) -> Coordinate:
        if coordinate.unit != self.source_unit:
            raise ValueError(f"Unit mismatch: expected {self.source_unit}, got {coordinate.unit}")
            
        val = coordinate.to_float() * self.slope + self.intercept
        return Coordinate(val, self.target_unit)
        
    def inverse(self) -> Optional[ConversionMap]:
        if self.slope == 0:
            return None
            
        return LinearMap(
            source_unit=self.target_unit,
            target_unit=self.source_unit,
            slope=1.0 / self.slope,
            intercept=-self.intercept / self.slope
        )

@dataclass
class ShiftMap(LinearMap):
    """f(x) = x + shift (Slope is always 1.0)"""
    
    def __init__(self, source_unit: TimeUnit, target_unit: TimeUnit, shift: float):
        super().__init__(source_unit, target_unit, 1.0, shift)

    def inverse(self) -> Optional[ConversionMap]:
        return ShiftMap(self.target_unit, self.source_unit, -self.intercept)
