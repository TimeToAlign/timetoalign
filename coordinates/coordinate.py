from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union

from timetoalign.core.enums import TimeUnit
from timetoalign.core.types import Scalar

@dataclass(frozen=True, order=True)
class Coordinate:
    """A point in time, consisting of a scalar value and a unit.
    
    This is a value object. It does not contain logic.
    Optimization (e.g. Flyweight) has been explicitly removed in favor of 
    simple, immutable data structures tailored for columnar storage later.
    """
    
    value: Scalar
    unit: TimeUnit
    
    def __str__(self) -> str:
        return f"{self.value} {self.unit}"
    
    def __add__(self, other: Any) -> Coordinate:
        if isinstance(other, Coordinate):
            if other.unit != self.unit:
                raise ValueError(f"Cannot add coordinates with different units: {self.unit} vs {other.unit}")
            return Coordinate(self.value + other.value, self.unit)
        # Assume scalar
        return Coordinate(self.value + other, self.unit)
        
    def __sub__(self, other: Any) -> Coordinate:
        if isinstance(other, Coordinate):
            if other.unit != self.unit:
                raise ValueError(f"Cannot subtract coordinates with different units: {self.unit} vs {other.unit}")
            return Coordinate(self.value - other.value, self.unit)
        # Assume scalar
        return Coordinate(self.value - other, self.unit)
    
    def to_float(self) -> float:
        """Returns the value as a float."""
        return float(self.value)
    
    def to_int(self) -> int:
        """Returns the value as an int (truncated)."""
        return int(self.value)
