from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List
import pyarrow as pa

class EventStore(ABC):
    """Adapter for external data sources.
    
    Responsibility:
    - Knows how to read a specific format (MIDI, JSON, etc.)
    - Transforms it into standard PyArrow tables for Timeline storage.
    - Manages ID generation/mapping for its events.
    """
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the source (e.g. 'tilia', 'midi'). Used for ID scoping."""
        ...
        
    @abstractmethod
    def to_table(self) -> pa.Table:
        """Returns the full event table.
        
        Must contain at least:
        - id: str (scoped)
        - category: str
        - label: str (optional)
        
        Plus any source-specific columns.
        """
        ...

    @abstractmethod
    def get_instants(self) -> pa.Table:
        """Returns table of instants.
        
        Schema:
        - coordinate: float
        - event_id: str
        """
        pass
        
    @abstractmethod
    def get_intervals(self) -> pa.Table:
        """Returns table of intervals.
        
        Schema:
        - start: float
        - end: float
        - event_id: str
        """
        pass
