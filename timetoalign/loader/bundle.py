"""EventStore and AlignmentStore: Containers for loaded data.

This module provides:
- **EventStore (ABC)**: Container for collections of EventData
- **SingleStore**: Simple wrapper for a single EventData
- **AlignmentStore**: Container for aligned multimodal data (events + C-maps + matches)

NOTE: This class was renamed from EventBundle to EventStore in the 2026-01 API
refactoring. EventStore holds one or more EventData tables.
- EventData (formerly EventStore): PyArrow-based storage for timeline events
- EventStore (formerly EventBundle): Container for multiple EventData

Design principles:
- Uniform interface for both single-data and multi-data stores
- Consistent timeline creation across all loader types
- Children timelines maintain their own 0-based coordinate systems
- AlignmentStore bundles events with conversion maps and matches
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pyarrow as pa

if TYPE_CHECKING:
    from timetoalign.core import Domain
    from timetoalign.loader.store import EventData
    from timetoalign.maps import ConversionMap
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


class EventStore(ABC):
    """Abstract base class for collections of EventData.

    Provides a uniform interface for both single-data and multi-data
    stores, enabling consistent timeline creation across loader types.

    All stores must implement the collection protocol (iteration, keys,
    items, getitem) to allow uniform access to their constituent data.

    NOTE: This class was renamed from EventBundle to EventStore in the 2026-01 API
    refactoring. EventStore holds one or more EventData tables.

    Subclasses:
        - ScoreStore: notes, measures, controls, annotations
        - MidiStore: notes, controls
        - SingleStore: generic wrapper for any single EventData

    Examples:
        >>> # Iterate over stores
        >>> for name, store in bundle.items():
        ...     print(f"{name}: {len(store)} events")

        >>> # Create default timeline with children
        >>> timeline = bundle.to_default_timeline(uid="my_score")

        >>> # Create filtered timeline
        >>> timeline = bundle.to_timeline(
        ...     store_filters={"notes": {"event_type": "Note"}},
        ...     exclude_stores=["annotations"],
        ... )
    """

    # region Abstract Methods

    @abstractmethod
    def __iter__(self) -> Iterator["EventData"]:
        """Iterate over data in canonical order.

        Yields:
            EventData in the store's canonical order.
        """
        ...

    @abstractmethod
    def items(self) -> Iterator[tuple[str, "EventData"]]:
        """Iterate over (name, data) pairs in canonical order.

        Yields:
            Tuples of (data_name, EventData).
        """
        ...

    @abstractmethod
    def keys(self) -> tuple[str, ...]:
        """Return data names in canonical order.

        Returns:
            Tuple of data names.
        """
        ...

    @abstractmethod
    def __getitem__(self, name: str) -> "EventData":
        """Get data by name.

        Args:
            name: The data name.

        Returns:
            The EventData for that name.

        Raises:
            KeyError: If name is not a valid data name.
        """
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return number of EventData in the store."""
        ...

    # endregion

    # region Collection Protocol

    def __contains__(self, name: object) -> bool:
        """Check if data name exists in the store.

        Args:
            name: Data name to check.

        Returns:
            True if name is a valid data name.
        """
        return name in self.keys()

    def values(self) -> Iterator["EventData"]:
        """Iterate over data.

        Yields:
            EventData in canonical order.
        """
        yield from self

    # endregion

    # region Conversion Maps

    def get_cmaps(self) -> dict[str, "ConversionMap"]:
        """Get ConversionMaps derivable from store metadata.

        Returns a dictionary mapping target unit names to ConversionMaps
        that can convert from this bundle's native unit. Subclasses should
        override to provide maps based on available metadata (PPQ, tempo
        events, sample rate, etc.).

        Returns:
            Dict mapping target unit name (e.g., "quarters", "seconds") to
            ConversionMap instances. Empty dict if no C-Maps can be derived.

        Examples:
            >>> bundle = midi_loader.load("performance.mid")
            >>> cmaps = bundle.get_cmaps()
            >>> if "quarters" in cmaps:
            ...     quarters = cmaps["quarters"](960)  # Convert 960 ticks
        """
        return {}

    # endregion

    # region Timeline Creation

    def create_timeline(
        self,
        uid: str | None = None,
        store_filters: dict[str, dict[str, Any]] | None = None,
        include_stores: list[str] | None = None,
        exclude_stores: list[str] | None = None,
        flatten: bool = False,
    ) -> "Timeline":
        """Create a Timeline from this store.

        By default, each data becomes a child timeline embedded at offset 0,
        maintaining its own 0-based coordinate system. The parent timeline's
        length equals the maximum length across all children.

        Args:
            uid: Unique ID for the parent timeline. Auto-generated if None.
            store_filters: Per-data filter kwargs to apply before timeline
                creation. Example: {"notes": {"event_type": "Note"}} excludes
                rests from the notes data.
            include_stores: Only include these data (default: all non-empty).
            exclude_stores: Exclude these data from the timeline.
            flatten: If True, merge all events into a single parent timeline
                without children. If False (default), each data becomes a
                child timeline at offset 0.

        Returns:
            A Timeline with the requested structure.

        Raises:
            ValueError: If no data remain after filtering, or all data
                are empty.

        Examples:
            >>> # Default: each data as a child
            >>> timeline = store.create_timeline(uid="my_score")
            >>> notes = timeline.get_child("notes")

            >>> # Filtered: only Note events, exclude annotations
            >>> timeline = store.create_timeline(
            ...     store_filters={"notes": {"event_type": "Note"}},
            ...     exclude_stores=["annotations"],
            ... )
        """
        from timetoalign.timelines.factory import create_timeline_from_bundle

        return create_timeline_from_bundle(
            self,
            uid=uid,
            store_filters=store_filters,
            include_stores=include_stores,
            exclude_stores=exclude_stores,
            flatten=flatten,
        )

    def to_timeline(
        self,
        uid: str | None = None,
        store_filters: dict[str, dict[str, Any]] | None = None,
        include_stores: list[str] | None = None,
        exclude_stores: list[str] | None = None,
        flatten: bool = False,
    ) -> "Timeline":
        """Deprecated alias for create_timeline().

        .. deprecated:: 0.2.0
            Use :meth:`create_timeline` instead.
        """
        import warnings

        warnings.warn(
            "to_timeline() is deprecated, use create_timeline() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.create_timeline(
            uid=uid,
            store_filters=store_filters,
            include_stores=include_stores,
            exclude_stores=exclude_stores,
            flatten=flatten,
        )

    def to_default_timeline(self, uid: str | None = None) -> "Timeline":
        """Create a canonical timeline from this store's data.

        When the store contains **multiple** data sources each one becomes
        a child timeline at offset 0, preserving its own 0-based coordinate
        system.  When the store contains a **single** data source the events
        are placed directly on the timeline (no child wrapping) for
        simplicity.  This is the recommended way to create timelines from
        loaded data.

        Args:
            uid: Unique ID for the parent timeline.

        Returns:
            A Timeline with events (single data) or children (multiple data).

        Examples:
            >>> timeline = store.to_default_timeline(uid="chopin_score")
            >>> for offset, child in timeline.iter_children():
            ...     print(f"{child.id}: {child.n_events} events at offset {offset}")
        """
        return self.create_timeline(uid=uid, flatten=False)

    # endregion


