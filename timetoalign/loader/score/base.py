"""ScoreLoader: Base loader for symbolic scores."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from timetoalign.core import TimeUnit
from timetoalign.loader.base import Loader

from .store import ScoreEventStore


class ScoreLoader(Loader):
    """Base loader for symbolic music scores (MusicXML, MIDI-Score, TSV)."""

    _default_unit = TimeUnit.ticks
    _event_store_class = ScoreEventStore

    def load(self, *sources: Path | str) -> Self:
        """Load sources and update store metadata."""
        super().load(*sources)

        # Aggregate has_rests from source metadata
        # If any source explicitly has rests, the store has rests
        has_rests = any(m.get("has_rests", False) for m in self._source_metadata)
        self.events._has_rests = has_rests

        return self
