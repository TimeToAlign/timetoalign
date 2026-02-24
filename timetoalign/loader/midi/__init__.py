"""MIDI loading and storage for TimeToAlign!

The core classes (:class:`MidiLoader`, :class:`MidiStore`,
:class:`MidiEventData`, :data:`CC_PURPOSE`, :class:`MidiEventType`) are
always available.  Individual loader backends are guarded behind optional
dependencies:

* :class:`PerformanceMidiLoader` — requires the ``midi`` extra (``mido``)
* :class:`ScoreMidiLoader` — requires the ``partitura`` extra

If you attempt to import a loader whose dependency is not installed, an
:exc:`ImportError` is raised with installation instructions.
"""

from .base import MidiLoader
from .bundle import MidiStore
from .constants import CC_PURPOSE, MidiEventType
from .store import MidiEventData

__all__ = [
    "CC_PURPOSE",
    "MidiEventData",
    "MidiEventType",
    "MidiLoader",
    "MidiStore",
]

# ---------------------------------------------------------------------------
# Optional loader backends
# ---------------------------------------------------------------------------

try:
    from .performance import PerformanceMidiLoader

    __all__.append("PerformanceMidiLoader")
except ImportError:
    pass

try:
    from .score import ScoreMidiLoader

    __all__.append("ScoreMidiLoader")
except ImportError:
    pass