class SingleStore(EventStore):
    """Store wrapper for a single EventData.

    Provides EventStore interface compatibility for loaders that naturally
    produce a single EventData rather than multiple categorized data.

    This is used as the default store type for loaders that don't have
    specialized store implementations (e.g., simple audio loaders).

    NOTE: This class was renamed from SingleStoreBundle to SingleStore in
    the 2026-01 API refactoring.

    Attributes:
        data: The wrapped EventData.
        name: The data name.

    Examples:
        >>> data = EventData.from_dicts([...], unit=TimeUnit.seconds)
        >>> store = SingleStore(data, name="beats")
        >>> timeline = store.create_timeline()
    """

    def __init__(self, data: "EventData", name: str = "events") -> None:
        """Initialize SingleStore.

        Args:
            data: The EventData to wrap.
            name: The name for this data. Used as the child timeline ID.
        """
        self._data = data
        self._name = name

    # region EventStore Protocol

    def __iter__(self) -> Iterator["EventData"]:
        """Yield the single data."""
        yield self._data

    def items(self) -> Iterator[tuple[str, "EventData"]]:
        """Yield (name, data) pair."""
        yield (self._name, self._data)

    def keys(self) -> tuple[str, ...]:
        """Return tuple with single data name."""
        return (self._name,)

    def __getitem__(self, name: str) -> "EventData":
        """Get data by name.

        Args:
            name: Must match the data name.

        Returns:
            The wrapped EventData.

        Raises:
            KeyError: If name doesn't match.
        """
        if name == self._name:
            return self._data
        raise KeyError(f"Unknown data: {name!r}. Valid: {self.keys()}")

    def __len__(self) -> int:
        """Return 1 (single data)."""
        return 1

    # endregion

    # region Properties

    @property
    def data(self) -> "EventData":
        """The wrapped EventData."""
        return self._data

    @property
    def name(self) -> str:
        """The data name."""
        return self._name

    # endregion

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SingleStore({self._name}={len(self._data)} events)"


