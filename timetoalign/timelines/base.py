"""Timeline: The central object of TimeToAlign!

A Timeline is a positive coordinate axis defined by an origin (zero) and a
measuring unit. It can hold events (via an EventData) and nested child
timelines (segments) that share the same coordinate type.

Design principles:
- Events stored in PyArrow-based EventData (no flyweight pattern)
- Children stored as direct object references AND as segment events
- Unit validation at add-time prevents coordinate type mismatches
- Locking mechanism prevents modification when embedded as child
"""

from __future__ import annotations

import logging
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Iterator, Literal, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
from typing_extensions import Self

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    Domain,
    IdCoordinate,
    NumberType,
    TimeUnit,
)
from timetoalign.core.timestamp import TimeIntervalStamp, TimeStamp
from timetoalign.loader import EventData
from timetoalign.maps import ConversionMap, InterpolationMap

from .regions import Region

if TYPE_CHECKING:
    from timetoalign.core.enums import ColumnNaming
    from timetoalign.display.ascii import Diagram

    from .flow import FlowMap
    from .types import SegmentLine

module_logger = logging.getLogger(__name__)

# Module-level counter for unique ID generation
_TIMELINE_COUNTER: dict[str, int] = {}

# region Constants

# Event type name for segment events in the EventData
SEGMENT_EVENT_TYPE = "Segment"

# Traversal order options for iterating children
TraversalOrder = Literal["sorted", "depth_first", "breadth_first"]

# Type alias for flexible conversion_maps parameter in get_timestamps
# Accepts: True (all), single cmap/str, or iterable of cmaps/strs
ConversionMapsSpec = (
    bool
    | str
    | TimeUnit
    | ConversionMap[Any]
    | list[ConversionMap[Any] | str | TimeUnit]
    | None
)

# endregion


