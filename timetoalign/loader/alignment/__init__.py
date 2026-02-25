"""Alignment loader sub-package for TimeToAlign!

This sub-package contains loaders for alignment file formats that encode
score-performance correspondences, cross-domain alignments, and related
multimodal data.

Loaders:
    MatchfileLoader: Vienna Match (.match) score-to-performance alignment files.
"""

from __future__ import annotations

from .matchfile import MatchfileLoader

__all__ = [
    "MatchfileLoader",
]
