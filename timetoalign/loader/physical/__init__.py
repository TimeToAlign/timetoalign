"""Physical domain loaders for TimeToAlign!

This package provides loaders for the physical (acoustic/time) domain:
- AudioLoader: Load audio file metadata and create DiscretePhysicalTimelines.

These are Type-1 (Manifest) loaders: they extract dimensions and metadata
from audio files without loading the actual sample data. The resulting
timelines have their length set in samples, with automatic C-maps for
sample-to-seconds conversion.

Design Philosophy:
    Unlike event-based loaders (ScoreLoader, MidiLoader) that derive timeline
    dimensions from event coordinates, AudioLoader follows the manifest pattern
    (like IIIFManifestLoader): the timeline dimensions are fixed by the file's
    inherent properties (sample count, sample rate).

    Events (e.g., note annotations, beat markers) can be added to these timelines
    after creation using separate event loaders.
"""

from __future__ import annotations

from .audio import AudioInfo, AudioLoader

__all__ = [
    "AudioLoader",
    "AudioInfo",
]
