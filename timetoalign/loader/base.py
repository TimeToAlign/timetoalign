"""Loader: Base classes for loading music representations into TimeToAlign!

This module provides the loader hierarchy for TimeToAlign!:

- **Loader (ABC)**: Base class for all loaders
- **EventLoader (ABC)**: Returns EventStore (events only)
- **ManifestLoader (ABC)**: Returns ManifestData (dimensions/metadata only)
- **AlignmentLoader (ABC)**: Returns AlignmentStore (events + C-maps + Matches)

Design principles:
- Multi-source: One Loader can aggregate multiple files
- Metadata in table: Deterministic, stored in PyArrow schema metadata
- Polymorphic returns: Different loader categories return different types
- Subclassable: Domain-specific loaders extend these ABCs
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, Union

import numpy as np
import pyarrow as pa
from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit

from .events import EventData

# Type alias for _load_source return: supports both vectorized and legacy modes
LoadSourceResult = Union[
    tuple[dict[str, Any], dict[str, np.ndarray | pa.Array]],  # Vectorized: column dict
    tuple[dict[str, Any], list[dict[str, Any]]],  # Legacy: row dicts
]

if TYPE_CHECKING:
    from timetoalign.loader.store import AlignmentStore, EventStore
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)

# Type variable for polymorphic loader returns
T = TypeVar("T")


class Loader(ABC):
    """Abstract base class for loading music representations.

    Loader provides a unified interface for loading one or more source files
    and aggregating their events into an EventData. Metadata about the sources
    is stored in the PyArrow table's schema metadata for determinism.

    Subclasses must implement:
    - _load_source(): Parse a single source file into event rows
    - _default_unit: The default time unit for this loader type

    Attributes:
        events: The EventData containing all loaded events.
        sources: List of loaded source file paths.
        unit: The time unit for coordinates.
        number_type: The number type for coordinates.

    Examples:
        >>> # Subclass implementation
        >>> class MidiLoader(Loader):
        ...     _default_unit = TimeUnit.ticks
        ...     _event_data_class = EventData
        ...
        ...     def _load_source(self, path):
        ...         # Parse MIDI file, return (metadata_dict, event_rows)
        ...         return {"format": "midi"}, [{"id": "n1", ...}]
        >>>
        >>> loader = MidiLoader()
        >>> loader.load("piece.mid")
        >>> print(loader.event_summary())
    """

    # Class-level configuration (subclasses override)
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    _event_data_class: ClassVar[type[EventData]] = EventData

    def __init__(
        self,
        unit: TimeUnit | None = None,
        number_type: NumberType = NumberType.float,
    ) -> None:
        """Initialize the Loader.

        Args:
            unit: The time unit for coordinates. Defaults to class's _default_unit.
            number_type: The number type for coordinates.
        """
        self._unit = unit or self._default_unit
        self._number_type = number_type
        self._sources: list[Path] = []
        self._source_metadata: list[dict[str, Any]] = []
        self._events: EventData = self._event_data_class.empty(
            self._unit, self._number_type
        )

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> LoadSourceResult:
        """Load a single source file.

        Subclasses implement this to parse their specific format.

        VECTORIZED API (preferred):
            Return (metadata_dict, column_dict) where column_dict contains
            numpy/pyarrow arrays for each column. This enables zero-iteration
            table construction.

        LEGACY API (deprecated):
            Return (metadata_dict, row_dicts) where row_dicts is a list of
            event dictionaries. This requires row iteration and should be
            migrated to the vectorized API.

        Args:
            source: Path to the source file.

        Returns:
            A tuple of (metadata_dict, event_data):
            - metadata_dict: File-specific metadata (format, duration, etc.)
            - event_data: Either:
                - dict[str, np.ndarray | pa.Array]: Column arrays (vectorized)
                - list[dict[str, Any]]: Row dicts (legacy, deprecated)

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def events(self) -> EventData:
        """The EventData containing all loaded events."""
        return self._events

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def unit(self) -> TimeUnit:
        """The time unit for coordinates."""
        return self._unit

    @property
    def number_type(self) -> NumberType:
        """The number type for coordinates."""
        return self._number_type

    @property
    def metadata(self) -> dict[str, Any]:
        """Aggregated metadata from all sources.

        Returns:
            Dict with loader info and per-source metadata.
        """
        return {
            "loader_class": self.__class__.__name__,
            "unit": str(self._unit),
            "number_type": str(self._number_type),
            "source_count": len(self._sources),
            "sources": self._source_metadata,
        }

    @property
    def store(self) -> "EventStore":
        """Return an EventStore wrapping the loader's events.

        Subclasses may override to return specialized stores
        (e.g., ScoreStore, MidiStore). Default implementation
        wraps self.events in a SingleStore.

        Returns:
            An EventStore providing uniform access to loaded data.
        """
        from timetoalign.loader.store import SingleStore

        return SingleStore(self._events, name="events")

    def create_timeline(
        self,
        uid: str | None = None,
        store_filters: dict[str, dict[str, Any]] | None = None,
        include_stores: list[str] | None = None,
        exclude_stores: list[str] | None = None,
        flatten: bool = False,
    ) -> "Timeline":
        """Create a Timeline from the loaded events.

        Convenience method that delegates to self.store.create_timeline().

        Args:
            uid: Unique ID for the parent timeline. Auto-generated if None.
            store_filters: Per-data filter kwargs to apply before timeline
                creation. Example: {"notes": {"event_type": "Note"}}.
            include_stores: Only include these data (default: all non-empty).
            exclude_stores: Exclude these data from the timeline.
            flatten: If True, merge all events into a single parent timeline.

        Returns:
            A Timeline containing the loaded events.

        Examples:
            >>> loader = Ms3Loader()
            >>> loader.load("notes.tsv")
            >>> timeline = loader.create_timeline(uid="my_score")
        """
        return self.store.create_timeline(
            uid=uid,
            store_filters=store_filters,
            include_stores=include_stores,
            exclude_stores=exclude_stores,
            flatten=flatten,
        )

    def create_timelines(
        self,
        id_pattern: str | None = None,
    ) -> "list[Timeline]":
        """Create all timelines, optionally filtered by regex pattern.

        The default implementation returns a single-element list with
        ``create_timeline()``. Subclasses with multi-timeline output
        (e.g., ``TiliaJsonLoader``, ``MatchfileLoader``) override this.

        Args:
            id_pattern: Optional regex pattern to filter timeline IDs.

        Returns:
            List of `Timeline` objects.
        """
        return [self.create_timeline()]

    def create_group(self, **kwargs: Any) -> Any:
        """Create a `TimelineGroup`. Override in subclasses that support groups.

        Returns:
            A `TimelineGroup`, or ``None`` if the loader does not produce groups.
        """
        return None

    def create_bundle(self, **kwargs: Any) -> Any:
        """Create an `AlignmentBundle`. Override in subclasses that support bundles.

        Returns:
            An `AlignmentBundle`, or ``None`` if the loader does not produce bundles.
        """
        return None

    # endregion

    # region Item Access

    def __getitem__(self, key: str) -> "EventData":
        """Access a named EventData table from the store.

        Delegates to ``self.store[key]``.

        Args:
            key: The name of the EventData table.

        Returns:
            The `EventData` for the given key.

        Raises:
            KeyError: If the key is not found in the store.
        """
        return self.store[key]

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        Events from all sources are aggregated into the EventData.
        Metadata for each source is recorded separately.

        Supports both vectorized (column dict) and legacy (row dicts) modes:
        - Vectorized: _load_source returns dict[str, np.ndarray | pa.Array]
        - Legacy: _load_source returns list[dict[str, Any]]

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)

            # Get source metadata and event data
            source_meta, event_data = self._load_source(path)

            # Add loading metadata
            source_meta["path"] = str(path)
            source_meta["loaded_at"] = datetime.now(timezone.utc).isoformat()

            # Track source
            self._sources.append(path)
            self._source_metadata.append(source_meta)

            # Add events - detect vectorized vs legacy mode
            if event_data:
                if isinstance(event_data, dict):
                    # VECTORIZED MODE: event_data is column dict
                    # Use from_arrays for zero-iteration construction
                    column_dict: dict[str, Any] = event_data
                    # Check for extra schema fields (e.g., from CoordinateField)
                    extra_fields = getattr(self, "_extra_schema_fields", None)
                    new_data = self._event_data_class.from_arrays(
                        column_dict,
                        self._unit,
                        self._number_type,
                        extra_fields=extra_fields,
                    )
                else:
                    # LEGACY MODE: event_data is list of row dicts
                    # Use from_dicts (triggers row iteration - deprecated)
                    module_logger.debug(
                        f"Using legacy row-based loading for {path.name}. "
                        "Consider migrating to vectorized API."
                    )
                    row_dicts: list[dict[str, Any]] = event_data
                    new_data = self._event_data_class.from_dicts(
                        row_dicts, self._unit, self._number_type
                    )

                # For the first source with events, replace the empty _events
                # This handles cases where extra columns create a different schema
                if len(self._events) == 0:
                    self._events = new_data
                else:
                    self._events.extend(new_data)

        return self

    def clear(self) -> None:
        """Clear all loaded sources and events."""
        self._sources.clear()
        self._source_metadata.clear()
        self._events = self._event_data_class.empty(self._unit, self._number_type)

    # endregion

    # region Stats (delegated to EventData)

    def event_summary(self) -> dict[str, Any]:
        """Get a summary of loaded events.

        Returns:
            Dict with event counts, types, coordinate range, etc.
        """
        summary = self._events.summary()
        summary["sources"] = [str(s) for s in self._sources]
        return summary

    def count_events_by_type(self) -> dict[str, int]:
        """Count events grouped by event_type.

        Returns:
            Dict mapping event type names to counts.
        """
        return self._events.count_by("event_type")

    def count_events_by_temporal_type(self) -> dict[str, int]:
        """Count events grouped by temporal_type (instant/interval).

        Returns:
            Dict mapping "instant"/"interval" to counts.
        """
        return self._events.count_by("temporal_type")

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return the total number of events across all store tables."""
        return self.store.event_count

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"{self.__class__.__name__}("
            f"sources={len(self._sources)}, "
            f"events={self.store.event_count}, "
            f"unit={self._unit})"
        )

    # endregion

    # region C-Map Creation

    def create_cmap(
        self,
        source_column: str,
        target_column: str,
        *,
        map_type: type | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a ConversionMap from two coordinate columns.

        This method creates a C-Map from loaded coordinate data, enabling
        conversion between different coordinate systems (e.g., seconds to pixels).

        Both columns must contain coordinate data (either core coordinates like
        'start'/'end', or CoordinateField extra columns).

        Args:
            source_column: Name of the source coordinate column.
            target_column: Name of the target coordinate column.
            map_type: The map class to create. Defaults to TableMap.
                Supported: TableMap, LinearMap, ScalarMap.
            **kwargs: Additional arguments passed to the map constructor.
                For TableMap: kind, extrapolate
                For LinearMap: (computed automatically from data)

        Returns:
            A ConversionMap instance.

        Raises:
            ValueError: If columns don't exist or aren't coordinate columns.
            ValueError: If insufficient data points for the map type.

        Examples:
            >>> # Load data with dual coordinates
            >>> loader.load("data.tsv")

            >>> # Create TableMap (default) from start -> x_pixels
            >>> cmap = loader.create_cmap("start", "x_pixels")

            >>> # Create LinearMap (fits y = ax + b to data)
            >>> cmap = loader.create_cmap("start", "x_pixels", map_type=LinearMap)

            >>> # TableMap with custom interpolation
            >>> cmap = loader.create_cmap("start", "x_pixels", kind="cubic")
        """
        from timetoalign.maps import LinearMap, ScalarMap, TableMap

        # Default to TableMap
        if map_type is None:
            map_type = TableMap

        # Extract coordinate values from columns
        source_values = self._extract_coordinate_values(source_column)
        target_values = self._extract_coordinate_values(target_column)

        if len(source_values) != len(target_values):
            raise ValueError(
                f"Column length mismatch: {source_column} has {len(source_values)} "
                f"values, {target_column} has {len(target_values)}"
            )

        if len(source_values) < 2:
            raise ValueError(
                f"Need at least 2 data points to create a C-Map, got {len(source_values)}"
            )

        # Get units from column metadata
        source_unit = self._get_column_unit(source_column)
        target_unit = self._get_column_unit(target_column)

        # Create the appropriate map type
        if map_type is TableMap:
            return TableMap(
                x_values=source_values,
                y_values=target_values,
                source_unit=source_unit,
                target_unit=target_unit,
                **kwargs,
            )
        elif map_type is LinearMap:
            # Fit linear regression: y = ax + b
            x = np.array(source_values, dtype=np.float64)
            y = np.array(target_values, dtype=np.float64)
            # Use numpy's polyfit for simple linear regression
            coeffs = np.polyfit(x, y, 1)
            scalar, offset = coeffs[0], coeffs[1]
            return LinearMap(
                scalar=float(scalar),
                offset=float(offset),
                source_unit=source_unit,
                target_unit=target_unit,
                **kwargs,
            )
        elif map_type is ScalarMap:
            # Fit pure scaling: y = ax (no offset)
            x = np.array(source_values, dtype=np.float64)
            y = np.array(target_values, dtype=np.float64)
            # Least squares fit through origin: scalar = sum(x*y) / sum(x*x)
            scalar = np.sum(x * y) / np.sum(x * x)
            return ScalarMap(
                scalar=float(scalar),
                source_unit=source_unit,
                target_unit=target_unit,
                **kwargs,
            )
        else:
            raise ValueError(
                f"Unsupported map_type: {map_type}. "
                f"Supported: TableMap, LinearMap, ScalarMap"
            )

    def _extract_coordinate_values(self, column_name: str) -> list[float]:
        """Extract float values from a coordinate column.

        Args:
            column_name: The column name to extract.

        Returns:
            List of float coordinate values.

        Raises:
            ValueError: If column doesn't exist or isn't a coordinate column.
        """
        import pyarrow.compute as pc

        table = self._events._table

        if column_name not in table.column_names:
            raise ValueError(
                f"Column '{column_name}' not found. " f"Available: {table.column_names}"
            )

        column = table.column(column_name)

        # Check if it's a coordinate struct (has 'value' field)
        if pa.types.is_struct(column.type):
            field_names = [f.name for f in column.type]
            if "value" in field_names:
                # Extract the 'value' field from the struct
                values = pc.struct_field(column, "value")
                return values.to_pylist()
            else:
                raise ValueError(
                    f"Column '{column_name}' is a struct but doesn't have a 'value' "
                    f"field. Fields: {field_names}"
                )
        elif pa.types.is_floating(column.type) or pa.types.is_integer(column.type):
            # Plain numeric column
            return [float(v) for v in column.to_pylist() if v is not None]
        else:
            raise ValueError(
                f"Column '{column_name}' is not a coordinate column. "
                f"Type: {column.type}"
            )

    def _get_column_unit(self, column_name: str) -> str | None:
        """Get the unit metadata from a coordinate column.

        Args:
            column_name: The column name.

        Returns:
            The unit string, or None if not specified.
        """
        table = self._events._table
        schema = table.schema

        field_idx = schema.get_field_index(column_name)
        if field_idx < 0:
            return None

        field = schema.field(field_idx)
        if field.metadata:
            unit = field.metadata.get(b"unit")
            if unit:
                return unit.decode("utf-8")

        # For core coordinate columns (start, end, duration), use loader's unit
        if column_name in ("start", "end", "duration"):
            return str(self._unit.value) if self._unit else None

        return None

    # endregion

    # region Convenience Constructors

    @classmethod
    def from_file(cls, *paths: Path | str, **kwargs: Any) -> Self:
        """Load one or more files and return the loader (convenience constructor).

        This combines instantiation and loading into a single call.

        Args:
            *paths: Paths to source files.
            **kwargs: Additional keyword arguments passed to ``__init__``.

        Returns:
            A new Loader instance with the files already loaded.

        Examples:
            >>> loader = Ms3Loader.from_file("notes.tsv")
            >>> len(loader.events)
            42
        """
        loader = cls(**kwargs)
        loader.load(*paths)
        return loader

    # endregion

    # region HTML Representation

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks.

        Shows the loader class name, source files, store summary,
        and available create methods.
        """
        parts = [f"<h4>{self.__class__.__name__}</h4>"]
        parts.append("<table>")

        # Sources
        n_sources = len(self._sources)
        parts.append(f"<tr><td><b>Sources</b></td><td>{n_sources} file(s)</td></tr>")
        for s in self._sources[:5]:
            parts.append(f"<tr><td></td><td><code>{s.name}</code></td></tr>")
        if n_sources > 5:
            parts.append(f"<tr><td></td><td>... and {n_sources - 5} more</td></tr>")

        # Events
        parts.append(
            f"<tr><td><b>Events</b></td><td>{self.store.event_count}</td></tr>"
        )
        parts.append(f"<tr><td><b>Unit</b></td><td>{self._unit.value}</td></tr>")

        # Available create methods
        creates = ["create_timeline()"]
        if self.create_group.__func__ is not Loader.create_group:
            creates.append("create_group()")
        if self.create_bundle.__func__ is not Loader.create_bundle:
            creates.append("create_bundle()")
        parts.append(
            f"<tr><td><b>Create</b></td>" f"<td>{', '.join(creates)}</td></tr>"
        )

        parts.append("</table>")
        return "\n".join(parts)

    # endregion

    # region Serialization

    def to_parquet(self, path: Path | str) -> None:
        """Save the loaded events to a Parquet file.

        The metadata (including source info) is preserved in the file.

        Args:
            path: Path to write the Parquet file.
        """
        self.events.to_parquet(path)

    @classmethod
    def from_parquet(cls, path: Path | str) -> Self:
        """Load a Loader from a Parquet file.

        Note: This creates a new Loader with the EventData loaded,
        but source paths may not be accessible for re-loading.

        Args:
            path: Path to the Parquet file.

        Returns:
            A new Loader with events loaded from the file.
        """
        events = cls._event_data_class.from_parquet(path)
        loader = cls.__new__(cls)
        loader._unit = events.unit
        loader._number_type = events.number_type
        loader._events = events
        loader._sources = []
        loader._source_metadata = []
        return loader

    # endregion


# Alias for backwards compatibility and clarity
EventLoader = Loader
"""EventLoader is an alias for Loader - the base class for loaders that return EventStore."""


# region ManifestData


@dataclass
class ManifestData:
    """Container for manifest/metadata from ManifestLoader.

    ManifestData holds structural information about a source without events.
    This includes dimensions, sample rates, page counts, etc.

    Attributes:
        dimensions: Dict of named dimensions (e.g., {"width": 1920, "height": 1080}).
        metadata: Additional metadata about the source.
        source_path: Path to the source file.
        source_type: Type of source (e.g., "audio", "image", "pdf").

    Examples:
        >>> # Audio manifest
        >>> manifest = ManifestData(
        ...     dimensions={"duration_samples": 44100 * 60, "duration_seconds": 60.0},
        ...     metadata={"sample_rate": 44100, "channels": 2},
        ...     source_type="audio",
        ... )

        >>> # PDF manifest
        >>> manifest = ManifestData(
        ...     dimensions={"pages": 10, "width": 612, "height": 792},
        ...     metadata={"title": "Score", "dpi": 72},
        ...     source_type="pdf",
        ... )
    """

    dimensions: dict[str, int | float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    source_type: str = "unknown"

    def __repr__(self) -> str:
        dims_str = ", ".join(f"{k}={v}" for k, v in self.dimensions.items())
        return f"ManifestData({self.source_type}, {dims_str})"


# endregion


# region ManifestLoader


class ManifestLoader(ABC):
    """Abstract base class for loaders that return ManifestData.

    ManifestLoader is for sources that provide dimensional/structural
    information without timeline events:
    - Audio files -> duration, sample rate, channels
    - PDF files -> pages, dimensions
    - Images -> width, height, DPI

    Subclasses must implement:
    - _load_source(): Parse a single source into ManifestData

    The loaded ManifestData can be used to create empty timelines with
    correct dimensions, or to configure subsequent event loading.

    Examples:
        >>> class AudioManifestLoader(ManifestLoader):
        ...     def _load_source(self, source: Path) -> ManifestData:
        ...         # Read audio header
        ...         return ManifestData(
        ...             dimensions={"duration_samples": n_samples},
        ...             metadata={"sample_rate": sr},
        ...             source_type="audio",
        ...         )
    """

    def __init__(self) -> None:
        """Initialize the ManifestLoader."""
        self._sources: list[Path] = []
        self._manifests: list[ManifestData] = []
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> ManifestData:
        """Load a single source file into ManifestData.

        Subclasses implement this to parse their specific format.

        Args:
            source: Path to the source file.

        Returns:
            ManifestData containing dimensions and metadata.

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def manifests(self) -> list[ManifestData]:
        """List of loaded ManifestData objects."""
        return list(self._manifests)

    @property
    def manifest(self) -> ManifestData | None:
        """The first (or only) manifest, for convenience."""
        return self._manifests[0] if self._manifests else None

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)
            manifest = self._load_source(path)
            manifest.source_path = path

            self._sources.append(path)
            self._manifests.append(manifest)
            self._logger.debug(f"Loaded manifest from {path}")

        return self

    def clear(self) -> None:
        """Clear all loaded sources and manifests."""
        self._sources.clear()
        self._manifests.clear()

    # endregion

    # region Timeline Creation

    def create_timeline(
        self,
        uid: str | None = None,
        **kwargs: Any,
    ) -> "Timeline":
        """Create a Timeline from the loaded manifest.

        Subclasses override this to create the appropriate timeline type
        (e.g., ``DiscretePhysicalTimeline`` for audio, ``DiscreteGraphicalTimeline``
        for images).

        Args:
            uid: Unique identifier for the timeline. Auto-generated if None.
            **kwargs: Additional arguments for subclass implementations.

        Returns:
            A Timeline representing the loaded source.

        Raises:
            NotImplementedError: If the subclass does not provide an implementation.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement create_timeline(). "
            "Subclasses should override this method."
        )

    def create_timelines(
        self,
        id_pattern: str | None = None,
    ) -> "list[Timeline]":
        """Create all timelines, optionally filtered by regex pattern.

        Default implementation returns a single-element list.

        Args:
            id_pattern: Optional regex pattern to filter timeline IDs.

        Returns:
            List of `Timeline` objects.
        """
        return [self.create_timeline()]

    # endregion

    # region Convenience Constructors

    @classmethod
    def from_file(cls, *paths: Path | str, **kwargs: Any) -> Self:
        """Load one or more files and return the loader (convenience constructor).

        Args:
            *paths: Paths to source files.
            **kwargs: Additional keyword arguments passed to ``__init__``.

        Returns:
            A new ManifestLoader instance with the files already loaded.

        Examples:
            >>> loader = AudioLoader.from_file("song.wav")
            >>> loader.duration_seconds
            180.0
        """
        loader = cls(**kwargs)
        loader.load(*paths)
        return loader

    # endregion

    # region HTML Representation

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        parts = [f"<h4>{self.__class__.__name__}</h4>"]
        parts.append("<table>")

        n_sources = len(self._sources)
        parts.append(f"<tr><td><b>Sources</b></td><td>{n_sources} file(s)</td></tr>")
        for s in self._sources[:5]:
            parts.append(f"<tr><td></td><td><code>{s.name}</code></td></tr>")

        if self._manifests:
            m = self._manifests[0]
            for k, v in m.dimensions.items():
                parts.append(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>")

        parts.append("</table>")
        return "\n".join(parts)

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return the number of loaded manifests."""
        return len(self._manifests)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(sources={len(self._sources)})"

    # endregion


