from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from timetoalign.core.ids import ScopedId

@dataclass
class Match:
    """A Match represents a claim that a set of events is equivalent.
    
    Supports:
    - N-way matching (set of event IDs)
    - NOMATCH sentinels (implicit exclusion from the set)
    - Metadata (certainty, creator)
    """
    
    id: str  # Scoped ID for the Match itself
    
    # Set of event IDs involved in this match.
    # Format: ScopedId strings ("source:event_id")
    event_ids: Set[str] = field(default_factory=set)
    
    # Metadata
    certainty: float = 1.0  # 0.0 to 1.0
    creator: Optional[str] = None
    comment: Optional[str] = None
    
    def add_event(self, event_id: str):
        self.event_ids.add(event_id)
        
    def has_event(self, event_id: str) -> bool:
        return event_id in self.event_ids