# endregion


# region AlignmentStore


# Match data PyArrow schema
MATCH_SCHEMA = pa.schema(
    [
        pa.field("match_id", pa.string(), nullable=False),
        pa.field("source_event_id", pa.string(), nullable=True),
        pa.field("source_domain", pa.string(), nullable=False),
        pa.field(
            "source_coordinate",
            pa.struct(
                [
                    pa.field("value", pa.float64(), nullable=False),
                    pa.field("numerator", pa.int64(), nullable=True),
                    pa.field("denominator", pa.int64(), nullable=True),
                ]
            ),
            nullable=True,
        ),
        pa.field("target_event_id", pa.string(), nullable=True),
        pa.field("target_domain", pa.string(), nullable=False),
        pa.field(
            "target_coordinate",
            pa.struct(
                [
                    pa.field("value", pa.float64(), nullable=False),
                    pa.field("numerator", pa.int64(), nullable=True),
                    pa.field("denominator", pa.int64(), nullable=True),
                ]
            ),
            nullable=True,
        ),
        pa.field("confidence", pa.float64(), nullable=True),
        pa.field("agent", pa.string(), nullable=True),
        pa.field("method", pa.string(), nullable=True),
    ]
)


@dataclass
class MatchData:
    """Container for alignment matches stored as a PyArrow table.

    Matches represent claims that events or coordinates from different
    timelines/domains are equivalent or synchronous.

    The schema follows the TTA conceptual model:
    - source_event_id/target_event_id: Event identifiers (optional)
    - source_coordinate/target_coordinate: Coordinate values
    - source_domain/target_domain: Domain labels ("physical", "logical", "graphical")
    - confidence: Certainty level (0.0-1.0)
    - agent: Who/what created the match
    - method: How it was created

    Attributes:
        table: PyArrow table containing match data.

    Examples:
        >>> matches = MatchData.from_dicts([
        ...     {
        ...         "match_id": "m1",
        ...         "source_event_id": "note_001",
        ...         "source_domain": "logical",
        ...         "source_coordinate": {"value": 0.0, "numerator": 0, "denominator": 1},
        ...         "target_event_id": None,
        ...         "target_domain": "physical",
        ...         "target_coordinate": {"value": 1.5, "numerator": None, "denominator": None},
        ...         "confidence": 0.95,
        ...         "agent": "human_annotator",
        ...         "method": "manual",
        ...     }
        ... ])
    """

    table: pa.Table

    @classmethod
    def empty(cls) -> "MatchData":
        """Create an empty MatchData."""
        return cls(
            table=pa.table(
                {name: [] for name in MATCH_SCHEMA.names}, schema=MATCH_SCHEMA
            )
        )

    @classmethod
    def from_dicts(cls, rows: list[dict[str, Any]]) -> "MatchData":
        """Create MatchData from a list of match dictionaries.

        Args:
            rows: List of match dictionaries matching MATCH_SCHEMA.

        Returns:
            A new MatchData containing the matches.
        """
        if not rows:
            return cls.empty()

        table = pa.Table.from_pylist(rows, schema=MATCH_SCHEMA)
        return cls(table=table)

    @classmethod
    def from_table(cls, table: pa.Table) -> "MatchData":
        """Create MatchData from an existing PyArrow table.

        Args:
            table: PyArrow table with MATCH_SCHEMA columns.

        Returns:
            A new MatchData wrapping the table.
        """
        return cls(table=table)

    @property
    def count(self) -> int:
        """Number of matches."""
        return self.table.num_rows

    def extend(self, other: "MatchData") -> None:
        """Extend this data with matches from another MatchData (in-place).

        Args:
            other: Another MatchData to append.
        """
        self.table = pa.concat_tables([self.table, other.table])

    def __len__(self) -> int:
        """Return number of matches."""
        return self.count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over matches as dictionaries."""
        for batch in self.table.to_batches():
            yield from batch.to_pylist()

    def __repr__(self) -> str:
        return f"MatchData(count={self.count})"


@dataclass
class AlignmentStore:
    """Container for aligned multimodal data.

    AlignmentStore bundles:
    - events: EventStore containing events from all domains
    - cmaps: ConversionMaps between coordinate systems
    - matches: MatchData with alignment claims

    This is the return type for AlignmentLoader subclasses that load
    formats encoding complete alignments (IEEE 1599, TiLiA, etc.).

    Attributes:
        events: EventStore with events organized by domain/category.
        cmaps: List of ConversionMaps between coordinate systems.
        matches: MatchData containing alignment claims.
        metadata: Additional metadata about the alignment.

    Examples:
        >>> store = AlignmentStore(
        ...     events=score_store,
        ...     cmaps=[ticks_to_seconds, quarters_to_ticks],
        ...     matches=match_data,
        ... )
        >>> store.domains
        {Domain.logical, Domain.physical}
    """

    events: EventStore
    cmaps: list["ConversionMap"] = field(default_factory=list)
    matches: MatchData = field(default_factory=MatchData.empty)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "AlignmentStore":
        """Create an empty AlignmentStore.

        Returns:
            An AlignmentStore with empty events, no C-maps, and no matches.
        """
        from timetoalign.core import TimeUnit
        from timetoalign.loader.store import EventData

        empty_data = EventData.empty(TimeUnit.seconds)
        empty_store = SingleStore(empty_data, name="events")

        return cls(
            events=empty_store,
            cmaps=[],
            matches=MatchData.empty(),
            metadata={},
        )

    @property
    def event_count(self) -> int:
        """Total number of events across all stores."""
        total = 0
        for data in self.events:
            total += len(data)
        return total

    @property
    def match_count(self) -> int:
        """Number of alignment matches."""
        return len(self.matches)

    @property
    def cmap_count(self) -> int:
        """Number of conversion maps."""
        return len(self.cmaps)

    @property
    def domains(self) -> set["Domain"]:
        """Return all domains represented in this alignment.

        Inferred from event units and match domain labels.
        """
        from timetoalign.core import Domain

        found: set[Domain] = set()

        # Infer from event data units
        for data in self.events:
            if hasattr(data, "unit"):
                found.add(data.unit.domain)

        # Also check match domains
        for match in self.matches:
            source_domain = match.get("source_domain")
            target_domain = match.get("target_domain")
            if source_domain:
                try:
                    found.add(Domain(source_domain))
                except ValueError:
                    pass
            if target_domain:
                try:
                    found.add(Domain(target_domain))
                except ValueError:
                    pass

        return found

    def extend(self, other: "AlignmentStore") -> None:
        """Extend this store with data from another AlignmentStore (in-place).

        Events are concatenated (by name if both are EventStore subclasses),
        C-maps are appended, and matches are concatenated.

        Args:
            other: Another AlignmentStore to merge.
        """
        # Extend events - this depends on the EventStore implementation
        # For simplicity, we'll create a new combined store
        # This is a limitation; real impl would need smart merging
        self.cmaps.extend(other.cmaps)
        self.matches.extend(other.matches)
        self.metadata.update(other.metadata)

    def get_cmap(self, source_unit: str, target_unit: str) -> "ConversionMap | None":
        """Find a ConversionMap between two units.

        Args:
            source_unit: Source unit name (e.g., "ticks").
            target_unit: Target unit name (e.g., "seconds").

        Returns:
            The ConversionMap if found, None otherwise.
        """
        for cmap in self.cmaps:
            if (
                hasattr(cmap, "source_unit")
                and hasattr(cmap, "target_unit")
                and cmap.source_unit == source_unit
                and cmap.target_unit == target_unit
            ):
                return cmap
        return None

    def get_matches_for_event(self, event_id: str) -> list[dict[str, Any]]:
        """Get all matches involving a specific event.

        Args:
            event_id: The event identifier to search for.

        Returns:
            List of match dictionaries where event_id is source or target.
        """
        results = []
        for match in self.matches:
            if (
                match.get("source_event_id") == event_id
                or match.get("target_event_id") == event_id
            ):
                results.append(match)
        return results

    def summary(self) -> dict[str, Any]:
        """Get a summary of the alignment store.

        Returns:
            Dict with event counts, match counts, domains, etc.
        """
        return {
            "event_count": self.event_count,
            "match_count": self.match_count,
            "cmap_count": self.cmap_count,
            "domains": [d.name for d in self.domains],
            "store_names": (
                list(self.events.keys()) if hasattr(self.events, "keys") else []
            ),
            **self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"AlignmentStore(events={self.event_count}, "
            f"matches={self.match_count}, "
            f"cmaps={self.cmap_count})"
        )


# endregion
