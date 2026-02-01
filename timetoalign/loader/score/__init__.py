"""Score loading module for TimeToAlign!"""

from __future__ import annotations

from .bundle import ScoreStore
from .measuremap import MeasureMapLoader
from .music21 import Music21Loader
from .partitura import PartituraLoader
from .store import ScoreEventData, ScoreEventType
from .tsv import TSVLoader

__all__ = [
    "MeasureMapLoader",
    "Music21Loader",
    "PartituraLoader",
    "ScoreStore",
    "ScoreEventData",
    "ScoreEventType",
    "TSVLoader",
]
