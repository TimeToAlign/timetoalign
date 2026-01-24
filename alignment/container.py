from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from timetoalign.alignment.match import Match
from timetoalign.timelines.timeline import Timeline

module_logger = logging.getLogger(__name__)

@dataclass
class Alignment:
    """The top-level container for a set of aligned timelines.
    
    Stores:
    - Timelines (Nodes)
    - Matches (Edges/Hyperedges)
    - Global Configuration
    
    This corresponds to the 'Project' or 'Corpus' concept.
    """
    
    id: str # Project/Alignment ID
    
    # Timelines by ID
    _timelines: Dict[str, Timeline] = field(default_factory=dict)
    
    # Matches by ID
    _matches: Dict[str, Match] = field(default_factory=dict)
    
    def add_timeline(self, timeline: Timeline):
        if timeline.id in self._timelines:
            module_logger.warning(f"Overwriting timeline {timeline.id} in alignment {self.id}")
        self._timelines[timeline.id] = timeline
        
    def get_timeline(self, id: str) -> Optional[Timeline]:
        return self._timelines.get(id)
        
    def add_match(self, match: Match):
        self._matches[match.id] = match
        
    def get_matches_for_event(self, event_id: str) -> List[Match]:
        """Returns all matches that include a specific event."""
        # Naive implementation. For perf, we would maintain an inverted index.
        return [m for m in self._matches.values() if m.has_event(event_id)]
    
    @property
    def timelines(self) -> List[Timeline]:
        return list(self._timelines.values())
