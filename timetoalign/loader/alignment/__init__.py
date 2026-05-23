"""Alignment loader sub-package for TimeToAlign!

This sub-package contains loaders for alignment file formats that encode
score-performance correspondences, cross-domain alignments, and related
multimodal data.

Loaders:
    MatchfileLoader: Vienna Match (.match) score-to-performance alignment files.
    TiliaJsonLoader: TiLiA JSON annotation exports (.tla/.json).
    PerformancePrecisionLoader: CAAMP audio-to-score alignment specimens
        (.solo score + Verovio timemap + per-performer alignment CSVs).

Stores:
    TiliaDictStore: DictStore subclass with TiLiA timeline type properties.
"""

from __future__ import annotations

from .matchfile import MatchfileLoader
from .performance_precision import PerformancePrecisionLoader
from .tilia import TiliaDictStore, TiliaJsonLoader

__all__ = [
    "MatchfileLoader",
    "PerformancePrecisionLoader",
    "TiliaDictStore",
    "TiliaJsonLoader",
]
