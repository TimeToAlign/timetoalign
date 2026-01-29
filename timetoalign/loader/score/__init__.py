"""Score loading module for TimeToAlign!"""

from __future__ import annotations

from .bundle import ScoreStore
from .music21 import Music21Loader
from .partitura import PartituraLoader
from .store import ScoreEventData, ScoreEventType

__all__ = [
    "Music21Loader",
    "PartituraLoader",
    "ScoreStore",
    "ScoreEventData",
    "ScoreEventType",
]
