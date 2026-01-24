from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, runtime_checkable, Optional

from timetoalign.core.enums import TimeUnit
from timetoalign.coordinates.coordinate import Coordinate

@runtime_checkable
class ConversionMap(Protocol):
    """Protocol for mapping coordinates from one unit to another."""
    
    source_unit: TimeUnit
    target_unit: TimeUnit
    
    @abstractmethod
    def convert(self, coordinate: Coordinate) -> Coordinate:
        """Converts a coordinate from source_unit to target_unit."""
        ...
        
    @abstractmethod
    def inverse(self) -> Optional[ConversionMap]:
        """Returns the inverse map if bijective, else None."""
        ...
