from __future__ import annotations

import enum

class TimeUnit(str, enum.Enum):
    """Units of measurement for coordinates."""
    
    # Physical
    SECONDS = "seconds"
    SAMPLES = "samples"
    FRAMES = "frames"
    
    # Logical
    QUARTERS = "quarters"
    BEATS = "beats"
    MEASURES = "measures"
    TICKS = "ticks"
    
    # Graphical
    PIXELS = "pixels"
    POINTS = "points"
    INCHES = "inches"
    
    def __str__(self) -> str:
        return self.value


class Domain(str, enum.Enum):
    """The temporal domain of a timeline."""
    
    PHYSICAL = "physical"
    LOGICAL = "logical"
    GRAPHICAL = "graphical"
    
    def __str__(self) -> str:
        return self.value


class NumberType(str, enum.Enum):
    """The type of number used for coordinates."""
    
    INT = "int"
    FLOAT = "float"
    FRACTION = "fraction"
    
    def __str__(self) -> str:
        return self.value
