"""Score loading module for TimeToAlign!

This package provides loaders for symbolic music scores.  The core classes
(:class:`ScoreStore`, :class:`ScoreEventData`, :class:`ScoreEventType`,
:class:`MeasureMapLoader`) are always available.  Individual loader backends
are guarded behind optional dependencies:

* :class:`PartituraLoader` — requires the ``partitura`` extra
* :class:`Music21Loader` — requires the ``music21`` extra
* :class:`TSVLoader` — requires the ``ms3`` extra

If you attempt to import a loader whose dependency is not installed, an
:exc:`ImportError` is raised with installation instructions.
"""

from __future__ import annotations

from .bundle import ScoreStore
from .measuremap import MeasureMapLoader
from .store import ScoreEventData, ScoreEventType

__all__ = [
    "MeasureMapLoader",
    "ScoreStore",
    "ScoreEventData",
    "ScoreEventType",
]

# ---------------------------------------------------------------------------
# Optional loader backends — guarded so that importing the package never
# fails merely because one backend's dependency is absent.
# ---------------------------------------------------------------------------

try:
    from .partitura import PartituraLoader

    __all__.append("PartituraLoader")
except ImportError:
    pass

try:
    from .music21 import Music21Loader

    __all__.append("Music21Loader")
except ImportError:
    pass

try:
    from .tsv import TSVLoader

    __all__.append("TSVLoader")
except ImportError:
    pass