# endregion


# region AlignmentLoader


class AlignmentLoader(ABC):
    """Abstract base class for loaders that return AlignmentStore.

    AlignmentLoader is for formats that encode aligned multimodal data:
    - IEEE 1599 -> score + audio + graphical alignments
    - TiLiA JSON -> hierarchical annotations with alignments
    - Match files -> score-to-performance alignment

    Subclasses must implement:
    - _load_source(): Parse a single source into AlignmentStore

    AlignmentStore contains:
    - EventData tables for each domain/layer
    - ConversionMaps between coordinate systems
    - Match objects representing alignment claims

    Examples:
        >>> class Ieee1599Loader(AlignmentLoader):
        ...     def _load_source(self, source: Path) -> AlignmentStore:
        ...         # Parse IEEE 1599 XML
        ...         return AlignmentStore(
        ...             events=event_store,
        ...             cmaps=[tick_to_seconds_map],
        ...             matches=match_data,
        ...         )
    """

    def __init__(self) -> None:
        """Initialize the AlignmentLoader."""
        self._sources: list[Path] = []
        self._source_metadata: list[dict[str, Any]] = []
        self._store: AlignmentStore | None = None
        self._logger = module_logger.getChild(self.__class__.__name__)

    # region Abstract Methods

    @abstractmethod
    def _load_source(self, source: Path) -> "AlignmentStore":
        """Load a single source file into AlignmentStore.

        Subclasses implement this to parse their specific format.

        Args:
            source: Path to the source file.

        Returns:
            AlignmentStore containing events, C-maps, and matches.

        Raises:
            FileNotFoundError: If the source file doesn't exist.
            ValueError: If the source file is invalid.
        """
        ...

    # endregion

    # region Properties

    @property
    def sources(self) -> list[Path]:
        """List of loaded source file paths."""
        return list(self._sources)

    @property
    def store(self) -> "AlignmentStore | None":
        """The AlignmentStore containing all loaded data."""
        return self._store

    @property
    def metadata(self) -> dict[str, Any]:
        """Aggregated metadata from all sources."""
        return {
            "loader_class": self.__class__.__name__,
            "source_count": len(self._sources),
            "sources": self._source_metadata,
        }

    # endregion

    # region Loading

    def load(self, *sources: Path | str) -> Self:
        """Load one or more source files.

        For multiple sources, stores are merged (events concatenated,
        C-maps and matches aggregated).

        Args:
            *sources: Paths to source files.

        Returns:
            Self, for method chaining.

        Raises:
            FileNotFoundError: If any source doesn't exist.
            ValueError: If any source is invalid.
        """
        for source in sources:
            path = Path(source)

            # Load store from source
            loaded_store = self._load_source(path)

            # Track metadata
            source_meta = {
                "path": str(path),
                "loaded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._sources.append(path)
            self._source_metadata.append(source_meta)

            # Merge or set store
            if self._store is None:
                self._store = loaded_store
            else:
                self._store.extend(loaded_store)

            self._logger.debug(f"Loaded alignment from {path}")

        return self

    def clear(self) -> None:
        """Clear all loaded sources and store."""
        self._sources.clear()
        self._source_metadata.clear()
        self._store = None

    # endregion

    # region Timeline & Bundle Creation

    def create_timeline(self, id: str | None = None, **kwargs: Any) -> "Timeline":
        """Create a single Timeline by ID.

        Subclasses override this to assemble timelines from loaded data.

        Args:
            id: Timeline identifier. Interpretation is subclass-specific.
            **kwargs: Additional arguments for subclass implementations.

        Returns:
            A Timeline.

        Raises:
            NotImplementedError: If the subclass does not provide an implementation.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement create_timeline(). "
            "Subclasses should override this method."
        )

    def create_timelines(
        self,
        id_pattern: str | None = None,
    ) -> "list[Timeline]":
        """Create all timelines, optionally filtered by regex pattern.

        Args:
            id_pattern: Optional regex pattern to filter timeline IDs.

        Returns:
            List of `Timeline` objects.

        Raises:
            NotImplementedError: If the subclass does not provide an implementation.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement create_timelines(). "
            "Subclasses should override this method."
        )

    def create_group(self, **kwargs: Any) -> Any:
        """Create a `TimelineGroup`. Override in subclasses that support groups.

        Returns:
            A `TimelineGroup`, or ``None`` if not supported.
        """
        return None

    def create_bundle(self, **kwargs: Any) -> Any:
        """Create an `AlignmentBundle`. Override in subclasses that support bundles.

        Returns:
            An `AlignmentBundle`, or ``None`` if not supported.
        """
        return None

    # endregion

    # region Convenience Constructors

    @classmethod
    def from_file(cls, *paths: Path | str, **kwargs: Any) -> Self:
        """Load one or more files and return the loader (convenience constructor).

        Args:
            *paths: Paths to source files.
            **kwargs: Additional keyword arguments passed to ``__init__``.

        Returns:
            A new AlignmentLoader instance with the files already loaded.
        """
        loader = cls(**kwargs)
        loader.load(*paths)
        return loader

    # endregion

    # region HTML Representation

    def _repr_html_(self) -> str:
        """Rich HTML representation for Jupyter notebooks."""
        parts = [f"<h4>{self.__class__.__name__}</h4>"]
        parts.append("<table>")

        n_sources = len(self._sources)
        parts.append(f"<tr><td><b>Sources</b></td><td>{n_sources} file(s)</td></tr>")
        for s in self._sources[:5]:
            parts.append(f"<tr><td></td><td><code>{s.name}</code></td></tr>")

        n_events = len(self)
        parts.append(f"<tr><td><b>Events</b></td><td>{n_events}</td></tr>")

        # Available create methods
        creates = []
        try:
            self.create_timeline
            creates.append("create_timeline()")
        except Exception:
            pass
        try:
            self.create_timelines
            creates.append("create_timelines()")
        except Exception:
            pass
        if self.create_group.__func__ is not AlignmentLoader.create_group:
            creates.append("create_group()")
        if self.create_bundle.__func__ is not AlignmentLoader.create_bundle:
            creates.append("create_bundle()")
        if creates:
            parts.append(
                f"<tr><td><b>Create</b></td>" f"<td>{', '.join(creates)}</td></tr>"
            )

        parts.append("</table>")
        return "\n".join(parts)

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return total event count across all stores."""
        if self._store is None:
            return 0
        return self._store.event_count

    def __repr__(self) -> str:
        """Return string representation."""
        n_events = len(self) if self._store else 0
        return (
            f"{self.__class__.__name__}("
            f"sources={len(self._sources)}, "
            f"events={n_events})"
        )

    # endregion


# endregion
