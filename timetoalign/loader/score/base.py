"""ScoreLoader: Base loader for symbolic scores."""

from __future__ import annotations

import logging
from abc import abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.base import Loader

from .events import ScoreEventData
from .store import ScoreStore

module_logger = logging.getLogger(__name__)


class ScoreLoader(Loader):
    """Base loader for symbolic music scores (MusicXML, MIDI-Score, TSV).

    All score loaders normalise coordinates to quarter-note positions using
    ``Fraction`` precision.  The reported metadata reflects this:
    ``unit='quarters'``, ``number_type='fraction'``.
    """

    _default_unit = TimeUnit.quarters
    _event_data_class = ScoreEventData

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("number_type", NumberType.fraction)
        super().__init__(*args, **kwargs)
        self._store = ScoreStore.empty()

    @property
    def store(self) -> ScoreStore:
        """The ScoreStore containing all loaded score elements."""
        return self._store

    @property
    def events(self) -> ScoreEventData:
        """The primary event data (notes), for compatibility."""
        return self._store.notes

    @abstractmethod
    def _load_source(self, source: Path) -> ScoreStore:
        """Load a single source file into a ScoreStore.

        Args:
            source: Path to the source file.

        Returns:
            A ScoreStore containing the loaded data.
        """
        ...

    def load(self, *sources: Path | str) -> Self:
        """Load sources into the store.

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.
        """
        for source in sources:
            path = Path(source)

            # Load store from source
            loaded_store = self._load_source(path)

            # Update metadata
            meta = loaded_store.metadata.copy()
            meta["path"] = str(path)
            meta["loaded_at"] = datetime.now(timezone.utc).isoformat()

            self._sources.append(path)
            self._source_metadata.append(meta)

            # Extend internal store
            self._store.extend(loaded_store)

        return self

    def clear(self) -> None:
        """Clear all loaded sources and store data."""
        super().clear()
        self._store = ScoreStore.empty()

    # region Serialization

    def to_parquet(self, path: Path | str) -> None:
        """Save the loaded score data to Parquet files.

        For ``ScoreLoader`` subclasses, data lives in a multi-facet
        ``ScoreStore`` (notes, measures, controls, annotations).  Each
        facet is written as a separate ``.parquet`` file inside a directory
        at *path*, together with a ``metadata.json`` for store-level
        metadata.

        Args:
            path: Directory to write into.  Created if it does not exist.
        """
        self._store.to_parquet(path)

    @classmethod
    def from_parquet(cls, path: Path | str) -> Self:
        """Load a ScoreLoader from a directory of Parquet files.

        Reconstructs the internal ``ScoreStore`` from the facet files
        produced by :meth:`to_parquet`.

        Args:
            path: Directory containing the facet Parquet files.

        Returns:
            A new ScoreLoader with events loaded from the files.
        """
        store = ScoreStore.from_parquet(path)
        loader = cls.__new__(cls)
        # Set attributes that __init__ would normally create
        loader._unit = cls._default_unit
        loader._number_type = NumberType.fraction
        loader._sources = []
        loader._source_metadata = []
        loader._events = cls._event_data_class.empty(loader._unit, loader._number_type)
        loader._store = store
        return loader

    # endregion
