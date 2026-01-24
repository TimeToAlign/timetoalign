from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar, Optional

module_logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ScopedId:
    """An ID with a scope prefix (e.g., source name) and a local part.
    
    Format: "{scope}:{local_id}"
    """
    scope: str
    local: str
    
    SEPARATOR: ClassVar[str] = ":"
    
    def __str__(self) -> str:
        if not self.scope:
            return self.local
        return f"{self.scope}{self.SEPARATOR}{self.local}"
    
    @classmethod
    def parse(cls, id_str: str) -> ScopedId:
        """Parses a scoped ID string into a ScopedId object."""
        if cls.SEPARATOR in id_str:
            scope, local = id_str.split(cls.SEPARATOR, 1)
            return cls(scope=scope, local=local)
        return cls(scope="", local=id_str)
    
    @classmethod
    def from_parts(cls, scope: str, local: str) -> ScopedId:
        """Creates a ScopedId, handling potential existing colons in local part strictly if needed,
        but generally trusted."""
        return cls(scope=scope, local=local)

class IdGenerator:
    """Generates unique IDs within a given scope."""
    
    def __init__(self, scope: str):
        self._scope = scope
        self._counters: dict[str, int] = {}
        self._seen: set[str] = set()

    def get_or_create(self, external_id: Optional[str], type_hint: str = "event") -> str:
        """
        Returns a scoped ID string.
        
        Args:
            external_id: The ID from the source, if any.
            type_hint: A prefix for generated IDs if external_id is missing.
            
        Returns:
            A string in "scope:local_id" format.
        """
        if external_id is not None and external_id.strip():
            # If the external ID already appears partially scoped or raw, 
            # we respect it but enforce our scope if not redundant?
            # Decision: We ALWAYS scope external IDs to avoid collision with 
            # other sources in the same alignment.
            # E.g. 'midi_track1:note_45'
            # But if external_id is "note_45" and scope is "beethoven", result is "beethoven:note_45"
            
            # TODO: Consider if external_id already contains the scope. 
            # For now, trust the caller to set scope correctly on init.
            local = external_id
            
            # Ensure uniqueness within this generator instance? 
            # If source has duplicates, we might need to handle expected duplicates vs collisions.
            # For now, assume external IDs are unique within their source scope.
            
            return str(ScopedId(self._scope, local))
            
        # Generate ID
        counter = self._counters.get(type_hint, 0) + 1
        self._counters[type_hint] = counter
        local = f"{type_hint}_{counter}"
        
        return str(ScopedId(self._scope, local))
