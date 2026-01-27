"""ScoreLoader: Base loader for symbolic scores."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from typing_extensions import Self

from timetoalign.core import TimeUnit
from timetoalign.loader.base import Loader

from .bundle import ScoreBundle
from .store import ScoreEventStore


class ScoreLoader(Loader):
    """Base loader for symbolic music scores (MusicXML, MIDI-Score, TSV)."""

    _default_unit = TimeUnit.ticks
    _event_store_class = ScoreEventStore

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bundle = ScoreBundle.empty()

    @property
    def bundle(self) -> ScoreBundle:
        """The ScoreBundle containing all loaded score elements."""
        return self._bundle

    @property
    def events(self) -> ScoreEventStore:
        """The primary event store (notes), for compatibility."""
        return self._bundle.notes

    @abstractmethod
    def _load_source(self, source: Path) -> ScoreBundle:
        """Load a single source file into a ScoreBundle.

        Args:
            source: Path to the source file.

        Returns:
            A ScoreBundle containing the loaded data.
        """
        ...

    def load(self, *sources: Path | str) -> Self:
        """Load sources into the bundle.

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.
        """
        for source in sources:
            path = Path(source)

            # Load bundle from source
            bundle = self._load_source(path)

            # Update metadata
            meta = bundle.metadata.copy()
            meta["path"] = str(path)
            meta["loaded_at"] = datetime.now(timezone.utc).isoformat()

            self._sources.append(path)
            self._source_metadata.append(meta)

            # Extend internal bundle
            self._bundle.extend(bundle)

        return self

    def clear(self) -> None:
        """Clear all loaded sources and bundle data."""
        super().clear()
        self._bundle = ScoreBundle.empty()