class Timeline:
    """A positive coordinate axis with events and nested child timelines.

    A Timeline represents a temporal dimension in one of three domains
    (Logical, Physical, Graphical) with either continuous or discrete
    coordinates. It stores events in an EventData and can contain
    nested child timelines (segments) at specified offsets.

    **Intended usage:** This base class provides the full Timeline API but
    does not enforce domain or modality constraints. For typical usage,
    prefer one of the six concrete subclasses or the ``create_timeline()``
    factory function:

    - ``ContinuousLogicalTimeline`` -- beats, quarters, measures (Fraction)
    - ``DiscreteLogicalTimeline`` -- ticks (int)
    - ``ContinuousPhysicalTimeline`` -- seconds, ms, minutes (float)
    - ``DiscretePhysicalTimeline`` -- samples, frames (int)
    - ``ContinuousGraphicalTimeline`` -- cm, inches, points (float)
    - ``DiscreteGraphicalTimeline`` -- pixels (int)

    These subclasses restrict allowed units and number types to prevent
    accidental cross-domain errors and provide sensible defaults.

    Direct instantiation of ``Timeline`` is appropriate for internal use,
    generic algorithms that operate across domains, or advanced scenarios
    where domain constraints are intentionally relaxed.

    If you have a ``Timeline`` instance and need the appropriate typed
    subclass, use :meth:`to_typed`.

    Attributes:
        id: Unique identifier for this timeline.
        unit: The time unit for coordinates (e.g., seconds, quarters, pixels).
        number_type: The numeric type for coordinates (int, float, Fraction).
        domain: The temporal domain (derived from unit).
        origin: The start coordinate (always 0).
        length: The end coordinate.
        is_locked: Whether the timeline can be modified.
        is_discrete: Whether the timeline uses discrete coordinates.
        is_continuous: Whether the timeline uses continuous coordinates.

    Examples:
        >>> # Preferred: use concrete subclasses
        >>> from timetoalign.timelines import ContinuousPhysicalTimeline
        >>> audio = ContinuousPhysicalTimeline(length=180.0)

        >>> # Or use the factory to auto-select the right subclass
        >>> from timetoalign.timelines import create_timeline
        >>> tl = create_timeline(loader)

        >>> # Direct base class (internal/advanced use)
        >>> from timetoalign.core import TimeUnit
        >>> tl = Timeline(length=100, unit=TimeUnit.seconds)
    """

    # region Class Variables

    # Subclasses can override these to restrict valid units/number_types
    _allowed_units: ClassVar[frozenset[TimeUnit] | None] = None
    _allowed_number_types: ClassVar[tuple[NumberType, ...] | None] = None

    # Default values for unit and number_type (subclasses override)
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    _default_number_type: ClassVar[NumberType] = NumberType.float

    # EventData class to use (subclasses can override for domain-specific data)
    _event_data_class: ClassVar[type[EventData]] = EventData

    # endregion

    # region Initialization

    def __init__(
        self,
        length: CoordinateValue = 0,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        id_prefix: str = "tl",
        uid: str | None = None,
        name: str | None = None,
        locked: bool = False,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Timeline.

        Args:
            length: The length (end coordinate) of the timeline. Default 0.
            unit: The time unit for coordinates. Defaults to class default.
            number_type: The number type for coordinates. Defaults to class default.
            id_prefix: Prefix for auto-generated ID. Default "tl".
            uid: Explicit unique identifier. Overrides auto-generation.
            name: Human-readable name for display (distinct from uid).
            locked: If True, timeline cannot expand. Default False.
            meta: Additional metadata dictionary.

        Raises:
            ValueError: If unit or number_type is not allowed for this class.
            TypeError: If length is not a valid coordinate value.
        """
        # Resolve unit
        if unit is None:
            unit = self._default_unit
        elif isinstance(unit, str):
            unit = TimeUnit(unit)
        self._validate_unit(unit)
        self._unit = unit

        # Resolve number_type
        if number_type is None:
            number_type = self._default_number_type
        elif isinstance(number_type, str):
            number_type = NumberType(number_type)
        self._validate_number_type(number_type)
        self._number_type = number_type

        # Generate or use provided ID
        if uid is not None:
            self._id = uid
        else:
            # Use module-level counter for truly unique IDs
            if id_prefix not in _TIMELINE_COUNTER:
                _TIMELINE_COUNTER[id_prefix] = 0
            _TIMELINE_COUNTER[id_prefix] += 1
            self._id = f"{id_prefix}:{_TIMELINE_COUNTER[id_prefix]}"

        # Initialize length as Coordinate
        self._length = self._make_coordinate(length)

        # State
        self._locked = locked
        self._name = name
        self._meta = dict(meta) if meta else {}

        # Event storage
        self._events = self._event_data_class.empty(self._unit, self._number_type)

        # Child timeline storage
        self._children: dict[str, Timeline] = {}
        self._child_offsets: dict[str, Coordinate] = {}

        # Conversion maps
        self._conversion_maps: dict[str, ConversionMap[Any]] = {}

        # Maps TimeUnit -> map for unit-based conversion via C-Maps.
        # Stores InterpolationMap (for TableMaps) or ConversionMap (for
        # analytical maps like ScalarMap, LinearMap) so that *any* C-Map
        # with a target_unit is available in the TimeStamp system.
        self._unit_maps: dict[TimeUnit, InterpolationMap | ConversionMap[Any]] = {}

        # Region storage (named TimeIntervals)
        # From TTA manuscript: "A Region is a named part of a timeline that is
        # defined by a TimeInterval. Regions are useful for referring to parts
        # of a timeline by name."
        self._regions: dict[str, Region] = {}

        # FlowMap storage (coordinate transformations for flow control)
        # Timelines store FlowMaps (not FlowControllers).
        # FlowMaps enable unfold/fold coordinate conversion for timelines
        # that have flow control (repeats, jumps, etc.).
        self._flow_maps: dict[str, "FlowMap"] = {}

        # Logger
        self._logger = module_logger.getChild(self._id)

    # endregion

    # region Class Methods - Validation

    @classmethod
    def _validate_unit(cls, unit: TimeUnit) -> None:
        """Validate that unit is allowed for this Timeline class.

        Args:
            unit: The unit to validate.

        Raises:
            ValueError: If unit is not in _allowed_units.
        """
        if cls._allowed_units is not None and unit not in cls._allowed_units:
            allowed = ", ".join(str(u) for u in cls._allowed_units)
            raise ValueError(
                f"{cls.__name__} does not allow unit '{unit}'. "
                f"Allowed units: {allowed}"
            )

    @classmethod
    def _validate_number_type(cls, number_type: NumberType) -> None:
        """Validate that number_type is allowed for this Timeline class.

        Args:
            number_type: The number type to validate.

        Raises:
            ValueError: If number_type is not in _allowed_number_types.
        """
        if (
            cls._allowed_number_types is not None
            and number_type not in cls._allowed_number_types
        ):
            allowed = ", ".join(str(nt) for nt in cls._allowed_number_types)
            raise ValueError(
                f"{cls.__name__} does not allow number_type '{number_type}'. "
                f"Allowed types: {allowed}"
            )

    # endregion

    # region Class Methods - Construction

    @classmethod
    def resolve_subclass(
        cls,
        unit: TimeUnit | str,
        number_type: NumberType | str | None = None,
    ) -> type[Timeline]:
        """Return the canonical Timeline subclass for a unit/number_type pair.

        Inspects all subclasses and selects the one whose
        ``_allowed_units`` includes *unit*.  Among candidates the selection
        prefers, in order:

        1. A class whose ``_default_number_type`` matches *number_type*
           (when supplied).
        2. The class with the **smallest** ``_allowed_units`` set (most
           specific domain).

        This ensures the six concrete types from ``timetoalign.timelines.types``
        are returned rather than further-derived specialisations like
        ``BeatGrid``.

        Falls back to the base ``Timeline`` if no subclass claims the unit.

        Args:
            unit: The time unit to look up.
            number_type: Optional number type for disambiguation
                (e.g. ``NumberType.fraction`` selects ``ContinuousLogicalTimeline``
                over ``DiscreteLogicalTimeline``).

        Returns:
            The canonical Timeline subclass that accepts *unit*.

        Examples:
            >>> Timeline.resolve_subclass(TimeUnit.quarters, NumberType.fraction)
            <class '...ContinuousLogicalTimeline'>
            >>> Timeline.resolve_subclass(TimeUnit.pixels)
            <class '...DiscreteGraphicalTimeline'>
        """
        if isinstance(unit, str):
            unit = TimeUnit(unit)
        if isinstance(number_type, str):
            number_type = NumberType(number_type)

        def _all_subclasses(base: type[Timeline]) -> Iterator[type[Timeline]]:
            """Yield *base* and all its descendants (breadth-first)."""
            for sub in base.__subclasses__():
                yield sub
                yield from _all_subclasses(sub)

        candidates: list[type[Timeline]] = []
        for sub in _all_subclasses(Timeline):
            allowed = getattr(sub, "_allowed_units", None)
            if allowed is not None and unit in allowed:
                candidates.append(sub)

        if not candidates:
            return Timeline

        # Sort by allowed-units size (smallest = most specific domain)
        candidates.sort(key=lambda c: len(getattr(c, "_allowed_units", frozenset())))

        # If number_type is given, prefer a candidate whose default matches
        if number_type is not None:
            for cand in candidates:
                if getattr(cand, "_default_number_type", None) == number_type:
                    return cand

        # Return the most specific candidate (smallest allowed-units set)
        return candidates[0]

    @classmethod
    def empty(
        cls,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create an empty Timeline with length 0.

        Args:
            unit: The time unit. Defaults to class default.
            number_type: The number type. Defaults to class default.
            **kwargs: Additional arguments passed to __init__.

        Returns:
            A new empty Timeline.
        """
        return cls(length=0, unit=unit, number_type=number_type, **kwargs)

    @classmethod
    def from_events(
        cls,
        rows: list[dict[str, Any]],
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create a Timeline from event dictionaries.

        The timeline length is automatically set to accommodate all events.

        Args:
            rows: List of event dictionaries with keys:
                - id: unique identifier
                - temporal_type: "instant" or "interval"
                - event_type: class name (e.g., "Note", "Beat")
                - instant: coordinate (for instant events)
                - start, end: coordinates (for interval events)
            unit: The time unit. Defaults to class default.
            number_type: The number type. Defaults to class default.
            **kwargs: Additional arguments passed to __init__.

        Returns:
            A new Timeline containing the events.
        """
        if not rows:
            return cls.empty(unit=unit, number_type=number_type, **kwargs)

        # Calculate max coordinate to determine length
        max_coord = 0.0
        for row in rows:
            if row.get("instant") is not None:
                max_coord = max(max_coord, float(row["instant"]))
            if row.get("end") is not None:
                max_coord = max(max_coord, float(row["end"]))
            elif row.get("start") is not None and row.get("duration") is not None:
                max_coord = max(max_coord, float(row["start"]) + float(row["duration"]))

        timeline = cls(length=max_coord, unit=unit, number_type=number_type, **kwargs)
        timeline._add_events_unchecked(rows)
        return timeline

    @classmethod
    def from_event_data(
        cls,
        data: EventData,
        **kwargs: Any,
    ) -> Self:
        """Create a Timeline from an existing EventData.

        Args:
            data: The EventData containing events.
            **kwargs: Additional arguments passed to __init__ (except unit/number_type).

        Returns:
            A new Timeline wrapping the EventData.
        """
        coord_range = data.coordinate_range()
        length = coord_range[1] if coord_range else 0

        timeline = cls(
            length=length,
            unit=data.unit,
            number_type=data.number_type,
            **kwargs,
        )
        timeline._events = data
        return timeline

    # endregion

    # region Properties - Identity

    @property
    def id(self) -> str:
        """Unique identifier for this timeline."""
        return self._id

    @property
    def name(self) -> str:
        """Human-readable name for display.

        Returns the explicit name if set, otherwise falls back to the ID.
        Use this for user-facing displays (e.g., timestamp column headers).
        """
        return self._name if self._name is not None else self._id

    @name.setter
    def name(self, value: str | None) -> None:
        """Set the human-readable name."""
        self._name = value

    @property
    def class_name(self) -> str:
        """The class name of this timeline."""
        return self.__class__.__name__

    # endregion

    # region Properties - Coordinate Type

    @property
    def unit(self) -> TimeUnit:
        """The time unit for coordinates."""
        return self._unit

    @property
    def number_type(self) -> NumberType:
        """The number type for coordinates."""
        return self._number_type

    @property
    def domain(self) -> Domain:
        """The temporal domain (derived from unit)."""
        return self._unit.domain

    @property
    def is_discrete(self) -> bool:
        """Whether this timeline uses discrete (integer) coordinates.

        Derived from the unit's inherent discreteness. Discrete timelines
        measure time in countable units (ticks, samples, frames, pixels).

        Returns:
            True if the timeline's unit is inherently discrete.

        Examples:
            >>> DiscreteLogicalTimeline(length=1920).is_discrete
            True
            >>> ContinuousPhysicalTimeline(length=10.0).is_discrete
            False
        """
        return self._unit.is_discrete

    @property
    def is_continuous(self) -> bool:
        """Whether this timeline uses continuous (real-valued) coordinates.

        The logical complement of :attr:`is_discrete`. Continuous timelines
        measure time in units that allow arbitrary precision (seconds,
        quarters, centimeters, etc.).

        Returns:
            True if the timeline's unit is not inherently discrete.

        Examples:
            >>> ContinuousLogicalTimeline(length=Fraction(4, 1)).is_continuous
            True
            >>> DiscreteGraphicalTimeline(length=1920).is_continuous
            False
        """
        return not self._unit.is_discrete

    # endregion

    # region Properties - Boundaries

    @property
    def origin(self) -> Coordinate:
        """The start coordinate (always 0)."""
        return self._make_coordinate(0)

    @property
    def length(self) -> Coordinate:
        """The end coordinate (length of the timeline)."""
        return self._length

    @length.setter
    def length(self, value: CoordinateValue | Coordinate) -> None:
        """Set the timeline length.

        Args:
            value: New length value.

        Raises:
            RuntimeError: If timeline is locked.
            ValueError: If new length is less than current content.
        """
        self._check_not_locked("set length")

        if isinstance(value, Coordinate):
            if value.unit != self._unit:
                raise ValueError(
                    f"Cannot set length with unit '{value.unit}', "
                    f"expected '{self._unit}'"
                )
            new_length = value
        else:
            new_length = self._make_coordinate(value)

        # Check that new length accommodates all content
        max_content = self._get_max_content_coordinate()
        if new_length.value < max_content:
            raise ValueError(
                f"Cannot reduce length to {new_length.value}: "
                f"content extends to {max_content}"
            )

        self._length = new_length

    @property
    def start(self) -> Coordinate:
        """Alias for origin."""
        return self.origin

    @property
    def end(self) -> Coordinate:
        """Alias for length."""
        return self._length

    # endregion

    # region Properties - State

    @property
    def is_locked(self) -> bool:
        """Whether this timeline is locked (cannot expand)."""
        return self._locked

    @property
    def meta(self) -> dict[str, Any]:
        """Metadata dictionary."""
        return dict(self._meta)

    # endregion

    # region Properties - Counts

    @property
    def n_events(self) -> int:
        """Number of events (excluding segment events)."""
        # Filter out segment events from count
        non_segment = self._events.filter(event_type=SEGMENT_EVENT_TYPE)
        return len(self._events) - len(non_segment)

    @property
    def n_children(self) -> int:
        """Number of direct child timelines."""
        return len(self._children)

    @property
    def n_conversion_maps(self) -> int:
        """Number of attached conversion maps."""
        return len(self._conversion_maps)

    @property
    def events(self) -> EventData:
        """The underlying EventData (read-only access)."""
        return self._events

    # endregion

    # region Coordinate Factory

    def _make_coordinate(self, value: CoordinateValue | Coordinate) -> Coordinate:
        """Create a Coordinate in this timeline's unit.

        Args:
            value: The coordinate value or an existing Coordinate.

        Returns:
            A Coordinate with this timeline's unit.

        Raises:
            ValueError: If value is a Coordinate with different unit.
        """
        if isinstance(value, Coordinate):
            if value.unit != self._unit:
                raise ValueError(
                    f"Coordinate unit mismatch: got '{value.unit}', "
                    f"expected '{self._unit}'"
                )
            return value
        return Coordinate(value, self._unit)

    def make_coordinate(self, value: CoordinateValue) -> Coordinate:
        """Create a Coordinate in this timeline's unit.

        Public API for creating coordinates compatible with this timeline.

        Args:
            value: The numeric value for the coordinate.

        Returns:
            A Coordinate with this timeline's unit.
        """
        return Coordinate(value, self._unit)

    # endregion

    # region Lock Management

    def _check_not_locked(self, operation: str) -> None:
        """Raise RuntimeError if timeline is locked.

        Args:
            operation: Description of the attempted operation.

        Raises:
            RuntimeError: If timeline is locked.
        """
        if self._locked:
            raise RuntimeError(
                f"Cannot {operation} on locked timeline '{self._id}'. "
                "Timelines are locked when embedded as children."
            )

    def _ensure_capacity(
        self,
        required_end: CoordinateValue,
        allow_expansion: bool = False,
    ) -> None:
        """Ensure timeline is long enough, expanding if permitted.

        Args:
            required_end: The coordinate that must be within bounds.
            allow_expansion: If True, override lock to expand.

        Raises:
            ValueError: If expansion is needed but not permitted.
        """
        required = (
            required_end.value if isinstance(required_end, Coordinate) else required_end
        )

        if required <= self._length.value:
            return

        if self._locked and not allow_expansion:
            raise ValueError(
                f"Adding content ending at {required} exceeds timeline length "
                f"{self._length.value}. Timeline is locked. "
                "Use allow_expansion=True to override."
            )

        # Expand (temporarily unlock if needed)
        was_locked = self._locked
        self._locked = False
        self._length = self._make_coordinate(required)
        self._locked = was_locked

    # endregion

    # region Event Management

    def add_events(
        self,
        rows: list[dict[str, Any]],
        allow_expansion: bool = False,
    ) -> None:
        """Add events to the timeline.

        Only ``event_type`` and a coordinate are strictly required per dict.
        Missing fields are filled in automatically:

        - **id**: auto-generated (``e000001``, ``e000002``, ...).
        - **temporal_type**: inferred from keys -- ``"interval"`` when both
          ``start`` and ``end`` (or ``duration``) are present, ``"instant"``
          otherwise.

        Args:
            rows: List of event dictionaries. Required keys:
                - event_type: class name (e.g. ``"Beat"``, ``"Note"``)
                - instant: coordinate (for instant events), **or**
                - start, end: coordinates (for interval events)
            allow_expansion: If True, expand timeline if events exceed length.

        Raises:
            ValueError: If events exceed length and expansion not allowed.
            RuntimeError: If timeline is locked and expansion not allowed.

        Examples:
            >>> tl.add_events([
            ...     {"event_type": "Beat", "instant": 0.0},
            ...     {"event_type": "Note", "start": 0.0, "end": 0.5},
            ... ])
        """
        if not rows:
            return

        # Validate and find max coordinate
        max_coord = 0.0
        for row in rows:
            coord = self._get_event_end_coordinate(row)
            max_coord = max(max_coord, coord)

        # Ensure capacity
        self._ensure_capacity(max_coord, allow_expansion)

        # Add events
        self._add_events_unchecked(rows)

    def _add_events_unchecked(self, rows: list[dict[str, Any]]) -> None:
        """Add events without validation (internal use).

        Uses the concrete type of ``self._events`` to create new EventData,
        ensuring schema compatibility when the events store is a subclass
        (e.g., MeasureData) that was assigned directly via
        ``EventData.create_timeline()``.

        Args:
            rows: Event dictionaries to add.
        """
        if not rows:
            return

        data_class = type(self._events)
        new_data = data_class.from_dicts(rows, self._unit, self._number_type)
        self._events.extend(new_data)

    @staticmethod
    def _coord_to_float(value: Any) -> float:
        """Convert a coordinate value to float.

        Handles both raw numeric values and coordinate struct dicts
        (e.g., ``{"value": 4.5, "numerator": 9, "denominator": 2}``)
        as produced by MeasureData and other loader stores.

        Args:
            value: A numeric value or a dict with a ``"value"`` key.

        Returns:
            The coordinate as a float.
        """
        if isinstance(value, dict):
            return float(value["value"])
        return float(value)

    def _get_event_end_coordinate(self, row: dict[str, Any]) -> float:
        """Extract the end coordinate from an event dict.

        Args:
            row: Event dictionary. Coordinate fields may be raw floats
                or struct dicts (``{"value": ..., ...}``).

        Returns:
            The end coordinate as float.
        """
        if row.get("instant") is not None:
            return self._coord_to_float(row["instant"])
        if row.get("end") is not None:
            return self._coord_to_float(row["end"])
        if row.get("start") is not None and row.get("duration") is not None:
            return self._coord_to_float(row["start"]) + self._coord_to_float(
                row["duration"]
            )
        if row.get("start") is not None:
            return self._coord_to_float(row["start"])
        return 0.0

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Look up a single event by its ``id`` field.

        Searches the timeline's event store for an event whose ``id``
        column matches *event_id*. Returns the first matching row as a
        dictionary, or ``None`` if no event with that ID exists.

        This is a convenience wrapper around a PyArrow filter on the
        ``id`` column and is intended for point lookups (e.g. verifying
        that a score note exists on a shared timeline). For bulk queries,
        use `get_events` or `get_events_at` instead.

        Args:
            event_id: The event identifier to search for.

        Returns:
            A dictionary representing the event row, or ``None`` if not
            found.

        Examples:
            >>> event = timeline.get_event("n1")
            >>> event["id"]
            'n1'
            >>> timeline.get_event("nonexistent") is None
            True
        """
        table = self._events.table
        mask = pc.equal(table.column("id"), event_id)
        filtered = table.filter(mask)
        if filtered.num_rows == 0:
            return None
        return filtered.to_pylist()[0]

    def get_events(
        self,
        temporal_type: Literal["instant", "interval"] | None = None,
        event_type: str | None = None,
        include_segments: bool = False,
        min_coord: float | None = None,
        max_coord: float | None = None,
    ) -> EventData:
        """Filter and retrieve events.

        Args:
            temporal_type: Filter by "instant" or "interval".
            event_type: Filter by event type name.
            include_segments: If True, include segment events. Default False.
            min_coord: Minimum coordinate (inclusive).
            max_coord: Maximum coordinate (exclusive).

        Returns:
            A filtered EventData.
        """
        result = self._events

        if temporal_type is not None:
            result = result.filter(temporal_type=temporal_type)

        if event_type is not None:
            result = result.filter(event_type=event_type)

        if not include_segments:
            # Exclude segment events by getting all and filtering
            # Note: This could be optimized with a NOT filter
            segment_data = result.filter(event_type=SEGMENT_EVENT_TYPE)
            if len(segment_data) > 0:
                # Filter by getting non-segment events
                result = EventData.from_dicts(
                    [
                        row
                        for row in result
                        if row.get("event_type") != SEGMENT_EVENT_TYPE
                    ],
                    self._unit,
                    self._number_type,
                )

        if min_coord is not None or max_coord is not None:
            result = result.filter(min_coord=min_coord, max_coord=max_coord)

        return result

    def query_events_hierarchical(
        self,
        coord_range: tuple[float, float] | None = None,
        event_types: set[str] | None = None,
        include_children: bool = True,
        recursion_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query events across the timeline hierarchy.

        Returns events from this timeline and all children, with coordinates
        adjusted to the root timeline's coordinate system.

        From TTA manuscript: Hierarchical timelines should support querying
        events across the entire hierarchy with root-relative coordinates.

        Args:
            coord_range: Optional (min, max) range filter in ROOT coordinates.
            event_types: Optional set of event types to include.
            include_children: If True, include events from children.
            recursion_limit: Maximum depth for child traversal. None = unlimited.

        Returns:
            List of event dictionaries, each augmented with:
            - "source_timeline": ID of the timeline containing the event
            - "root_start": Root-relative start coordinate
            - "root_end": Root-relative end coordinate (for intervals)

        Examples:
            >>> # Get all notes in a range
            >>> events = score.query_events_hierarchical(
            ...     coord_range=(16.0, 40.0),
            ...     event_types={"Note"},
            ... )
            >>> len(events)
            127
        """
        return self._query_events_recursive(
            coord_range=coord_range,
            event_types=event_types,
            include_children=include_children,
            recursion_limit=recursion_limit,
            root_offset=0.0,
        )

    def _query_events_recursive(
        self,
        coord_range: tuple[float, float] | None,
        event_types: set[str] | None,
        include_children: bool,
        recursion_limit: int | None,
        root_offset: float,
    ) -> list[dict[str, Any]]:
        """Internal recursive helper for query_events_hierarchical."""
        result: list[dict[str, Any]] = []

        # Get this timeline's events (excluding segment events)
        local_events = self.get_events(include_segments=False)

        for event in local_events:
            # Filter by event type if specified
            if event_types and event.get("event_type") not in event_types:
                continue

            # Extract coordinates
            start_val = self._extract_coord_value(event, "start", "instant")
            end_val = self._extract_coord_value(event, "end")

            # Calculate root-relative coordinates
            root_start = start_val + root_offset if start_val is not None else None
            root_end = end_val + root_offset if end_val is not None else None

            # Filter by coordinate range (using root_start)
            if coord_range and root_start is not None:
                if root_start < coord_range[0] or root_start >= coord_range[1]:
                    continue

            # Create augmented event
            augmented = dict(event)
            augmented["source_timeline"] = self._id
            augmented["root_start"] = root_start
            augmented["root_end"] = root_end
            result.append(augmented)

        # Recurse into children
        if include_children and (recursion_limit is None or recursion_limit > 0):
            next_limit = None if recursion_limit is None else recursion_limit - 1

            for child_id, child in self._children.items():
                child_offset = float(self._child_offsets[child_id].value)
                combined_offset = root_offset + child_offset

                child_events = child._query_events_recursive(
                    coord_range=coord_range,
                    event_types=event_types,
                    include_children=True,
                    recursion_limit=next_limit,
                    root_offset=combined_offset,
                )
                result.extend(child_events)

        return result

    def _extract_coord_value(
        self,
        event: dict[str, Any],
        *keys: str,
    ) -> float | None:
        """Extract coordinate value from event, trying multiple keys.

        Args:
            event: Event dictionary.
            *keys: Keys to try in order (e.g., "start", "instant").

        Returns:
            The coordinate value as float, or None if not found.
        """
        for key in keys:
            val = event.get(key)
            if val is not None:
                if isinstance(val, dict) and "value" in val:
                    return float(val["value"])
                return float(val)
        return None

    def get_events_at(
        self,
        coord: CoordinateValue | Coordinate,
        tolerance: float = 0.0,
        include_children: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get all events active at a specific coordinate.

        Returns events from this timeline and all children that are
        active (containing or at) the specified coordinate.

        For instant events, an event is "at" the coordinate if its instant
        is within tolerance of the query coordinate.

        For interval events, an event is "active" if the coordinate falls
        within [start, end).

        Args:
            coord: Coordinate to query (in this timeline's unit).
            tolerance: Tolerance for instant event matching (default 0).
            include_children: If True, include events from children.

        Returns:
            Dict mapping timeline_id to list of events active at that coordinate.
            Child events have coordinates in their local coordinate system.

        Examples:
            >>> events = score.get_events_at(50.0)
            >>> events["score:1"]  # Events in root at coord 50
            [{"id": "n1", "event_type": "Note", ...}]
            >>> events["measure_5"]  # Events in measure 5
            [...]
        """
        coord_val = float(coord.value if isinstance(coord, Coordinate) else coord)
        result: dict[str, list[dict[str, Any]]] = {}

        # Get events from this timeline
        local_events = self._get_events_at_local(coord_val, tolerance)
        if local_events:
            result[self._id] = local_events

        # Check children
        if include_children:
            ts = self.get_timestamp(coord_val)

            for child_id in self._children.keys():
                child_coord = ts.get(child_id)
                if child_coord is not None and child_coord >= 0:
                    child = self._children[child_id]
                    if child_coord <= child.length.value:
                        # Recursively get events in child
                        child_result = child.get_events_at(
                            child_coord,
                            tolerance=tolerance,
                            include_children=True,
                        )
                        result.update(child_result)

        return result

    def _get_events_at_local(
        self,
        coord: float,
        tolerance: float,
    ) -> list[dict[str, Any]]:
        """Get events at a coordinate in this timeline (local, no children)."""
        result = []

        for event in self.get_events(include_segments=False):
            temporal_type = event.get("temporal_type")

            if temporal_type == "instant":
                instant_val = self._extract_coord_value(event, "instant", "start")
                if instant_val is not None:
                    if abs(instant_val - coord) <= tolerance:
                        result.append(dict(event))

            elif temporal_type == "interval":
                start_val = self._extract_coord_value(event, "start")
                end_val = self._extract_coord_value(event, "end")

                if start_val is not None and end_val is not None:
                    # Left-inclusive, right-exclusive: [start, end)
                    if start_val <= coord < end_val:
                        result.append(dict(event))

        return result

    # endregion

    # region Child Management

    def validate_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
    ) -> None:
        """Validate that a timeline can be added as a child.

        From the TTA manuscript (Section 3.4 - Nested Timelines):
        "A timeline can accommodate not only events but also other timelines,
        called Children, as long as they use the same measuring unit."

        For cross-domain relationships (e.g., physical to logical), use
        TimelineGroup instead of parent-child nesting.

        Args:
            child: The timeline to validate.
            offset: The proposed start coordinate.

        Raises:
            TypeError: If child is not a Timeline.
            ValueError: If units don't match or child already has a parent.
        """
        if not isinstance(child, Timeline):
            raise TypeError(f"Child must be a Timeline, got {type(child).__name__}")

        if child.unit != self._unit:
            raise ValueError(
                f"Child unit '{child.unit}' does not match "
                f"parent unit '{self._unit}'. "
                f"Per TTA specification, Children must share the parent's unit. "
                f"For cross-domain relationships, use TimelineGroup instead."
            )

        if child.id in self._children:
            raise ValueError(f"Child '{child.id}' is already a child of this timeline")

        # Validate offset
        offset_coord = self._make_coordinate(offset)
        if offset_coord.value < 0:
            raise ValueError(f"Offset cannot be negative: {offset_coord.value}")

    def _convert_child_to_parent_unit(
        self,
        child: Timeline,
        use_conversion_map: ConversionMapsSpec,
    ) -> Timeline:
        """Convert a child timeline to this timeline's unit via a C-Map.

        The conversion map is resolved from the parent's attached C-Maps.
        We find a map whose ``target_unit`` matches the child's unit, invert
        it, and use it to derive a copy of the child in the parent's unit.

        The derived copy receives the ID ``{child.id}[{parent.unit}]`` and
        retains all events with converted coordinates.

        Args:
            child: The child timeline to convert.
            use_conversion_map: Flexible specification for which C-Map to use.
                Accepts the same formats as the ``conversion_maps`` parameter
                in timestamp functions:
                - ``True``: Auto-select a C-Map whose target unit matches
                  the child's unit.
                - ``str``: Look up by C-Map ID or target unit name.
                - ``TimeUnit``: Find by target unit.
                - ``ConversionMap``: Use directly (must map parent unit to
                  child unit so that its inverse converts child to parent).

        Returns:
            A new Timeline in the parent's unit with converted events.

        Raises:
            ValueError: If no suitable C-Map can be found or inverted.
        """
        # Resolve the conversion map on the parent
        if use_conversion_map is True:
            # Auto-select: find a parent C-Map whose target_unit matches child's unit
            cmap = self.get_conversion_map(child.unit)
            if cmap is None:
                raise ValueError(
                    f"Cannot auto-select conversion map: no C-Map from "
                    f"'{self._unit}' to '{child.unit}' attached to parent "
                    f"'{self._id}'. Attach a C-Map first or specify one "
                    f"explicitly via use_conversion_map."
                )
        elif isinstance(use_conversion_map, ConversionMap):
            cmap = use_conversion_map
        else:
            # Use _resolve_conversion_maps for str / TimeUnit / list
            resolved = self._resolve_conversion_maps(use_conversion_map)
            # Find the one whose target_unit matches child's unit
            matching = [m for m in resolved if m.target_unit == child.unit]
            if not matching:
                raise ValueError(
                    f"None of the resolved conversion maps target the child's "
                    f"unit '{child.unit}'. Resolved maps target: "
                    f"{[m.target_unit for m in resolved]}"
                )
            cmap = matching[0]

        # Invert: we need child_unit -> parent_unit
        if not cmap.is_invertible:
            raise ValueError(
                f"C-Map '{cmap.id}' ({cmap.source_unit} -> {cmap.target_unit}) "
                f"is not invertible. Cannot convert child from "
                f"'{child.unit}' to '{self._unit}'."
            )
        inverse_cmap = cmap.inverse()

        # Temporarily add the inverse map to the child so derive() can use it
        child_had_map = child.get_conversion_map(self._unit) is not None
        if not child_had_map:
            child.add_conversion_map(inverse_cmap)

        try:
            derived = child.derive(
                self._unit,
                copy_events=True,
            )
        finally:
            # Clean up: remove the temporarily added map if we added it
            if not child_had_map and inverse_cmap.id in child._conversion_maps:
                del child._conversion_maps[inverse_cmap.id]
                # Also clean up _unit_maps
                if self._unit in child._unit_maps:
                    del child._unit_maps[self._unit]

        # Assign a clear ID and name linking back to the original
        derived._id = f"{child.id}[{self._unit}]"
        derived._name = f"{child.name or child.id} [{self._unit}]"

        self._logger.debug(
            f"Converted child '{child.id}' ({child.unit}) to "
            f"'{derived.id}' ({self._unit}) via inverse of '{cmap.id}'"
        )

        return derived

    def add_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
        allow_expansion: bool = False,
        use_conversion_map: ConversionMapsSpec = None,
    ) -> None:
        """Embed a child timeline at the specified offset.

        The child timeline will be locked after being added.
        Parent-child coordinate conversion uses exact offset arithmetic.

        From the TTA manuscript (Section 3.4 - Nested Timelines):
        "A timeline can accommodate not only events but also other timelines,
        called Children, as long as they use the same measuring unit."

        When the child uses a different unit than the parent, set
        ``use_conversion_map`` to automatically convert the child to the
        parent's unit via a C-Map. The parent must have a C-Map whose
        ``target_unit`` matches the child's unit, so that inverting it yields
        the ``child_unit -> parent_unit`` conversion. The child's events are
        copied with converted coordinates; the original child is NOT modified.

        The converted child receives the ID ``{child.id}[{parent.unit}]``.

        Args:
            child: The timeline to embed.
            offset: The start coordinate on this timeline, in the **parent's**
                unit. When ``use_conversion_map`` is set, the offset must
                already be expressed in the parent's unit (e.g. samples).
            allow_expansion: If True, expand this timeline if needed.
            use_conversion_map: Conversion map specification for unit
                conversion. Accepts the same formats as the
                ``conversion_maps`` parameter in timestamp functions:
                - ``None`` (default): No conversion; units must match.
                - ``True``: Auto-select a parent C-Map whose target unit
                  matches the child's unit.
                - ``str``: Look up by C-Map ID or target unit name.
                - ``TimeUnit``: Find by target unit.
                - ``ConversionMap``: Use directly.

        Raises:
            TypeError: If child is not a Timeline.
            ValueError: If units don't match (and no conversion map given)
                or would exceed bounds.
            RuntimeError: If this timeline is locked.
        """
        # Convert child's unit if a conversion map is specified
        if use_conversion_map is not None and child.unit != self._unit:
            child = self._convert_child_to_parent_unit(child, use_conversion_map)

        self.validate_child(child, offset)

        offset_coord = self._make_coordinate(offset)
        child_end = offset_coord.value + child.length.value

        # Ensure capacity
        self._ensure_capacity(child_end, allow_expansion)

        # Store child reference
        self._children[child.id] = child
        self._child_offsets[child.id] = offset_coord

        # Lock the child
        child._locked = True

        # Add segment event to EventData
        segment_event = {
            "id": child.id,
            "name": child.id,
            "temporal_type": "interval",
            "event_type": SEGMENT_EVENT_TYPE,
            "start": offset_coord.value,
            "end": child_end,
            "duration": child.length.value,
        }
        self._add_events_unchecked([segment_event])

        self._logger.debug(f"Added child '{child.id}' at offset {offset_coord.value}")

    def create_child(
        self,
        length: CoordinateValue | Coordinate,
        offset: CoordinateValue | Coordinate,
        uid: str | None = None,
        name: str | None = None,
        allow_expansion: bool = False,
    ) -> "Timeline":
        """Create a new child timeline and embed it at the specified offset.

        Convenience method that creates a new timeline with the same unit as the
        parent and immediately adds it as a child. This is equivalent to:

            child = Timeline(length=length, unit=parent.unit, uid=uid, name=name)
            parent.add_child(child, offset=offset)

        From the TTA manuscript (Section 3.4 - Nested Timelines):
        "A timeline can accommodate not only events but also other timelines,
        called Children, as long as they use the same measuring unit."

        Args:
            length: Length of the child timeline (in parent's unit). Can be a
                Coordinate object if its unit matches the parent.
            offset: The start coordinate on this timeline where the child begins.
            uid: Unique identifier for the child. Auto-generated if None.
            name: Human-readable name for the child.
            allow_expansion: If True, expand parent timeline if needed.

        Returns:
            The newly created and embedded child Timeline.

        Raises:
            ValueError: If offset is negative or child would exceed parent bounds.
            ValueError: If length/offset Coordinate has mismatched unit.
            RuntimeError: If this timeline is locked.

        Examples:
            >>> # Create a child representing a region of interest
            >>> holes_region = image_timeline.create_child(
            ...     length=277776,
            ...     offset=15343,
            ...     uid="dgt1_holes",
            ...     name="Musical Holes Region",
            ... )
            >>> # Now add events to the child
            >>> holes_region.add_events(hole_events)
        """
        # Extract value from Coordinate if provided, validating unit
        if isinstance(length, Coordinate):
            if length.unit != self._unit:
                raise ValueError(
                    f"Length Coordinate unit mismatch: got {length.unit}, "
                    f"expected {self._unit}"
                )
            length = length.value

        child = Timeline(
            length=length,
            unit=self._unit,
            number_type=self._number_type,
            uid=uid,
            name=name,
        )
        self.add_child(child, offset=offset, allow_expansion=allow_expansion)
        return child

    def get_child(self, child_id: str) -> Timeline:
        """Retrieve a child timeline by ID.

        Args:
            child_id: The ID of the child to retrieve.

        Returns:
            The child Timeline.

        Raises:
            KeyError: If no child with that ID exists.
        """
        if child_id not in self._children:
            raise KeyError(f"No child with ID '{child_id}'")
        return self._children[child_id]

    def get_child_offset(self, child_id: str) -> Coordinate:
        """Get the offset of a child timeline.

        Args:
            child_id: The ID of the child.

        Returns:
            The offset Coordinate.

        Raises:
            KeyError: If no child with that ID exists.
        """
        if child_id not in self._child_offsets:
            raise KeyError(f"No child with ID '{child_id}'")
        return self._child_offsets[child_id]

    def iter_children(
        self,
        order: TraversalOrder = "sorted",
        recursion_limit: int | None = None,
        include_self: bool = False,
    ) -> Iterator[tuple[Coordinate, Timeline]]:
        """Iterate over child timelines.

        Args:
            order: Traversal order - "sorted" (by offset), "depth_first",
                   or "breadth_first".
            recursion_limit: Maximum recursion depth. None for unlimited.
            include_self: If True, yield this timeline first.

        Yields:
            Tuples of (offset_coordinate, child_timeline).
        """
        if include_self:
            yield self._make_coordinate(0), self

        if recursion_limit is not None and recursion_limit <= 0:
            return

        next_limit = None if recursion_limit is None else recursion_limit - 1

        if order == "sorted":
            # Sort by offset
            sorted_children = sorted(
                self._children.items(),
                key=lambda x: self._child_offsets[x[0]].value,
            )
            for child_id, child in sorted_children:
                offset = self._child_offsets[child_id]
                yield offset, child
                # Recurse
                for sub_offset, sub_child in child.iter_children(
                    order=order, recursion_limit=next_limit, include_self=False
                ):
                    # Adjust offset relative to parent
                    combined_offset = self._make_coordinate(
                        offset.value + sub_offset.value
                    )
                    yield combined_offset, sub_child

        elif order == "breadth_first":
            # Yield all direct children first
            direct_children = []
            for child_id, child in self._children.items():
                offset = self._child_offsets[child_id]
                direct_children.append((offset, child))
                yield offset, child

            # Then recurse
            for offset, child in direct_children:
                for sub_offset, sub_child in child.iter_children(
                    order=order, recursion_limit=next_limit, include_self=False
                ):
                    combined_offset = self._make_coordinate(
                        offset.value + sub_offset.value
                    )
                    yield combined_offset, sub_child

        elif order == "depth_first":
            # Yield child, then its descendants, then next child
            for child_id, child in self._children.items():
                offset = self._child_offsets[child_id]
                yield offset, child
                for sub_offset, sub_child in child.iter_children(
                    order=order, recursion_limit=next_limit, include_self=False
                ):
                    combined_offset = self._make_coordinate(
                        offset.value + sub_offset.value
                    )
                    yield combined_offset, sub_child

    # endregion

    # region Content Inspection

    def _get_max_content_coordinate(self) -> CoordinateValue:
        """Get the maximum coordinate of all content.

        Returns:
            The maximum coordinate value.
        """
        max_coord: CoordinateValue = 0

        # Check events
        coord_range = self._events.coordinate_range()
        if coord_range:
            max_coord = max(max_coord, coord_range[1])

        # Check children
        for child_id, child in self._children.items():
            offset = self._child_offsets[child_id]
            child_end = offset.value + child.length.value
            max_coord = max(max_coord, child_end)

        return max_coord

    def summary(self) -> dict[str, Any]:
        """Get a summary of the timeline.

        Returns:
            Dict with timeline information.
        """
        return {
            "id": self._id,
            "class": self.class_name,
            "unit": str(self._unit),
            "number_type": str(self._number_type),
            "domain": str(self.domain),
            "length": self._length.value,
            "is_locked": self._locked,
            "n_events": self.n_events,
            "n_children": self.n_children,
            "event_summary": self._events.summary(),
        }

    # endregion

    # region Serialization

    def to_dict(self) -> dict[str, Any]:
        """Convert timeline to a dictionary for serialization.

        Returns:
            A dictionary representation of the timeline.
        """
        children_data = {}
        for child_id, child in self._children.items():
            children_data[child_id] = {
                "offset": self._child_offsets[child_id].value,
                "timeline": child.to_dict(),
            }

        return {
            "id": self._id,
            "name": self._name,
            "class": self.class_name,
            "unit": str(self._unit),
            "number_type": str(self._number_type),
            "length": self._length.value,
            "locked": self._locked,
            "meta": self._meta,
            "events": list(self._events),
            "children": children_data,
            "conversion_maps": [
                cmap.to_dict() for cmap in self._conversion_maps.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a Timeline from a dictionary.

        Args:
            data: Dictionary from to_dict().

        Returns:
            A new Timeline instance.
        """
        timeline = cls(
            length=data["length"],
            unit=data["unit"],
            number_type=data["number_type"],
            uid=data["id"],
            name=data.get("name"),
            locked=data.get("locked", False),
            meta=data.get("meta"),
        )

        # Add events (filter out segment events - they'll be recreated)
        # Events from to_dict have coordinate structs, need to extract values
        events = []
        for e in data.get("events", []):
            if e.get("event_type") == SEGMENT_EVENT_TYPE:
                continue
            # Convert coordinate structs back to raw values
            event = dict(e)
            for coord_col in ("instant", "start", "end", "duration"):
                if coord_col in event and event[coord_col] is not None:
                    coord_struct = event[coord_col]
                    if isinstance(coord_struct, dict) and "value" in coord_struct:
                        event[coord_col] = coord_struct["value"]
            events.append(event)

        if events:
            timeline._add_events_unchecked(events)

        # Add children
        for child_id, child_data in data.get("children", {}).items():
            child = cls.from_dict(child_data["timeline"])
            timeline.add_child(child, offset=child_data["offset"])

        # Add conversion maps
        for map_data in data.get("conversion_maps", []):
            cmap = ConversionMap.from_dict(map_data)
            timeline.add_conversion_map(cmap)

        return timeline

    def to_typed(self) -> "Timeline":
        """Return this timeline re-instantiated as the appropriate typed subclass.

        Uses the timeline's unit and number type to determine the correct
        concrete subclass (e.g., ``ContinuousPhysicalTimeline`` for seconds/float).
        If the timeline is already an instance of the correct subclass, returns
        ``self`` unchanged.

        This is useful after deserialization (e.g., ``Timeline.from_dict()``) or
        when working with generic ``Timeline`` instances that should carry
        domain-specific type information.

        Note: Only the timeline object itself is re-typed. Events, children,
        conversion maps, regions, and metadata are preserved. Children are
        transferred as-is (not recursively re-typed).

        Returns:
            A Timeline instance of the appropriate typed subclass, or ``self``
            if it is already the correct type.

        Examples:
            >>> tl = Timeline(length=10.0, unit=TimeUnit.seconds)
            >>> typed = tl.to_typed()
            >>> type(typed).__name__
            'ContinuousPhysicalTimeline'
            >>> typed.is_continuous
            True

            >>> # Already typed -- returns self
            >>> cpt = ContinuousPhysicalTimeline(length=10.0)
            >>> cpt.to_typed() is cpt
            True
        """
        from .types import get_timeline_class

        target_class = get_timeline_class(
            self.domain.value, discrete=self._unit.is_discrete
        )

        # Already the correct type -- return self
        if type(self) is target_class:
            return self

        # Create new instance of the correct class
        typed = target_class(
            length=self._length.value,
            unit=self._unit,
            number_type=self._number_type,
            uid=self._id,
            name=self._name,
            locked=self._locked,
            meta=dict(self._meta) if self._meta else None,
        )

        # Transfer events (use internal method to skip validation overhead)
        if self._events is not None and len(self._events) > 0:
            events = []
            for event in self._events:
                if event.get("event_type") == SEGMENT_EVENT_TYPE:
                    continue
                events.append(dict(event))
            if events:
                typed._add_events_unchecked(events)

        # Transfer children
        for child_id, child in self._children.items():
            offset = self._child_offsets[child_id]
            typed.add_child(child, offset=offset)

        # Transfer conversion maps
        for cmap in self._conversion_maps.values():
            typed.add_conversion_map(cmap)

        # Transfer regions
        for region in self._regions.values():
            typed._regions[region.name] = region

        # Transfer flow maps
        for flow_id, flow_map in self._flow_maps.items():
            typed._flow_maps[flow_id] = flow_map

        return typed

    # endregion

    # region Conversion Maps

    def add_conversion_map(self, cmap: ConversionMap[Any]) -> None:
        """Add a ConversionMap to this timeline.

        Any map with a ``target_unit`` is automatically registered in the
        unified timestamp system so that :meth:`get_timestamp` can resolve
        coordinates in that unit.  ``TableMap`` instances are wrapped in an
        ``InterpolationMap`` for O(log n) lookup; analytical maps (e.g.
        ``ScalarMap``, ``LinearMap``) are stored directly.

        Args:
            cmap: The ConversionMap to add.

        Raises:
            ValueError: If the map's source unit is incompatible.
        """
        from timetoalign.maps import TableMap

        if cmap.source_unit is not None and cmap.source_unit != self._unit:
            raise ValueError(
                f"Map source unit '{cmap.source_unit}' does not match "
                f"timeline unit '{self._unit}'"
            )
        self._conversion_maps[cmap.id] = cmap

        # Register in the unified timestamp system for unit-based lookup
        if cmap.target_unit is not None:
            if isinstance(cmap, TableMap):
                self._unit_maps[cmap.target_unit] = InterpolationMap.from_table_map(
                    cmap
                )
            else:
                self._unit_maps[cmap.target_unit] = cmap

        self._logger.debug(f"Added conversion map '{cmap.id}'")

    def get_conversion_map(
        self, target_unit: TimeUnit | str
    ) -> ConversionMap[Any] | None:
        """Get a conversion map by target unit **or** by name/id.

        When *target_unit* is a valid `TimeUnit` value (or an alias such as
        ``"seconds"``), the method returns the first attached map whose
        ``target_unit`` matches.

        When *target_unit* is a string that does **not** correspond to any
        ``TimeUnit`` member, the method falls back to a name-based lookup:
        it searches first by ``cmap.id``, then by ``cmap.name``.  This is
        useful for maps where source and target units are identical (e.g. a
        ``ShiftMap`` named ``"raw_quarters"`` that maps normalised quarters
        back to raw partitura quarters).

        Args:
            target_unit: A ``TimeUnit`` member, a unit alias string, or a
                conversion-map name/id string.

        Returns:
            A matching ``ConversionMap``, or ``None`` if not found.

        Examples:
            >>> timeline.get_conversion_map(TimeUnit.seconds)
            ScalarMap(...)
            >>> timeline.get_conversion_map("raw_quarters")
            ShiftMap(offset=-0.5, ...)
        """
        # Attempt unit-based lookup first
        try:
            target = TimeUnit(target_unit)
        except ValueError:
            pass
        else:
            for cmap in self._conversion_maps.values():
                if cmap.target_unit == target:
                    return cmap
            return None

        # Fallback: name/id-based lookup (target_unit is a plain string)
        name = str(target_unit)
        # Direct id lookup (O(1) — _conversion_maps is keyed by cmap.id)
        if name in self._conversion_maps:
            return self._conversion_maps[name]
        # Fallback to name attribute scan
        for cmap in self._conversion_maps.values():
            if cmap.name == name:
                return cmap
        return None

    def convert_to(
        self,
        values: CoordinateValue | Coordinate | np.ndarray,
        target_unit: TimeUnit | str,
    ) -> Coordinate | np.ndarray:
        """Convert coordinates to another unit using attached C-Maps.

        Args:
            values: Coordinate value(s) to convert. Can be:
                - Scalar (int, float, Fraction): Returns a Coordinate object
                - Coordinate: Returns a Coordinate object
                - numpy array: Returns a numpy array of converted values
            target_unit: Target unit.

        Returns:
            - For scalar/Coordinate input: Coordinate object in the target unit
            - For array input: numpy array of converted values

        Raises:
            ValueError: If no suitable map is found.

        Examples:
            >>> timeline.add_conversion_map(ScalarMap(scalar=1/300, ...))
            >>> coord = timeline.convert_to(15343, "inches")
            >>> coord
            Coordinate(51.1, inches)
            >>> arr = timeline.convert_to(np.array([100, 200]), "inches")
            >>> arr
            array([0.333, 0.666])
        """
        target = TimeUnit(target_unit)
        cmap = self.get_conversion_map(target)
        if cmap is None:
            raise ValueError(
                f"No conversion map found from '{self._unit}' to '{target}'"
            )
        converted_value = cmap(values)

        # Return array for array input, Coordinate for scalar input
        if isinstance(values, np.ndarray):
            return converted_value
        return Coordinate(converted_value, target)

    def derive(
        self,
        target_unit: TimeUnit | str,
        name: str | None = None,
        copy_events: bool = False,
    ) -> "Timeline":
        """Create a derivative timeline in a different unit via C-Map conversion.

        From TTA manuscript (Section 3.3):
        "A ConversionMap implies the presence of a derived timeline in the
        target unit. The derive() method makes this implicit timeline explicit."

        The derived timeline:
        - Has coordinates in the target unit
        - Has length equal to the converted source length
        - Automatically has an inverse C-Map back to the source unit
        - Optionally copies and converts events from the source

        This operation creates a NEW timeline, NOT a child timeline.
        The source and derived timelines have different units, so per TTA
        specification, they cannot be parent-child (children must share
        the parent's unit). Use TimelineGroup to connect them.

        Args:
            target_unit: The unit for the derived timeline.
            name: Optional name for the derived timeline.
            copy_events: If True, copy and convert events to the derived timeline.

        Returns:
            A new Timeline in the target unit.

        Raises:
            ValueError: If no C-Map exists for the target unit.
            ValueError: If C-Map is not invertible (needed for roundtrip).

        Examples:
            >>> # Create physical timeline with tempo C-Map
            >>> audio = ContinuousPhysicalTimeline(length=60.0)
            >>> audio.add_conversion_map(LinearMap(2.0, 0.0,
            ...     source_unit=TimeUnit.seconds, target_unit=TimeUnit.quarters))
            >>> # Derive a logical timeline
            >>> score = audio.derive(TimeUnit.quarters, name="score")
            >>> score.unit
            TimeUnit.quarters
            >>> score.length
            Coordinate(120.0, quarters)  # 60 seconds * 2 q/s
        """
        target = TimeUnit(target_unit) if isinstance(target_unit, str) else target_unit

        # Get the C-Map for this conversion
        cmap = self.get_conversion_map(target)
        if cmap is None:
            raise ValueError(
                f"No C-Map from '{self._unit}' to '{target}'. "
                f"Add a ConversionMap with add_conversion_map() first."
            )

        # Convert length
        derived_length = cmap(self._length.value)

        # Determine appropriate Timeline class for target domain
        from .types import get_timeline_class

        target_domain = target.domain.name.lower()
        # Determine discrete vs continuous based on target unit
        # Ticks, samples, frames, pixels are discrete
        discrete_units = {
            TimeUnit.ticks,
            TimeUnit.samples,
            TimeUnit.frames,
            TimeUnit.pixels,
        }
        is_discrete = target in discrete_units

        try:
            derived_class = get_timeline_class(target_domain, discrete=is_discrete)
        except ValueError:
            # Fallback to base Timeline if domain lookup fails
            derived_class = Timeline

        # Create derived timeline
        derived = derived_class(
            length=derived_length,
            unit=target,
            name=name or f"{self._id}_derived",
        )

        # Add inverse C-Map if available (for roundtrip conversion)
        if cmap.is_invertible:
            inverse = cmap.inverse()
            derived.add_conversion_map(inverse)
        else:
            self._logger.warning(
                f"C-Map '{cmap.id}' is not invertible. "
                f"The derived timeline will not have a C-Map back to '{self._unit}'."
            )

        # Copy and convert events if requested
        if copy_events:
            converted_events = []
            for event in self._events:
                # Skip segment events
                if event.get("event_type") == SEGMENT_EVENT_TYPE:
                    continue

                converted = dict(event)
                for coord_col in ("instant", "start", "end"):
                    val = converted.get(coord_col)
                    if val is not None:
                        # Handle coordinate struct or raw value
                        if isinstance(val, dict) and "value" in val:
                            converted[coord_col] = float(cmap(val["value"]))
                        else:
                            converted[coord_col] = float(cmap(val))

                # Convert duration if present
                if converted.get("duration") is not None:
                    duration_val = converted["duration"]
                    if isinstance(duration_val, dict) and "value" in duration_val:
                        # Duration needs to be converted using rate, not absolute value
                        # For linear maps: derived_duration = source_duration * scalar
                        converted["duration"] = float(
                            cmap(duration_val["value"])
                        ) - float(cmap(0))
                    else:
                        converted["duration"] = float(cmap(duration_val)) - float(
                            cmap(0)
                        )

                converted_events.append(converted)

            if converted_events:
                derived.add_events(converted_events)

        self._logger.debug(
            f"Derived timeline '{derived.id}' in {target} from '{self._id}'"
        )

        return derived

    # endregion

    # region Unified Timestamp API (offset arithmetic + InterpolationMap-based)

    def _get_child_coordinate(self, child_id: str, parent_coord: float) -> float | None:
        """Convert a parent coordinate to a child coordinate via exact offset arithmetic.

        ``child_coord = parent_coord - offset``

        Returns None if *parent_coord* falls outside the child's
        ``[offset, offset + length)`` span.

        Args:
            child_id: The child timeline ID.
            parent_coord: Coordinate on this (parent) timeline.

        Returns:
            Coordinate on the child timeline, or None if out of bounds.
        """
        offset = self._child_offsets.get(child_id)
        if offset is None:
            return None
        child = self._children[child_id]
        child_coord = parent_coord - float(offset.value)
        child_length = float(child.length.value)
        if child_coord < 0 or (child_length > 0 and child_coord >= child_length):
            return None
        return child_coord

    def _get_parent_coordinate_from_child(
        self, child_id: str, child_coord: float
    ) -> float:
        """Convert a child coordinate to a parent coordinate via exact offset arithmetic.

        ``parent_coord = child_coord + offset``

        Args:
            child_id: The child timeline ID.
            child_coord: Coordinate on the child timeline.

        Returns:
            Coordinate on this (parent) timeline.

        Raises:
            KeyError: If *child_id* is not a child of this timeline.
        """
        offset = self._child_offsets[child_id]
        return child_coord + float(offset.value)

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> InterpolationMap | None:
        """Get InterpolationMap for coordinate conversion to target.

        This method is part of the `TimeStampSource` protocol.

        For parent-child relationships, returns None: child coordinates are
        resolved via exact offset arithmetic in ``_get_child_coordinate()``
        instead. InterpolationMaps are only used for unit-based conversions
        (via ``_get_unit_map``) and by `TimelineGroup` for inter-member
        conversions.

        Args:
            target_id: Target timeline ID.
            source_id: Source timeline ID (ignored for Timeline, always self).

        Returns:
            None. Child conversion uses offset arithmetic.
        """
        return None

    def _get_unit_map(
        self, unit: TimeUnit
    ) -> InterpolationMap | ConversionMap[Any] | None:
        """Get a map for unit-based conversion.

        Returns an ``InterpolationMap`` (for ``TableMap``-based conversions)
        or a ``ConversionMap`` (for analytical maps like ``ScalarMap``) --
        whichever was registered by :meth:`add_conversion_map`.

        This method is part of the TimeStampSource protocol.

        Args:
            unit: Target unit.

        Returns:
            A map for conversion, or None if no C-Map available.
        """
        return self._unit_maps.get(unit)

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of all related timelines (children).

        This method is part of the TimeStampSource protocol.

        Returns:
            List of child timeline IDs.
        """
        return list(self._children.keys())

    def _get_available_units(self) -> list[TimeUnit]:
        """Get all units available via C-Maps.

        This method is part of the TimeStampSource protocol.

        Returns:
            List of target units available for conversion.
        """
        return list(self._unit_maps.keys())

    def _get_unit_for_timeline(self, timeline_id: str) -> TimeUnit | None:
        """Get the TimeUnit for a timeline in the hierarchy.

        This method is part of the TimeStampSource protocol. It enables
        TimeStamp to construct proper Coordinate objects with correct units.

        Args:
            timeline_id: The timeline ID to look up.

        Returns:
            The TimeUnit for the timeline, or None if not found.
        """
        if timeline_id == self._id:
            return self._unit

        # Check children
        if timeline_id in self._children:
            return self._children[timeline_id].unit

        return None

    def _contains_coordinate(self, timeline_id: str, axis: float) -> bool:
        """Check whether *axis* falls within the span of a child timeline.

        A child embedded at *offset* with *length* spans
        ``[offset, offset + length)`` on this (parent) timeline.

        This method is part of the TimeStampSource protocol.

        Args:
            timeline_id: Child timeline ID.
            axis: Coordinate on the parent (source) timeline.

        Returns:
            True if *axis* is inside the child's span, or if
            *timeline_id* is the source itself.
        """
        if timeline_id == self._id:
            return True
        if timeline_id not in self._child_offsets:
            return False
        offset = float(self._child_offsets[timeline_id].value)
        length = float(self._children[timeline_id].length.value)
        return offset <= axis < offset + length

    def get_timestamp(
        self,
        coord: CoordinateValue | Coordinate,
        unit: TimeUnit | str | None = None,
    ) -> TimeStamp:
        """Get a TimeStamp at a specific coordinate.

        This is the primary coordinate resolution API. The TimeStamp provides
        access to all equivalent coordinates across children and C-Map units.

        Uses InterpolationMaps for O(log n) coordinate conversion.

        Args:
            coord: Coordinate value. Can be:
                - int/float/Fraction: Value in timeline's native unit
                - Coordinate: Must match unit or specify via `unit` param
            unit: If provided, interpret coord as being in this unit.
                The coordinate is first converted via inverse C-Map.

        Returns:
            TimeStamp object for the resolved coordinate.

        Raises:
            ValueError: If unit specified but no inverse C-Map available.

        Examples:
            >>> ts = timeline.get_timestamp(5.0)
            >>> ts["child_a"]  # Get coordinate on child_a
            2.5

            >>> # Query with unit conversion
            >>> ts = timeline.get_timestamp(10.5, unit=TimeUnit.seconds)
            >>> ts.axis  # Converted from seconds to timeline's unit
            5.0
        """
        # Resolve coordinate value
        if isinstance(coord, Coordinate):
            if unit is None and coord.unit != self._unit:
                unit = coord.unit
            axis = float(coord.value)
        else:
            axis = float(coord)

        # Convert from specified unit if needed
        if unit is not None:
            target_unit = TimeUnit(unit) if isinstance(unit, str) else unit
            if target_unit != self._unit:
                imap = self._get_unit_map(target_unit)
                if imap is None:
                    raise ValueError(
                        f"No C-Map available for unit '{target_unit}'. "
                        f"Cannot resolve coordinate."
                    )
                # Inverse: target unit -> timeline's unit
                axis = float(imap.inverse(axis))

        return TimeStamp(
            axis=axis,
            source=self,
            source_id=self._id,
        )

    def get_interval_stamp(
        self,
        start: CoordinateValue | Coordinate,
        end: CoordinateValue | Coordinate,
        unit: TimeUnit | str | None = None,
    ) -> TimeIntervalStamp:
        """Get a TimeIntervalStamp for a coordinate range.

        Args:
            start: Start coordinate.
            end: End coordinate.
            unit: If provided, interpret both coords as being in this unit.

        Returns:
            TimeIntervalStamp with start and end TimeStamps.

        Examples:
            >>> interval = timeline.get_interval_stamp(0.0, 10.0)
            >>> interval.duration
            10.0
            >>> interval["child:1"]  # Get (start, end) tuple for child
            (0.0, 7.5)
        """
        return TimeIntervalStamp(
            start=self.get_timestamp(start, unit),
            end=self.get_timestamp(end, unit),
        )

    # endregion

    # region Timestamp Generation

    def _extract_event_coordinates(
        self,
        event_filter: dict[str, Any] | pc.Expression | None = None,
    ) -> pa.ChunkedArray:
        """Extract all unique event coordinates as a sorted PyArrow array.

                Uses PyArrow compute to efficiently extract coordinates from the
                EventData table without Python iteration.

                Args:
                    event_filter: Optional filter to apply before extracting coordinates.
        Can be a dict (passed to EventData.filter()) or a pc.Expression
                        (passed to EventData.where()).

                Returns:
                    Sorted PyArrow ChunkedArray of unique coordinate values (float64).
                    Returns empty array if no events.

                Notes:
                    - Extracts start.value from all events
                    - Extracts end.value from interval events (drops nulls)
                    - Deduplicates and sorts the result
        """
        # Apply filter if provided
        if event_filter is not None:
            if isinstance(event_filter, pc.Expression):
                filtered_store = self._events.where(event_filter)
            else:
                filtered_store = self._events.filter(**event_filter)
            table = filtered_store.table
        else:
            table = self._events.table

        if table.num_rows == 0:
            return pa.chunked_array([], type=pa.float64())

        # Extract start coordinates (all events have start)
        # struct_field returns ChunkedArray
        start_col = table.column("start")
        start_vals = pc.struct_field(start_col, "value")

        # Extract end coordinates (intervals only, filter nulls)
        end_col = table.column("end")
        end_vals = pc.struct_field(end_col, "value")
        end_vals = pc.drop_null(end_vals)

        # Combine chunks from both ChunkedArrays
        all_chunks = start_vals.chunks + end_vals.chunks
        if not all_chunks:
            return pa.chunked_array([], type=pa.float64())

        combined = pa.chunked_array(all_chunks, type=pa.float64())

        # Deduplicate
        unique_coords = pc.unique(combined)

        # Sort ascending
        sort_indices = pc.sort_indices(unique_coords)
        sorted_coords = pc.take(unique_coords, sort_indices)

        return sorted_coords

    def _collect_all_coordinates(
        self,
        recursion_limit: int | None = None,
        offset: float = 0.0,
        event_filter: dict[str, Any] | pc.Expression | None = None,
    ) -> pa.Array:
        """Collect coordinates from this timeline and all children.

        Recursively collects event coordinates, applying cumulative offset
        to convert to root-relative coordinates.

        Args:
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            offset: Cumulative offset from root timeline (internal use).
            event_filter: Optional filter applied to each timeline's events.
                Can be a dict (passed to EventData.filter()) or a pc.Expression
                (passed to EventData.where()). The same filter is applied to
                all timelines in the hierarchy.

        Returns:
            PyArrow array of unique, sorted, root-relative coordinates (float64).
        """
        # Get this timeline's coordinates (with optional filter)
        local_coords = self._extract_event_coordinates(event_filter)

        # Apply offset to make root-relative
        if offset != 0.0 and len(local_coords) > 0:
            local_coords = pc.add(local_coords, offset)

        arrays = [local_coords]

        # Recurse into children
        if recursion_limit is None or recursion_limit > 0:
            next_limit = None if recursion_limit is None else recursion_limit - 1
            for child_id, child in self._children.items():
                child_offset = self._child_offsets[child_id].value
                child_coords = child._collect_all_coordinates(
                    recursion_limit=next_limit,
                    offset=offset + child_offset,
                    event_filter=event_filter,
                )
                if len(child_coords) > 0:
                    arrays.append(child_coords)

        # Combine all and deduplicate
        if len(arrays) == 1:
            return arrays[0]

        # Filter out empty arrays before concatenation
        non_empty = [a for a in arrays if len(a) > 0]
        if not non_empty:
            return pa.array([], type=pa.float64())

        combined = pa.concat_arrays(non_empty)
        unique = pc.unique(combined)

        # Sort ascending
        sort_indices = pc.sort_indices(unique)
        return pc.take(unique, sort_indices)

    def _collect_boundary_coordinates(
        self,
        recursion_limit: int | None = None,
        offset: float = 0.0,
    ) -> pa.Array:
        """Collect timeline boundary coordinates (start=0, end=length).

        Recursively collects boundary coordinates from this timeline
        and all children, applying cumulative offsets.

        Args:
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            offset: Cumulative offset from root timeline (internal use).

        Returns:
            PyArrow array of unique, sorted, root-relative boundary coordinates.
        """
        # This timeline's boundaries
        boundaries = [offset, offset + self._length.value]
        arrays = [pa.array(boundaries, type=pa.float64())]

        # Recurse into children
        if recursion_limit is None or recursion_limit > 0:
            next_limit = None if recursion_limit is None else recursion_limit - 1
            for child_id, child in self._children.items():
                child_offset = self._child_offsets[child_id].value
                child_bounds = child._collect_boundary_coordinates(
                    recursion_limit=next_limit,
                    offset=offset + child_offset,
                )
                if len(child_bounds) > 0:
                    arrays.append(child_bounds)

        # Combine and deduplicate
        if len(arrays) == 1:
            return arrays[0]

        combined = pa.concat_arrays(arrays)
        unique = pc.unique(combined)
        sort_indices = pc.sort_indices(unique)
        return pc.take(unique, sort_indices)

    def _compute_local_coordinates(
        self,
        root_coords: pa.Array,
        offset: float = 0.0,
    ) -> pa.Array:
        """Compute local coordinates from root coordinates.

        Vectorized offset subtraction with bounds checking. Coordinates
        outside [0, length] are replaced with null.

        Args:
            root_coords: Array of root-relative coordinates.
            offset: This timeline's offset from root.

        Returns:
            PyArrow array with local coordinates, null for out-of-bounds.
        """
        if len(root_coords) == 0:
            return pa.array([], type=pa.float64())

        # Subtract offset: local = root - offset
        local = pc.subtract(root_coords, offset)

        # Create mask for out-of-bounds coordinates
        too_low = pc.less(local, 0.0)
        too_high = pc.greater(local, self._length.value)
        out_of_bounds = pc.or_(too_low, too_high)

        # Replace out-of-bounds with null
        null_scalar = pa.scalar(None, type=pa.float64())
        return pc.if_else(out_of_bounds, null_scalar, local)

    def _resolve_conversion_maps(
        self, spec: ConversionMapsSpec
    ) -> list[ConversionMap[Any]]:
        """Resolve a flexible conversion_maps specification to a list of C-Maps.

        Supports multiple input formats for convenience:
        - True: Return all attached conversion maps
        - False/None: Return empty list
        - str: Look up by map ID, or find map by target unit name
        - TimeUnit: Find map by target unit
        - ConversionMap: Return as single-element list
        - Iterable: Resolve each element recursively

        Args:
            spec: Flexible specification for which C-Maps to include.

        Returns:
            List of resolved ConversionMap objects.

        Raises:
            KeyError: If a string ID doesn't match any attached map.
            ValueError: If a TimeUnit doesn't match any attached map's target.

        Examples:
            >>> tl._resolve_conversion_maps(True)  # All maps
            >>> tl._resolve_conversion_maps("inches")  # Single map by ID/unit
            >>> tl._resolve_conversion_maps(["inches", "cm"])  # Multiple
            >>> tl._resolve_conversion_maps(TimeUnit.seconds)  # By unit enum
        """
        if spec is None or spec is False:
            return []

        if spec is True:
            # Return all attached conversion maps
            return list(self._conversion_maps.values())

        # Single string: could be map ID or target unit name
        if isinstance(spec, str):
            # First try exact ID match
            if spec in self._conversion_maps:
                return [self._conversion_maps[spec]]
            # Try as target unit name
            try:
                unit = TimeUnit(spec)
                cmap = self.get_conversion_map(unit)
                if cmap is not None:
                    return [cmap]
            except ValueError:
                pass
            raise KeyError(
                f"No conversion map with ID '{spec}' or target unit '{spec}'. "
                f"Available: {list(self._conversion_maps.keys())}"
            )

        # TimeUnit: find by target unit
        if isinstance(spec, TimeUnit):
            cmap = self.get_conversion_map(spec)
            if cmap is not None:
                return [cmap]
            raise ValueError(
                f"No conversion map with target unit '{spec}'. "
                f"Available: {list(self._conversion_maps.keys())}"
            )

        # Single ConversionMap object
        if isinstance(spec, ConversionMap):
            return [spec]

        # Iterable: resolve each element
        resolved: list[ConversionMap[Any]] = []
        for item in spec:
            resolved.extend(self._resolve_conversion_maps(item))
        return resolved

    def _build_timestamp_table(
        self,
        axis: pa.Array,
        conversion_maps: list[ConversionMap[Any]] | None = None,
        recursion_limit: int | None = None,
    ) -> pa.Table:
        """Build a timestamp table from axis coordinates.

        Constructs a PyArrow table with:
        - axis: Root coordinate values
        - One column per timeline (root + children) with local coordinates
        - One column per C-Map with converted values

        Each column includes field metadata:
        - unit: The TimeUnit for this column's coordinates
        - timeline_id: The timeline ID (for timeline columns)
        - cmap_id: The C-Map ID (for C-Map columns)

        Args:
            axis: Array of root-relative coordinates (the timestamp axis).
            conversion_maps: Optional list of C-Maps to include as columns.
            recursion_limit: Maximum depth for child traversal. None = unlimited.

        Returns:
            PyArrow table with timestamp data and field-level unit metadata.
        """
        columns: dict[str, pa.Array] = {}
        fields: list[pa.Field] = []

        # Helper to get PyArrow type from NumberType
        def _get_pa_type(number_type: NumberType) -> pa.DataType:
            """Map NumberType to PyArrow type: int -> int64, else float64."""
            return pa.int64() if number_type == NumberType.int else pa.float64()

        # Add axis column (root timeline coordinate)
        axis_pa_type = _get_pa_type(self._number_type)
        columns["axis"] = axis
        fields.append(
            pa.field(
                "axis",
                axis_pa_type,
                metadata={
                    b"unit": self._unit.value.encode("utf-8"),
                    b"timeline_id": self._id.encode("utf-8"),
                },
            )
        )

        # Add root timeline column (offset=0)
        columns[self._id] = self._compute_local_coordinates(axis, offset=0.0)
        fields.append(
            pa.field(
                self._id,
                axis_pa_type,
                metadata={
                    b"unit": self._unit.value.encode("utf-8"),
                    b"timeline_id": self._id.encode("utf-8"),
                },
            )
        )

        # Add child columns recursively
        for child_offset, child in self.iter_children(
            recursion_limit=recursion_limit,
            include_self=False,
        ):
            child_pa_type = _get_pa_type(child._number_type)
            columns[child.id] = child._compute_local_coordinates(
                axis, offset=float(child_offset.value)
            )
            fields.append(
                pa.field(
                    child.id,
                    child_pa_type,
                    metadata={
                        b"unit": child.unit.value.encode("utf-8"),
                        b"timeline_id": child.id.encode("utf-8"),
                    },
                )
            )

        # Add C-Map columns
        # C-Maps work on NumPy arrays; we convert PyArrow <-> NumPy at the boundary
        # See: .agent/skills/tta-guide/references/cmap_pyarrow_integration.md
        if conversion_maps:
            # Allow copy for arrays with nulls (zero_copy_only=False)
            axis_np = axis.to_numpy(zero_copy_only=False)
            for cmap in conversion_maps:
                converted = cmap.convert_array(axis_np)
                # Use map's name property for human-readable column header
                col_name = cmap.name
                columns[col_name] = pa.array(converted)
                # C-Map columns include target unit from the C-Map
                target_unit = getattr(cmap, "target_unit", None)
                unit_value = target_unit.value if target_unit else "unknown"
                fields.append(
                    pa.field(
                        col_name,
                        pa.float64(),
                        metadata={
                            b"unit": unit_value.encode("utf-8"),
                            b"cmap_id": cmap.id.encode("utf-8"),
                        },
                    )
                )

        # Build table with explicit schema to preserve metadata
        schema = pa.schema(fields)
        return pa.table(columns, schema=schema)

    def _resolve_coordinate_spec(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec],
    ) -> pa.Array:
        """Resolve CoordinateSpec to axis coordinates.

        Handles IdCoordinate objects by automatically applying child offsets.
        This enables the dead-simple pattern:

            child_coords = [IdCoordinate(v, unit, "child_id") for v in values]
            df = parent.get_timestamps(coordinates=child_coords)

        When an IdCoordinate's timeline_id matches a child of this timeline,
        the coordinate is automatically converted to parent coordinates by
        adding the child's offset.

        Args:
            coordinates: Single CoordinateSpec or sequence of CoordinateSpec.
                - int/float/Fraction: Used directly as axis coordinate
                - Coordinate: Value extracted
                - IdCoordinate: Child offset applied if timeline_id matches a child
                - Sequence of the above: Each element processed individually

        Returns:
            PyArrow array of float64 axis coordinates.

        Examples:
            >>> # IdCoordinate from child timeline - offset auto-applied
            >>> child_coord = IdCoordinate(1000.0, TimeUnit.pixels, "dgt_holes")
            >>> axis = parent._resolve_coordinate_spec([child_coord])
            >>> # axis[0] == 1000.0 + child_offset
        """

        # Fast path: PyArrow array or numpy array of plain floats
        if isinstance(coordinates, pa.Array):
            return coordinates.cast(pa.float64())
        if isinstance(coordinates, np.ndarray):
            return pa.array(coordinates.astype(np.float64))

        # Single Coordinate or IdCoordinate
        if isinstance(coordinates, (Coordinate, IdCoordinate)):
            coordinates = [coordinates]

        # Process list of coordinates
        resolved: list[float] = []
        for coord in coordinates:
            if isinstance(coord, IdCoordinate):
                # Check if timeline_id matches a child
                if coord.timeline_id in self._children:
                    # Apply offset: parent_coord = child_coord + offset
                    offset = float(self._child_offsets[coord.timeline_id].value)
                    resolved.append(float(coord.value) + offset)
                elif coord.timeline_id == self._id:
                    # Coordinate is already in parent's coordinate system
                    resolved.append(float(coord.value))
                else:
                    # Unknown timeline_id - use value as-is (may be intentional)
                    resolved.append(float(coord.value))
            elif isinstance(coord, Coordinate):
                # Plain Coordinate - use value directly
                resolved.append(float(coord.value))
            else:
                # Numeric value (int, float, Fraction, or pyarrow scalar)
                resolved.append(
                    float(coord.as_py() if hasattr(coord, "as_py") else coord)
                )

        return pa.array(resolved, type=pa.float64())

    def get_timestamp_table(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
    ) -> pa.Table:
        """Generate a timestamp table as a PyArrow Table.

        A Timestamp is a cross-section through the timeline hierarchy showing
        synchronous coordinates. This method computes local coordinates for
        each timeline in the hierarchy at each axis coordinate.

        Supports IdCoordinate for automatic child offset resolution:

            >>> # IdCoordinates from child timeline - offsets auto-applied!
            >>> child_coords = [IdCoordinate(v, unit, "child_id") for v in values]
            >>> df = parent.get_timestamps(coordinates=child_coords)

        Args:
            coordinates: Explicit coordinates to use as the axis. If None,
                coordinates are extracted from events (and optionally boundaries).
                Accepts IdCoordinate objects - if timeline_id matches a child,
                the offset is automatically applied.
            conversion_maps: C-Maps to include as columns. Flexible input:
                - True: Include all attached conversion maps
                - str: Map ID or target unit name (e.g., "inches", "seconds")
                - TimeUnit: Find map by target unit enum
                - ConversionMap: Include the specific map
                - list: Mix of the above
                - None/False: No conversion maps
            recursion_limit: Maximum depth for child traversal. None = unlimited.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.

        Returns:
            PyArrow Table with schema:
                - axis: float64 (root coordinate)
                - {timeline_id}: float64 (nullable, local coordinate per timeline)
                - {cmap_id}: varies (converted value per C-Map)

            Each field includes metadata:
                - unit: TimeUnit.value string (e.g., "seconds", "pixels")
                - timeline_id: Timeline ID (for timeline columns)
                - cmap_id: C-Map ID (for C-Map columns)

            Access metadata via: ``table.schema.field(col_name).metadata``

        Examples:
            >>> table = timeline.get_timestamp_table()
            >>> table.column_names
            ['axis', 'tl:1', 'notes', 'measures']

            >>> # Include all attached C-Maps
            >>> table = timeline.get_timestamp_table(conversion_maps=True)

            >>> # Include specific C-Maps by target unit
            >>> table = timeline.get_timestamp_table(conversion_maps=["inches", "cm"])

            >>> # Access unit metadata
            >>> table.schema.field('axis').metadata[b'unit']
            b'seconds'
        """
        # Resolve coordinates (handles IdCoordinate with auto child offset)
        if coordinates is not None:
            axis = self._resolve_coordinate_spec(coordinates)
        elif include_events:
            # Extract from events
            event_coords = self._collect_all_coordinates(
                recursion_limit=recursion_limit
            )
            if include_boundaries:
                boundary_coords = self._collect_boundary_coordinates(
                    recursion_limit=recursion_limit
                )
                if len(event_coords) > 0 and len(boundary_coords) > 0:
                    combined = pa.concat_arrays([event_coords, boundary_coords])
                    unique = pc.unique(combined)
                    sort_indices = pc.sort_indices(unique)
                    axis = pc.take(unique, sort_indices)
                elif len(boundary_coords) > 0:
                    axis = boundary_coords
                else:
                    axis = event_coords
            else:
                axis = event_coords
        else:
            # Boundaries only
            axis = self._collect_boundary_coordinates(recursion_limit=recursion_limit)

        # Resolve C-Map references using flexible helper
        resolved_maps = self._resolve_conversion_maps(conversion_maps)

        return self._build_timestamp_table(
            axis=axis,
            conversion_maps=resolved_maps if resolved_maps else None,
            recursion_limit=recursion_limit,
        )

    def get_timestamps(
        self,
        coordinates: CoordinateSpec | Sequence[CoordinateSpec] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
        *,
        units: bool = True,
    ) -> pd.DataFrame:
        """Generate timestamps as a pandas DataFrame with units in column names.

        Convenience wrapper around get_timestamp_table() for users who
        prefer working with pandas.

        **IdCoordinate support:** When passing IdCoordinate objects whose
        `timeline_id` matches a child timeline, the offset is automatically
        applied. This enables the dead-simple pattern::

            child_coords = [IdCoordinate(v, unit, "dgt_holes") for v in values]
            df = parent.get_timestamps(coordinates=child_coords)

        Args:
            coordinates: CoordinateSpec or sequence of CoordinateSpec. Accepts
                IdCoordinate - if timeline_id matches a child, offset is auto-applied.
            conversion_maps: C-Maps to include as columns. Flexible input:
                - True: Include all attached conversion maps
                - str: Map ID or target unit name (e.g., "inches", "seconds")
                - TimeUnit: Find map by target unit enum
                - ConversionMap: Include the specific map
                - list: Mix of the above
                - None/False: No conversion maps
            recursion_limit: Maximum depth for child traversal.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.
            units: If True (default), append units to column names like "name (unit)".

        Returns:
            pandas DataFrame with units in column names (if units=True).

        Examples:
            >>> df = timeline.get_timestamps()
            >>> df.columns
            Index(['axis (pixels)', 'tl:1 (pixels)', 'pixels_to_inches (inches)'])

            >>> # Include all attached C-Maps
            >>> df = timeline.get_timestamps(conversion_maps=True)

            >>> # Without units in column names
            >>> df = timeline.get_timestamps(units=False)
        """
        from timetoalign.core.timestamp import timestamp_table_to_dataframe

        table = self.get_timestamp_table(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
        )
        return timestamp_table_to_dataframe(table=table, units=units)

    def to_dataframe(
        self,
        coordinates: pa.Array | np.ndarray | list[float] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
        *,
        columns: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
        units: bool = True,
        format: str = "pandas",
    ) -> pd.DataFrame:
        """Generate timestamps as a pandas DataFrame with formatted column names.

        This is the recommended high-level method for getting timestamp data.
        It builds on get_timestamp_table() and applies column formatting.

        Args:
            coordinates: Explicit coordinates to use as the axis.
            conversion_maps: C-Maps to include as columns. Defaults to True (all).
            recursion_limit: Maximum depth for child traversal.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.
            columns: How to name the columns. Options:
                - None or ColumnNaming.name (default): Use timeline/cmap name
                - ColumnNaming.id: Use timeline/cmap id
                - Callable: Function taking (name, metadata_dict) -> new_name
                - list[str]: Explicit column names
            units: If True (default), append units to column names like "name (unit)".
            format: Output format. Currently only "pandas" is supported.

        Returns:
            pandas DataFrame with:
            - Columns named according to the `columns` parameter
            - Units appended if `units=True`
            - Integer columns using pandas nullable Int64 dtype

        Examples:
            >>> df = timeline.to_dataframe()
            >>> df.columns
            Index(['axis (pixels)', 'dgt1 (pixels)', 'pixels_to_inches (inches)'])

            >>> # Without units in column names
            >>> df = timeline.to_dataframe(units=False)
            >>> df.columns
            Index(['axis', 'dgt1', 'pixels_to_inches'])
        """
        from timetoalign.core.timestamp import timestamp_table_to_dataframe

        table = self.get_timestamp_table(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
        )
        return timestamp_table_to_dataframe(
            table=table,
            columns=columns,
            units=units,
            format=format,
        )

    def get_boundary_table(
        self,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
    ) -> pa.Table:
        """Get timestamps for timeline boundaries only.

        Returns a timestamp table containing only start (0) and end (length)
        coordinates for this timeline and all children.

        Args:
            conversion_maps: C-Maps to include as columns (see get_timestamp_table).
            recursion_limit: Maximum depth for child traversal.

        Returns:
            PyArrow Table with boundary timestamps.

        Examples:
            >>> table = timeline.get_boundary_table()
            >>> table.to_pandas()
               axis  tl:1  child:1
            0   0.0   0.0      NaN
            1  10.0  10.0     10.0
            2  50.0   NaN      0.0
            3  60.0   NaN     10.0
        """
        return self.get_timestamp_table(
            coordinates=self._collect_boundary_coordinates(
                recursion_limit=recursion_limit
            ),
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=False,
            include_boundaries=False,  # Already included in coordinates
        )

    def get_timestamp_table_filtered(
        self,
        event_filter: dict[str, Any] | pc.Expression,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_boundaries: bool = False,
    ) -> pa.Table:
        """Generate timestamps for filtered events only.

        Applies an event filter before extracting coordinates from EventData.
        This enables efficient timestamp generation for subsets of events
        (e.g., only Note events, events above a certain duration, etc.).

        The filter is applied to each timeline in the hierarchy using either
        EventData.filter() (for dict filters) or EventData.where() (for
        PyArrow compute expressions).

        Args:
            event_filter: Filter to apply before extracting coordinates.
                - dict: Passed to EventData.filter() for simple filters.
                  Example: {"event_type": "Note"} or {"temporal_type": "interval"}
                - pc.Expression: Passed to EventData.where() for complex filters.
                  Example: pc.greater(pc.struct_field(pc.field("start"), "value"), 10.0)
            conversion_maps: C-Maps to include as columns (see get_timestamp_table).
            recursion_limit: Maximum depth for child traversal.
            include_boundaries: If True, also include timeline boundary coordinates.

        Returns:
            PyArrow Table with timestamp data for filtered events only.

        Examples:
            >>> # Dict filter: only Note events
            >>> table = timeline.get_timestamp_table_filtered(
            ...     {"event_type": "Note"}
            ... )

            >>> # Dict filter: only interval events
            >>> table = timeline.get_timestamp_table_filtered(
            ...     {"temporal_type": "interval"}
            ... )

            >>> # PyArrow Expression: events starting after coordinate 10
            >>> import pyarrow.compute as pc
            >>> expr = pc.greater(
            ...     pc.struct_field(pc.field("start"), "value"),
            ...     10.0
            ... )
            >>> table = timeline.get_timestamp_table_filtered(expr)

            >>> # Combine with C-Maps
            >>> table = timeline.get_timestamp_table_filtered(
            ...     {"event_type": "Note"},
            ...     conversion_maps=["seconds"],
            ... )
        """
        # Extract filtered coordinates
        filtered_coords = self._collect_all_coordinates(
            recursion_limit=recursion_limit,
            event_filter=event_filter,
        )

        # Optionally include boundaries
        if include_boundaries:
            boundary_coords = self._collect_boundary_coordinates(
                recursion_limit=recursion_limit
            )
            if len(filtered_coords) > 0 and len(boundary_coords) > 0:
                combined = pa.concat_arrays([filtered_coords, boundary_coords])
                unique = pc.unique(combined)
                sort_indices = pc.sort_indices(unique)
                axis = pc.take(unique, sort_indices)
            elif len(boundary_coords) > 0:
                axis = boundary_coords
            else:
                axis = filtered_coords
        else:
            axis = filtered_coords

        # Resolve C-Map references using flexible helper
        resolved_maps = self._resolve_conversion_maps(conversion_maps)

        return self._build_timestamp_table(
            axis=axis,
            conversion_maps=resolved_maps if resolved_maps else None,
            recursion_limit=recursion_limit,
        )

    def get_timestamps_filtered(
        self,
        event_filter: dict[str, Any] | pc.Expression,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_boundaries: bool = False,
    ) -> pd.DataFrame:
        """Generate timestamps for filtered events as a pandas DataFrame.

        Convenience wrapper around get_timestamp_table_filtered() for users
        who prefer working with pandas.

        Args:
            event_filter: Filter to apply (dict for simple, pc.Expression for complex).
            conversion_maps: C-Maps to include as columns (see get_timestamp_table).
            recursion_limit: Maximum depth for child traversal.
            include_boundaries: If True, include timeline boundary coordinates.

        Returns:
            pandas DataFrame with timestamps for filtered events.

        Examples:
            >>> df = timeline.get_timestamps_filtered({"event_type": "Note"})
            >>> df.head()
        """
        table = self.get_timestamp_table_filtered(
            event_filter=event_filter,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_boundaries=include_boundaries,
        )
        return table.to_pandas()

    def export_to_csv(
        self,
        filepath: str,
        coordinates: pa.Array | np.ndarray | list[float] | None = None,
        conversion_maps: ConversionMapsSpec = True,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
        *,
        columns: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
        units: bool = True,
        sep: str = ",",
        header: bool = True,
        index: bool = False,
    ) -> int:
        """Export timeline data to a CSV file.

        This is a convenience method that generates a timestamp DataFrame and
        writes it to a CSV file. For more control over the output, use
        to_dataframe() and save manually.

        Args:
            filepath: Output CSV file path.
            coordinates: Explicit coordinates to use as the axis.
            conversion_maps: C-Maps to include as columns. Defaults to True (all).
            recursion_limit: Maximum depth for child traversal.
            include_events: If True and coordinates is None, extract from events.
            include_boundaries: If True, include timeline boundary coordinates.
            columns: How to name the columns (see to_dataframe).
            units: If True (default), append units to column names.
            sep: Field separator. Default "," (comma).
            header: If True (default), write column headers.
            index: If True, write row indices. Default False.

        Returns:
            Number of rows written.

        Examples:
            >>> timeline.export_to_csv("timestamps.csv")
            100

            >>> # Tab-separated, no header
            >>> timeline.export_to_csv("data.tsv", sep="\\t", header=False)
            100
        """
        df = self.to_dataframe(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
            columns=columns,
            units=units,
        )
        df.to_csv(filepath, sep=sep, header=header, index=index)
        return len(df)

    # endregion

    # region Regions — Unified verb x noun API

    # -- add (pre-existing) / create (from parameters) --

    def add_region(
        self,
        region_or_name: Region | str,
        start: CoordinateValue | Coordinate | None = None,
        end: CoordinateValue | Coordinate | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> Region:
        """Add or create a named Region on this timeline.

        Overloaded for backward compatibility:
        - ``add_region(Region)`` — attach a pre-existing Region object.
        - ``add_region(name, start, end)`` — delegate to :meth:`create_region`.

        Under the unified verb×noun API, ``add`` means "attach an existing
        object" while ``create`` means "construct + attach + return".

        Args:
            region_or_name: A Region object (new) or a string name (legacy).
            start: Start coordinate (only when region_or_name is a string).
            end: End coordinate (only when region_or_name is a string).
            meta: Optional metadata dictionary.

        Returns:
            The Region object (either the one passed in or the newly created one).

        Raises:
            ValueError: If region name already exists, end < start, or
                arguments are inconsistent.
            RuntimeError: If timeline is locked.

        Examples:
            >>> # New API — attach a pre-existing Region
            >>> r = Region("Chorus", Coordinate(10, TimeUnit.seconds),
            ...            Coordinate(30, TimeUnit.seconds))
            >>> tl.add_region(r)

            >>> # Legacy API (delegates to create_region)
            >>> tl.add_region("Verse", 30, 50, meta={"repeat": 2})
        """
        if isinstance(region_or_name, Region):
            return self._add_existing_region(region_or_name)
        # Legacy path: string name + positional start/end
        if start is None or end is None:
            raise ValueError(
                "add_region(name, start, end) requires both start and end. "
                "Pass a Region object for the single-argument form."
            )
        return self.create_region(region_or_name, start, end, meta=meta)

    def _add_existing_region(self, region: Region) -> Region:
        """Attach a pre-existing Region object to this timeline.

        Args:
            region: The Region to attach.

        Returns:
            The same Region object.

        Raises:
            ValueError: If a region with the same name already exists or
                the region's unit does not match the timeline's unit.
            RuntimeError: If timeline is locked.
        """
        self._check_not_locked("add region")

        if region.unit != self._unit:
            raise ValueError(
                f"Region unit '{region.unit}' does not match "
                f"timeline unit '{self._unit}'"
            )

        if region.name in self._regions:
            raise ValueError(f"Region '{region.name}' already exists")

        self._regions[region.name] = region
        self._logger.debug(
            f"Added region '{region.name}' "
            f"[{region.start.value}, {region.end.value})"
        )
        return region

    def create_region(
        self,
        name: str,
        start: CoordinateValue | Coordinate,
        end: CoordinateValue | Coordinate,
        *,
        meta: dict[str, Any] | None = None,
    ) -> Region:
        """Create a new named Region and attach it to this timeline.

        Under the unified verb×noun API, ``create`` constructs a new object,
        attaches it, and returns it.

        Args:
            name: Unique name for this region.
            start: Start coordinate.
            end: End coordinate (must be >= start).
            meta: Optional metadata dictionary.

        Returns:
            The created Region object.

        Raises:
            ValueError: If name already exists or end < start.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_region("Chorus", 10.0, 30.0)
            >>> tl.create_region("Verse", 30.0, 50.0, meta={"repeat": 2})
        """
        self._check_not_locked("create region")

        if name in self._regions:
            raise ValueError(f"Region '{name}' already exists")

        start_coord = self._make_coordinate(start)
        end_coord = self._make_coordinate(end)

        region = Region(
            name=name,
            start=start_coord,
            end=end_coord,
            meta=meta or {},
        )

        self._regions[name] = region
        self._logger.debug(
            f"Created region '{name}' [{start_coord.value}, {end_coord.value})"
        )
        return region

    # -- create_regions_* bulk factories --

    def create_regions_from_boundaries(
        self,
        boundaries: Sequence[CoordinateValue],
        *,
        names: Sequence[str] | None = None,
        name_format: str = "{prefix}_{n}",
        prefix: str = "section",
    ) -> list[Region]:
        """Create contiguous regions from boundary coordinates.

        Given k+1 sorted boundary coordinates, creates k regions where
        region_i spans [boundaries[i], boundaries[i+1]).

        Args:
            boundaries: k+1 monotonically increasing coordinates.
            names: Explicit names for the k regions. Mutually exclusive
                with name_format/prefix.
            name_format: Format string. Placeholders: {prefix}, {i} (0-based),
                {n} (1-based).
            prefix: Prefix for auto-generated names.

        Returns:
            List of k Region objects in boundary order.

        Raises:
            ValueError: If fewer than 2 boundaries or not monotonically
                increasing.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_regions_from_boundaries(
            ...     [0, 30, 60, 90],
            ...     prefix="movement",
            ... )
            [Region('movement_1', 0-30), Region('movement_2', 30-60),
             Region('movement_3', 60-90)]
        """
        self._check_not_locked("create regions from boundaries")

        if len(boundaries) < 2:
            raise ValueError(
                f"Need at least 2 boundary coordinates, got {len(boundaries)}"
            )

        coords = [float(b) for b in boundaries]
        for i in range(1, len(coords)):
            if coords[i] <= coords[i - 1]:
                raise ValueError(
                    f"Boundaries must be monotonically increasing: "
                    f"boundaries[{i - 1}]={coords[i - 1]} >= "
                    f"boundaries[{i}]={coords[i]}"
                )

        n_regions = len(coords) - 1
        if names is not None:
            if len(names) != n_regions:
                raise ValueError(
                    f"Expected {n_regions} names for {n_regions} regions, "
                    f"got {len(names)}"
                )
            region_names = list(names)
        else:
            region_names = [
                name_format.format(prefix=prefix, i=i, n=i + 1)
                for i in range(n_regions)
            ]

        result: list[Region] = []
        for i in range(n_regions):
            region = self.create_region(region_names[i], coords[i], coords[i + 1])
            result.append(region)
        return result

    def create_regions_by_grouping(
        self,
        column: str,
        *,
        name_format: str = "{value}",
    ) -> list[Region]:
        """Create regions by grouping *adjacent* events on a column value.

        For each *run* of consecutive events that share the same value in the
        specified column, creates a region spanning the run's coordinate extent
        ``[min_start, max_end)``. Only adjacent events with the same value are
        grouped — non-adjacent occurrences of the same value produce separate
        regions.

        This "run-length" semantics is essential for musical data where, e.g.,
        the same time signature may recur after a change (4/4 → 3/4 → 4/4)
        and each occurrence should be its own region.

        Args:
            column: Event column name to group by.
            name_format: Format string. Placeholders: {value}, {i} (0-based),
                {n} (1-based), {run} (1-based run index for this value).

        Returns:
            List of Region objects ordered by start coordinate.

        Raises:
            ValueError: If column does not exist in events.
            RuntimeError: If timeline is locked.

        Examples:
            >>> # Time-signature regions (adjacent grouping)
            >>> tl.create_regions_by_grouping("timesig")
            [Region('4/4', 0-64), Region('3/4', 64-88), Region('4/4', 88-120)]
        """
        self._check_not_locked("create regions by grouping")

        # Collect events sorted by start coordinate
        events_sorted = self._sorted_event_dicts()
        if not events_sorted:
            return []

        # Check column exists
        first_event = events_sorted[0]
        if column not in first_event:
            raise ValueError(
                f"Column '{column}' not found in events. "
                f"Available columns: {list(first_event.keys())}"
            )

        # Build runs of adjacent equal values
        runs: list[tuple[Any, float, float]] = []  # (value, start, end)
        value_counts: dict[Any, int] = {}

        current_value = None
        run_start = 0.0
        run_end = 0.0

        for event in events_sorted:
            val = event.get(column)
            # Normalize struct values
            if isinstance(val, dict) and "value" in val:
                val = val["value"]

            ev_start = self._extract_coord_value(event, "start", "instant")
            ev_end = self._extract_coord_value(event, "end") or ev_start

            if val != current_value:
                # Close previous run
                if current_value is not None:
                    runs.append((current_value, run_start, run_end))
                # Start new run
                current_value = val
                run_start = ev_start if ev_start is not None else 0.0
                run_end = ev_end if ev_end is not None else run_start
            else:
                # Extend current run
                if ev_end is not None:
                    run_end = max(run_end, ev_end)

        # Close last run
        if current_value is not None:
            runs.append((current_value, run_start, run_end))

        # Pre-compute total occurrences per value to detect ambiguity
        from collections import Counter

        total_occurrences = Counter(val for val, _, _ in runs)

        # Create regions
        result: list[Region] = []
        for i, (value, start, end) in enumerate(runs):
            value_counts.setdefault(value, 0)
            value_counts[value] += 1
            region_name = name_format.format(
                value=value,
                i=i,
                n=i + 1,
                run=value_counts[value],
            )
            # Auto-disambiguate if the default format would produce duplicates
            if region_name in self._regions and total_occurrences[value] > 1:
                region_name = f"{region_name}_run{value_counts[value]}"
            region = self.create_region(region_name, start, end)
            result.append(region)

        return result

    def create_regions_by_splitting(
        self,
        predicate: str | dict[str, Any] | Callable[[dict], bool],
        *,
        names: Sequence[str] | None = None,
        name_format: str = "{prefix}_{n}",
        prefix: str = "section",
        include_before_first: bool = True,
        include_after_last: bool = True,
    ) -> list[Region]:
        """Create contiguous regions by splitting at events matching a predicate.

        Finds events matching the predicate, uses their coordinates as split
        points, creates contiguous regions between consecutive split points.

        The predicate can be:
        - A string: column name. Events where this column is truthy (non-null,
          non-empty, non-zero) are split points.
        - A dict: keyword filters in the same style as ``EventData.filter()``.
          For example ``{"breaks": "section"}`` selects events whose ``breaks``
          column equals ``"section"``.
        - A callable: receives event dict, returns True for split points.

        For each matching event the split coordinate is the event's ``end``
        (interval events) or ``start``/``instant`` (instant events).

        Args:
            predicate: Column name, filter dict, or callable identifying
                split-point events.
            names: Explicit region names.
            name_format: Format string. Placeholders: {prefix}, {i}, {n}.
            prefix: Prefix for auto-generated names.
            include_before_first: Create a region from timeline origin to
                first split point.
            include_after_last: Create a region from last split point to
                timeline end.

        Returns:
            List of contiguous Region objects in coordinate order.

        Raises:
            RuntimeError: If timeline is locked.

        Examples:
            >>> # Split at section breaks
            >>> tl.create_regions_by_splitting("breaks", prefix="movement")

            >>> # Split at specific break types
            >>> tl.create_regions_by_splitting(
            ...     {"breaks": "section"}, prefix="movement"
            ... )
        """
        self._check_not_locked("create regions by splitting")

        # Resolve predicate to a callable
        match_fn = self._resolve_predicate(predicate)

        # Find split coordinates
        split_coords: list[float] = []
        events_sorted = self._sorted_event_dicts()

        for event in events_sorted:
            if match_fn(event):
                # Use end coordinate for intervals, start for instants
                coord = self._extract_coord_value(event, "end")
                if coord is None:
                    coord = self._extract_coord_value(event, "start", "instant")
                if coord is not None:
                    split_coords.append(coord)

        # Deduplicate and sort
        split_coords = sorted(set(split_coords))

        # Build boundary list
        boundaries: list[float] = []
        if include_before_first:
            boundaries.append(float(self.origin.value))
        boundaries.extend(split_coords)
        if include_after_last:
            boundaries.append(float(self.length.value))

        # Deduplicate again (split point might coincide with origin/end)
        boundaries = sorted(set(boundaries))

        if len(boundaries) < 2:
            return []

        # Determine names
        n_regions = len(boundaries) - 1
        if names is not None:
            if len(names) != n_regions:
                raise ValueError(f"Expected {n_regions} names, got {len(names)}")
            region_names = list(names)
        else:
            region_names = [
                name_format.format(prefix=prefix, i=i, n=i + 1)
                for i in range(n_regions)
            ]

        result: list[Region] = []
        for i in range(n_regions):
            region = self.create_region(
                region_names[i], boundaries[i], boundaries[i + 1]
            )
            result.append(region)
        return result

    def _resolve_predicate(
        self,
        predicate: str | dict[str, Any] | Callable[[dict], bool],
    ) -> Callable[[dict], bool]:
        """Convert a predicate specification to a callable.

        Supports three forms:
        - str: column name — truthy test on that column's value.
        - dict: keyword filters (same semantics as ``EventData.filter``).
        - callable: used directly.

        Args:
            predicate: The predicate specification.

        Returns:
            A callable ``(event_dict) -> bool``.
        """
        if callable(predicate) and not isinstance(predicate, (str, dict)):
            return predicate

        if isinstance(predicate, str):
            col = predicate

            def _match_truthy(event: dict) -> bool:
                val = event.get(col)
                if val is None:
                    return False
                if isinstance(val, dict) and "value" in val:
                    val = val["value"]
                if isinstance(val, str):
                    return bool(val.strip())
                return bool(val)

            return _match_truthy

        if isinstance(predicate, dict):
            filters = predicate

            def _match_dict(event: dict) -> bool:
                for key, expected in filters.items():
                    val = event.get(key)
                    if val is None:
                        return False
                    if isinstance(val, dict) and "value" in val:
                        val = val["value"]
                    # Support list of acceptable values
                    if isinstance(expected, (list, tuple, set, frozenset)):
                        if val not in expected:
                            return False
                    else:
                        if val != expected:
                            return False
                return True

            return _match_dict

        raise TypeError(
            f"predicate must be str, dict, or callable, got {type(predicate)}"
        )

    def _sorted_event_dicts(self) -> list[dict[str, Any]]:
        """Return events as dicts sorted by start coordinate."""
        events_list = list(self.get_events(include_segments=False))
        events_list.sort(
            key=lambda e: self._extract_coord_value(e, "start", "instant") or 0.0
        )
        return events_list

    # -- read operations --

    def get_region(self, name: str) -> Region:
        """Get a Region by name.

        Args:
            name: The region name.

        Returns:
            The Region object.

        Raises:
            KeyError: If no region with that name exists.
        """
        if name not in self._regions:
            raise KeyError(f"No region named '{name}'")
        return self._regions[name]

    def get_regions_at(
        self,
        coord: CoordinateValue | Coordinate,
    ) -> list[Region]:
        """Return all regions containing the given coordinate.

        A region contains coord if region.start <= coord < region.end
        (left-inclusive, right-exclusive).

        Args:
            coord: The coordinate to query.

        Returns:
            List of Region objects containing coord, ordered by start
            coordinate. Empty list if no regions contain coord.

        Examples:
            >>> tl.get_regions_at(75.0)
            [Region('verse_1', 30-90), Region('chorus', 60-120)]
        """
        coord_val = float(coord.value if isinstance(coord, Coordinate) else coord)
        matching = [r for r in self._regions.values() if r.contains(coord_val)]
        matching.sort(key=lambda r: float(r.start.value))
        return matching

    def has_region(self, name: str) -> bool:
        """Check if a region exists.

        Args:
            name: Name of the region.

        Returns:
            True if the region exists.
        """
        return name in self._regions

    def iter_regions(self) -> Iterator[Region]:
        """Iterate over all regions in insertion order.

        Yields:
            Region objects.
        """
        yield from self._regions.values()

    @property
    def n_regions(self) -> int:
        """Number of regions on this timeline."""
        return len(self._regions)

    def list_regions(self) -> list[str]:
        """List all region names.

        Returns:
            List of region names in insertion order.
        """
        return list(self._regions.keys())

    # endregion

    # region Children — Unified verb x noun API

    def create_child_from_region(
        self,
        region_name: str,
        *,
        copy_events: bool = True,
        uid: str | None = None,
    ) -> "Timeline":
        """Create a child timeline from a named region (partitioning).

        The child's length = region duration, offset = region start.
        The child's class matches the parent's concrete class.
        If copy_events, events in [start, end) are copied with adjusted
        coordinates.

        Args:
            region_name: Name of an existing region.
            copy_events: Copy events within the region to the child.
            uid: Explicit child ID. Defaults to region name.

        Returns:
            The newly created and attached child timeline.

        Raises:
            KeyError: If region_name not found.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_regions_by_splitting("breaks", prefix="movement")
            >>> mov4 = tl.create_child_from_region("movement_4")
        """
        region = self._regions.get(region_name)
        if region is None:
            raise KeyError(f"Region '{region_name}' not found on timeline '{self._id}'")

        self._check_not_locked("create child from region")

        child = self.__class__(
            length=region.duration,
            unit=self._unit,
            number_type=self._number_type,
            uid=uid or region_name,
            name=region.name,
        )

        if copy_events:
            self._copy_events_to_child(child, region)

        self.add_child(child, offset=region.start)
        return child

    def create_children_from_regions(
        self,
        region_names: Sequence[str] | None = None,
        *,
        copy_events: bool = True,
    ) -> list["Timeline"]:
        """Create children from multiple regions (batch partitioning).

        Each region becomes a child. Regions may overlap — resulting children
        are independent.

        Args:
            region_names: Region names. None = all regions in insertion order.
            copy_events: Copy events to children.

        Returns:
            List of child timelines in region order.

        Raises:
            KeyError: If any region_name not found.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.create_regions_by_grouping("@pageIndex",
            ...                               name_format="page_{value}")
            >>> tl.create_children_from_regions()  # All pages as children
        """
        if region_names is None:
            region_names = list(self._regions.keys())

        result: list[Timeline] = []
        for name in region_names:
            child = self.create_child_from_region(name, copy_events=copy_events)
            result.append(child)
        return result

    def get_children_at(
        self,
        coord: CoordinateValue | Coordinate,
    ) -> list["Timeline"]:
        """Return all children whose extent contains the given coordinate.

        A child contains coord if offset <= coord < offset + child.length.

        Args:
            coord: The coordinate to query.

        Returns:
            List of child Timeline objects, ordered by offset.
            Empty list if no children contain coord.
        """
        coord_val = float(coord.value if isinstance(coord, Coordinate) else coord)
        matching: list[tuple[float, Timeline]] = []
        for child_id, child in self._children.items():
            offset = float(self._child_offsets[child_id].value)
            if offset <= coord_val < offset + float(child.length.value):
                matching.append((offset, child))
        matching.sort(key=lambda x: x[0])
        return [child for _, child in matching]

    def list_children(self) -> list[str]:
        """List child timeline IDs.

        Returns:
            List of child IDs in insertion order.
        """
        return list(self._children.keys())

    def has_child(self, child_id: str) -> bool:
        """Check if a child with the given ID exists.

        Args:
            child_id: The child ID to check.

        Returns:
            True if such a child exists.
        """
        return child_id in self._children

    def _copy_events_to_child(
        self,
        child: "Timeline",
        region: Region,
    ) -> None:
        """Copy events within a region to a child, adjusting coordinates.

        Events in [region.start, region.end) are copied with coordinates
        shifted by -region.start so they are relative to the child's origin.

        Args:
            child: The target child timeline.
            region: The region defining the source interval.
        """
        events_in_region = self.get_events(
            min_coord=float(region.start.value),
            max_coord=float(region.end.value),
        )

        adjusted_events = []
        for event in events_in_region:
            adjusted = dict(event)
            for coord_col in ("instant", "start", "end"):
                val = adjusted.get(coord_col)
                if val is not None:
                    if isinstance(val, dict) and "value" in val:
                        adjusted[coord_col] = val["value"] - region.start.value
                    else:
                        adjusted[coord_col] = float(val) - region.start.value
            adjusted_events.append(adjusted)

        if adjusted_events:
            child.add_events(adjusted_events)

    # endregion

    # region Slicing

    def get_slice(
        self,
        start: CoordinateValue,
        end: CoordinateValue,
        *,
        truncate_events: bool = True,
        include_children: bool = True,
        copy_cmaps: bool = True,
    ) -> "Timeline":
        """Extract a portion of this timeline as a new, independent timeline.

        Returns a new timeline containing all events within [start, end).
        The returned timeline has its coordinate origin at 0, with all
        coordinates shifted by -start.

        From the TTA manuscript: slicing creates a new timeline that is a
        structural copy of the specified interval of the source.

        Args:
            start: Start coordinate (inclusive).
            end: End coordinate (exclusive).
            truncate_events: If True (default), interval events straddling
                the slice boundaries are clipped to [start, end). If False,
                events must be fully contained to be included.
            include_children: If True (default), child timelines whose span
                overlaps [start, end) are recursively sliced and included.
            copy_cmaps: If True (default), ConversionMaps are bounded-copied
                for the slice range.

        Returns:
            New Timeline (same concrete subclass) with length = end - start,
            coordinates shifted to [0, end-start).

        Raises:
            ValueError: If start >= end or either is outside timeline bounds.

        Examples:
            >>> source = ContinuousLogicalTimeline(length=100)
            >>> source.add_events([
            ...     {"event_type": "Note", "start": 10, "end": 30},
            ...     {"event_type": "Beat", "instant": 25},
            ... ])
            >>> sliced = source.get_slice(20, 40)
            >>> sliced.length.value  # 40 - 20 = 20
            Fraction(20, 1)
        """
        # Coerce to the timeline's native number type for consistent arithmetic
        nt = self._number_type
        if nt == NumberType.fraction:
            s = Fraction(start)
            e = Fraction(end)
        elif nt == NumberType.int:
            s = int(start)
            e = int(end)
        else:
            s = float(start)
            e = float(end)

        # Validate
        if s >= e:
            raise ValueError(f"start ({s}) must be less than end ({e})")
        if s < 0:
            raise ValueError(
                f"start ({s}) is outside timeline bounds [0, {self._length.value})"
            )
        if e > self._length.value:
            raise ValueError(
                f"end ({e}) is outside timeline bounds [0, {self._length.value}]"
            )

        slice_length = e - s

        # Create new timeline of same concrete class
        sliced = self.__class__(
            length=slice_length,
            unit=self._unit,
            number_type=self._number_type,
        )

        # Copy events with coordinate shifting
        self._copy_events_to_slice(sliced, s, e, truncate_events)

        # Recursively slice children
        if include_children:
            self._copy_children_to_slice(sliced, s, e)

        # Copy conversion maps (bounded to slice range)
        if copy_cmaps:
            self._copy_cmaps_to_slice(sliced, s, e)

        return sliced

    def _copy_events_to_slice(
        self,
        target: "Timeline",
        start: Any,
        end: Any,
        truncate_events: bool,
    ) -> None:
        """Copy events from [start, end) to target with coordinate shifting.

        All coordinates are shifted by -start. Interval events straddling
        boundaries are either truncated or excluded depending on
        truncate_events.

        Note: In the EventData PyArrow schema, all events store their
        coordinate in 'start' (a struct with 'value', 'numerator',
        'denominator' keys). Instant events have 'start' but no 'end'.
        The 'instant' key is only used as input convenience during
        ``add_events()`` and is converted to 'start' internally.

        Args:
            target: The target timeline to receive events.
            start: Start coordinate (inclusive) in source coords.
            end: End coordinate (exclusive) in source coords.
            truncate_events: If True, clip straddling intervals. If False,
                only include fully-contained intervals.
        """
        # Get all events (excluding segments, which are managed via children)
        all_events = self.get_events()

        # Convert start/end to float for comparison with PyArrow struct values
        start_f = float(start)
        end_f = float(end)

        adjusted_events = []
        for event in all_events:
            ev = dict(event)
            temporal = ev.get("temporal_type")

            if temporal == "instant":
                # In EventData, instant events have start={value:...} and end=None
                start_dict = ev.get("start")
                if start_dict is None:
                    continue
                coord = (
                    start_dict["value"] if isinstance(start_dict, dict) else start_dict
                )
                # Left-inclusive, right-exclusive: start <= coord < end
                if coord >= start_f and coord < end_f:
                    shifted = coord - start_f
                    ev["start"] = shifted
                    adjusted_events.append(ev)

            elif temporal == "interval":
                ev_start_dict = ev.get("start")
                ev_end_dict = ev.get("end")
                if ev_start_dict is None or ev_end_dict is None:
                    continue
                ev_start = (
                    ev_start_dict["value"]
                    if isinstance(ev_start_dict, dict)
                    else ev_start_dict
                )
                ev_end = (
                    ev_end_dict["value"]
                    if isinstance(ev_end_dict, dict)
                    else ev_end_dict
                )

                if truncate_events:
                    # Clip to [start, end)
                    clipped_start = max(ev_start, start_f)
                    clipped_end = min(ev_end, end_f)

                    if clipped_start >= clipped_end:
                        continue  # Fully outside

                    shifted_start = clipped_start - start_f
                    shifted_end = clipped_end - start_f
                    ev["start"] = shifted_start
                    ev["end"] = shifted_end
                    ev["duration"] = shifted_end - shifted_start
                    adjusted_events.append(ev)
                else:
                    # Only include fully contained intervals
                    if ev_start >= start_f and ev_end <= end_f:
                        ev["start"] = ev_start - start_f
                        ev["end"] = ev_end - start_f
                        ev["duration"] = (ev_end - start_f) - (ev_start - start_f)
                        adjusted_events.append(ev)

        if adjusted_events:
            target._add_events_unchecked(adjusted_events)

    def _copy_children_to_slice(
        self,
        target: "Timeline",
        start: Any,
        end: Any,
    ) -> None:
        """Recursively slice child timelines that overlap [start, end).

        For each child at offset o with length l, if [o, o+l) overlaps
        [start, end), recursively slice the child at the overlapping range.
        The child's offset in the target is max(0, o - start).

        Args:
            target: The target timeline to receive sliced children.
            start: Start coordinate in source (parent) coords.
            end: End coordinate in source (parent) coords.
        """
        for child_id, child in self._children.items():
            child_offset = self._child_offsets[child_id].value
            child_end = child_offset + child.length.value

            # Check overlap with [start, end)
            overlap_start = max(child_offset, start)
            overlap_end = min(child_end, end)

            if overlap_start >= overlap_end:
                continue  # No overlap

            # Convert to child-local coordinates
            child_local_start = overlap_start - child_offset
            child_local_end = overlap_end - child_offset

            # Recursively slice the child
            sliced_child = child.get_slice(
                child_local_start,
                child_local_end,
                truncate_events=True,
                include_children=True,
                copy_cmaps=True,
            )

            # Offset in the target timeline
            target_offset = overlap_start - start
            target.add_child(sliced_child, offset=target_offset, allow_expansion=True)

    def _copy_cmaps_to_slice(
        self,
        target: "Timeline",
        start: Any,
        end: Any,
    ) -> None:
        """Copy conversion maps to a sliced timeline.

        Currently copies all conversion maps without range bounding.
        Future enhancement: implement bounded C-Map copying for the
        slice coordinate range.

        Args:
            target: The target timeline to receive C-Maps.
            start: Start coordinate in source coords (for future bounded copy).
            end: End coordinate in source coords (for future bounded copy).
        """
        for cmap_id, cmap in self._conversion_maps.items():
            try:
                target.add_conversion_map(cmap)
            except (ValueError, TypeError):
                # Skip incompatible maps (e.g., unit mismatch after slicing)
                self._logger.debug(
                    f"Skipping C-Map '{cmap_id}' during slice: incompatible"
                )

    # endregion

    # region SegmentLine creation — Unified verb x noun API

    def create_segment_line(
        self,
        boundaries: Sequence[CoordinateValue],
        *,
        copy_events: bool = True,
    ) -> "SegmentLine":
        """Create a SegmentLine by segmenting at boundary coordinates.

        Given k+1 sorted coordinates, produces a new SegmentLine with k
        contiguous segments. Each segment's class matches self's class.

        Does NOT modify self. Returns a new independent SegmentLine.

        Args:
            boundaries: k+1 monotonically increasing coordinates.
            copy_events: Copy events into their respective segments.

        Returns:
            A new SegmentLine with k segments.

        Raises:
            ValueError: If fewer than 2 boundaries or not monotonically
                increasing.

        Examples:
            >>> measures = audio_tl.create_segment_line(
            ...     [0.0] + measure_times.tolist() + [float(audio_tl.length)]
            ... )
        """
        from .types import SegmentLine

        if len(boundaries) < 2:
            raise ValueError(
                f"Need at least 2 boundary coordinates, got {len(boundaries)}"
            )

        coords = [float(b) for b in boundaries]
        for i in range(1, len(coords)):
            if coords[i] <= coords[i - 1]:
                raise ValueError(
                    f"Boundaries must be monotonically increasing: "
                    f"boundaries[{i - 1}]={coords[i - 1]} >= "
                    f"boundaries[{i}]={coords[i]}"
                )

        sl = SegmentLine(
            segment_type=self.__class__,
            length=0,
            unit=self._unit,
            number_type=self._number_type,
        )

        for i in range(len(coords) - 1):
            start = coords[i]
            end = coords[i + 1]
            length = end - start

            segment = self.__class__(
                length=length,
                unit=self._unit,
                number_type=self._number_type,
                name=f"segment_{i}",
            )

            if copy_events:
                events_in_range = self.get_events(
                    min_coord=start,
                    max_coord=end,
                )
                adjusted = []
                for event in events_in_range:
                    adj = dict(event)
                    for col in ("instant", "start", "end"):
                        val = adj.get(col)
                        if val is not None:
                            if isinstance(val, dict) and "value" in val:
                                adj[col] = val["value"] - start
                            else:
                                adj[col] = float(val) - start
                    adjusted.append(adj)
                if adjusted:
                    segment.add_events(adjusted)

            sl.append_segment(segment)

        return sl

    def create_segment_line_from_regions(
        self,
        region_names: Sequence[str] | None = None,
        *,
        copy_events: bool = True,
    ) -> "SegmentLine":
        """Create a SegmentLine from contiguous regions.

        Validates that regions are contiguous and non-overlapping
        (each region's end == next region's start).

        Does NOT modify self.

        Args:
            region_names: Ordered region names. None = all regions sorted
                by start coordinate.
            copy_events: Copy events into segments.

        Returns:
            A new SegmentLine.

        Raises:
            ValueError: If regions are not contiguous or empty.

        Examples:
            >>> tl.create_regions_by_grouping("timesig")
            >>> seg_line = tl.create_segment_line_from_regions()
        """
        if region_names is None:
            # Sort regions by start coordinate
            sorted_regions = sorted(
                self._regions.values(), key=lambda r: float(r.start.value)
            )
            region_names = [r.name for r in sorted_regions]

        if not region_names:
            raise ValueError("No regions to create segment line from")

        regions = [self.get_region(name) for name in region_names]

        # Validate contiguity
        for i in range(1, len(regions)):
            prev_end = float(regions[i - 1].end.value)
            curr_start = float(regions[i].start.value)
            if abs(prev_end - curr_start) > 1e-10:
                raise ValueError(
                    f"Regions are not contiguous: '{regions[i - 1].name}' "
                    f"ends at {prev_end} but '{regions[i].name}' starts "
                    f"at {curr_start}"
                )

        # Build boundaries from regions
        boundaries = [float(regions[0].start.value)]
        for r in regions:
            boundaries.append(float(r.end.value))

        # Create the segment line
        sl = self.create_segment_line(boundaries, copy_events=copy_events)

        # Rename segments to match region names
        for i, seg_id in enumerate(sl._segment_order):
            sl._children[seg_id]._name = regions[i].name

        return sl

    def create_segment_line_by_grouping(
        self,
        column: str,
        *,
        copy_events: bool = True,
        name_format: str = "{value}",
    ) -> "SegmentLine":
        """Create a SegmentLine by grouping adjacent events on a column value.

        Groups must form contiguous, non-overlapping spans. This is validated
        and raises if not satisfied.

        Does NOT modify self. Does NOT add intermediate regions to self.

        Args:
            column: Event column to group by.
            copy_events: Copy events into segments.
            name_format: Format string for segment names.

        Returns:
            A new SegmentLine.

        Raises:
            ValueError: If groups are not contiguous.

        Examples:
            >>> systems = page.create_segment_line_by_grouping("spacing_run_id")
        """
        # Build runs (same logic as create_regions_by_grouping but temporary)
        events_sorted = self._sorted_event_dicts()
        if not events_sorted:
            raise ValueError("No events to group")

        first_event = events_sorted[0]
        if column not in first_event:
            raise ValueError(
                f"Column '{column}' not found in events. "
                f"Available columns: {list(first_event.keys())}"
            )

        runs: list[tuple[Any, float, float]] = []
        value_counts: dict[Any, int] = {}

        current_value = None
        run_start = 0.0
        run_end = 0.0

        for event in events_sorted:
            val = event.get(column)
            if isinstance(val, dict) and "value" in val:
                val = val["value"]

            ev_start = self._extract_coord_value(event, "start", "instant")
            ev_end = self._extract_coord_value(event, "end") or ev_start

            if val != current_value:
                if current_value is not None:
                    runs.append((current_value, run_start, run_end))
                current_value = val
                run_start = ev_start if ev_start is not None else 0.0
                run_end = ev_end if ev_end is not None else run_start
            else:
                if ev_end is not None:
                    run_end = max(run_end, ev_end)

        if current_value is not None:
            runs.append((current_value, run_start, run_end))

        # Validate contiguity
        for i in range(1, len(runs)):
            prev_end = runs[i - 1][2]
            curr_start = runs[i][1]
            if abs(prev_end - curr_start) > 1e-10:
                raise ValueError(
                    f"Groups are not contiguous: group "
                    f"'{runs[i - 1][0]}' ends at {prev_end} but group "
                    f"'{runs[i][0]}' starts at {curr_start}"
                )

        # Build boundaries
        if not runs:
            raise ValueError("No groups found")

        boundaries = [runs[0][1]]
        for _, _, end in runs:
            boundaries.append(end)

        sl = self.create_segment_line(boundaries, copy_events=copy_events)

        # Rename segments
        for i, seg_id in enumerate(sl._segment_order):
            value_counts.setdefault(runs[i][0], 0)
            value_counts[runs[i][0]] += 1
            seg_name = name_format.format(
                value=runs[i][0],
                i=i,
                n=i + 1,
                run=value_counts[runs[i][0]],
            )
            sl._children[seg_id]._name = seg_name

        return sl

    def create_segment_line_by_splitting(
        self,
        predicate: str | dict[str, Any] | Callable[[dict], bool],
        *,
        copy_events: bool = True,
        names: Sequence[str] | None = None,
        name_format: str = "{prefix}_{n}",
        prefix: str = "section",
        include_before_first: bool = True,
        include_after_last: bool = True,
    ) -> "SegmentLine":
        """Create a SegmentLine by splitting at events matching a predicate.

        Shortcut for finding split points and creating a SegmentLine directly.
        Does NOT modify self (no intermediate regions are created).

        The predicate follows the same semantics as
        :meth:`create_regions_by_splitting`.

        Args:
            predicate: Column name, filter dict, or callable identifying
                split-point events.
            copy_events: Copy events into segments.
            names: Explicit segment names.
            name_format: Format string for segment names.
            prefix: Prefix for auto-generated names.
            include_before_first: Include segment before first split point.
            include_after_last: Include segment after last split point.

        Returns:
            A new SegmentLine.

        Examples:
            >>> sl = tl.create_segment_line_by_splitting(
            ...     {"breaks": "section"}, prefix="movement"
            ... )
        """
        match_fn = self._resolve_predicate(predicate)

        split_coords: list[float] = []
        events_sorted = self._sorted_event_dicts()

        for event in events_sorted:
            if match_fn(event):
                coord = self._extract_coord_value(event, "end")
                if coord is None:
                    coord = self._extract_coord_value(event, "start", "instant")
                if coord is not None:
                    split_coords.append(coord)

        split_coords = sorted(set(split_coords))

        boundaries: list[float] = []
        if include_before_first:
            boundaries.append(float(self.origin.value))
        boundaries.extend(split_coords)
        if include_after_last:
            boundaries.append(float(self.length.value))

        boundaries = sorted(set(boundaries))

        if len(boundaries) < 2:
            raise ValueError("Not enough split points to create segments")

        sl = self.create_segment_line(boundaries, copy_events=copy_events)

        # Rename segments
        n_segments = sl.n_segments
        if names is not None:
            if len(names) != n_segments:
                raise ValueError(f"Expected {n_segments} names, got {len(names)}")
            seg_names = list(names)
        else:
            seg_names = [
                name_format.format(prefix=prefix, i=i, n=i + 1)
                for i in range(n_segments)
            ]

        for i, seg_id in enumerate(sl._segment_order):
            sl._children[seg_id]._name = seg_names[i]

        return sl

    # endregion

    # region FlowMaps

    def attach_flow_map(self, flow_map: "FlowMap", id: str | None = None) -> None:
        """Attach a FlowMap to this timeline.

        FlowMaps enable coordinate transformation for timelines with flow
        control (repeats, jumps, D.S., D.C., etc.). They are created by
        FlowController and attached to the timeline for later use.

        Design Decision: Timelines store FlowMaps, NOT FlowControllers.
        FlowControllers are factories that produce FlowMaps.

        Args:
            flow_map: The FlowMap to attach.
            id: Identifier for this FlowMap. If None, uses flow_map.id.
                Common values: "default", "atomic", "single".

        Examples:
            >>> controller = ScoreFlowController(measure_data)
            >>> flow_map = controller.create_flow_map()
            >>> timeline.attach_flow_map(flow_map)
            >>> timeline.get_flow_map("default")  # Retrieve later
            FlowMap(default: 5 sections)
        """
        if id is None:
            id = flow_map.id
        self._flow_maps[id] = flow_map
        self._logger.debug(f"Attached FlowMap '{id}'")

    def get_flow_map(self, id: str = "default") -> "FlowMap | None":
        """Get an attached FlowMap by id.

        Args:
            id: Identifier of the FlowMap. Default is "default".

        Returns:
            The FlowMap if found, None otherwise.
        """
        return self._flow_maps.get(id)

    def has_flow_map(self, id: str = "default") -> bool:
        """Check if a FlowMap with the given id is attached.

        Args:
            id: Identifier to check.

        Returns:
            True if a FlowMap with that id exists.
        """
        return id in self._flow_maps

    def list_flow_maps(self) -> list[str]:
        """List all attached FlowMap ids.

        Returns:
            List of id strings.
        """
        return list(self._flow_maps.keys())

    @property
    def n_flow_maps(self) -> int:
        """Number of attached FlowMaps."""
        return len(self._flow_maps)

    def unfold(self, coord: float | int, id: str = "default") -> list[float]:
        """Convert a folded coordinate to unfolded coordinates.

        Convenience method that delegates to the attached FlowMap.
        Since repeats can cause a folded coordinate to appear multiple times
        in the unfolded timeline, this returns a list.

        Args:
            coord: Coordinate in the folded timeline.
            id: Which FlowMap to use.

        Returns:
            List of coordinates in the unfolded timeline.

        Raises:
            ValueError: If no FlowMap with the given id is attached.
        """
        flow_map = self._flow_maps.get(id)
        if flow_map is None:
            raise ValueError(f"No FlowMap attached with id '{id}'")
        return [float(c) for c in flow_map.unfold(coord)]

    def fold(self, coord: float | int, id: str = "default") -> float:
        """Convert an unfolded coordinate to a folded coordinate.

        Convenience method that delegates to the attached FlowMap.

        Args:
            coord: Coordinate in the unfolded timeline.
            id: Which FlowMap to use.

        Returns:
            Coordinate in the folded timeline.

        Raises:
            ValueError: If no FlowMap with the given id is attached,
                        or if the coordinate is outside the flow range.
        """
        flow_map = self._flow_maps.get(id)
        if flow_map is None:
            raise ValueError(f"No FlowMap attached with id '{id}'")
        return float(flow_map.fold(coord))

    # endregion

    # region Future API Stubs

    def add_match(self, match: Any) -> None:
        """Add an alignment Match to this timeline.

        Args:
            match: The Match to add.

        Raises:
            NotImplementedError: Alignment is managed via AlignmentBundle.
        """
        raise NotImplementedError("Alignment is managed via AlignmentBundle")

    def add_break(self, at: Coordinate) -> None:
        """Add a Break (contiguity void) at the specified coordinate.

        Args:
            at: The coordinate for the break.

        Raises:
            NotImplementedError: Breaks will be implemented in a future phase.
        """
        raise NotImplementedError("Breaks will be implemented in a future phase")

    def add_jump(self, from_: Coordinate, to: Coordinate) -> None:
        """Add a Jump (non-linear contiguity) between coordinates.

        Args:
            from_: The jump source coordinate.
            to: The jump target coordinate.

        Raises:
            NotImplementedError: Jumps will be implemented in a future phase.
        """
        raise NotImplementedError("Jumps will be implemented in a future phase")

    # endregion

    # region Display

    def diagram(
        self,
        width: int = 70,
        show_children: bool = True,
        max_children: int = 6,
        unicode: bool = True,
        show: set[str] | None = None,
    ) -> "Diagram":
        """Generate ASCII diagram for this timeline.

        Args:
            width: Total width of the diagram in characters.
            show_children: Whether to show child timelines (one per row).
            max_children: Maximum children to show before truncating.
            unicode: Use Unicode characters (True) or ASCII fallback (False).
            show: Optional set controlling which elements appear. Supported
                values: ``"children"``, ``"regions"``, and ``"cmaps"``
                (attached conversion maps). When ``None``, behaviour is
                exactly as before.

        Returns:
            Diagram object (displays as ASCII in terminal, rich HTML in Jupyter).

        Examples:
            >>> print(timeline.diagram())
            DiscreteGraphicalTimeline[dgt1:1] (11 events, 5 children)
            0 ∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶ 4835 pixels
              ├─ system_1     0   ∶∶∶∶∶∶∶                        967
              ├─ system_2   967          ∶∶∶∶∶∶∶∶               1934
              └─ ...
        """
        from timetoalign.display.ascii import timeline_diagram

        return timeline_diagram(
            self,
            width=width,
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
            show=show,
        )

    # endregion

    # region Magic Methods

    def __len__(self) -> int:
        """Return total number of events (excluding segments)."""
        return self.n_events

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"{self.class_name}("
            f"id={self._id!r}, "
            f"length={self._length.value}, "
            f"unit={self._unit}, "
            f"events={self.n_events}, "
            f"children={self.n_children})"
        )

    def __str__(self) -> str:
        """Return human-readable ASCII diagram of the timeline.

        Uses the diagram() method to generate a visual representation
        showing the timeline bar and any children.
        """
        return str(self.diagram())

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the ASCII diagram in a monospace pre block so it
        renders correctly in notebook output cells.
        """
        return self.diagram()._repr_html_()

    def __contains__(self, item: str | Region | Timeline) -> bool:
        """Check if a region name, child ID, or timeline is part of this timeline.

        Checks all noun types uniformly:
        - ``"name" in tl`` checks regions AND children.
        - ``some_timeline in tl`` checks if it's a child (by identity).
        - ``some_region in tl`` checks if a region with that name exists.
        """
        if isinstance(item, Region):
            return item.name in self._regions
        if isinstance(item, Timeline):
            return item.id in self._children
        # String: check regions first, then children
        return item in self._regions or item in self._children

    # endregion
