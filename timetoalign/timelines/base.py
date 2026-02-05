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
from typing import TYPE_CHECKING, Any, ClassVar, Iterator, Literal

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
from typing_extensions import Self

from timetoalign.core import Coordinate, CoordinateValue, Domain, NumberType, TimeUnit
from timetoalign.core.timestamp import TimeIntervalStamp, TimeStamp
from timetoalign.loader import EventData
from timetoalign.maps import ConversionMap, InterpolationMap

from .regions import Region

if TYPE_CHECKING:
    from .flow import FlowMap

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

    Attributes:
        id: Unique identifier for this timeline.
        unit: The time unit for coordinates (e.g., seconds, quarters, pixels).
        number_type: The numeric type for coordinates (int, float, Fraction).
        domain: The temporal domain (derived from unit).
        origin: The start coordinate (always 0).
        length: The end coordinate.
        is_locked: Whether the timeline can be modified.

    Examples:
        >>> from timetoalign.core import TimeUnit, NumberType
        >>> tl = Timeline(length=100, unit=TimeUnit.seconds)
        >>> tl.add_events([
        ...     {"id": "e1", "temporal_type": "instant", "event_type": "Beat",
        ...      "instant": 0.0},
        ... ])
        >>> len(tl)
        1

        >>> child = Timeline(length=10, unit=TimeUnit.seconds)
        >>> tl.add_child(child, offset=50)
        >>> tl.n_children
        1
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

        # InterpolationMaps for O(log n) coordinate conversion (unified timestamp system)
        # Maps child_id -> InterpolationMap for child<->parent conversion
        self._interpolation_maps: dict[str, InterpolationMap] = {}
        # Maps TimeUnit -> InterpolationMap for unit-based conversion via C-Maps
        self._unit_maps: dict[TimeUnit, InterpolationMap] = {}

        # Region storage (named TimeIntervals)
        # From TTA manuscript: "A Region is a named part of a timeline that is
        # defined by a TimeInterval. Regions are useful for referring to parts
        # of a timeline by name."
        self._regions: dict[str, Region] = {}

        # FlowMap storage (coordinate transformations for flow control)
        # From Phase 3.9: Timelines store FlowMaps (not FlowControllers).
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

        Args:
            rows: List of event dictionaries with keys:
                - id: unique identifier
                - temporal_type: "instant" or "interval"
                - event_type: class name
                - instant: coordinate (for instant events)
                - start, end: coordinates (for interval events)
            allow_expansion: If True, expand timeline if events exceed length.

        Raises:
            ValueError: If events exceed length and expansion not allowed.
            RuntimeError: If timeline is locked and expansion not allowed.
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

        Args:
            rows: Event dictionaries to add.
        """
        if not rows:
            return

        new_data = self._event_data_class.from_dicts(
            rows, self._unit, self._number_type
        )
        self._events.extend(new_data)

    def _get_event_end_coordinate(self, row: dict[str, Any]) -> float:
        """Extract the end coordinate from an event dict.

        Args:
            row: Event dictionary.

        Returns:
            The end coordinate as float.
        """
        if row.get("instant") is not None:
            return float(row["instant"])
        if row.get("end") is not None:
            return float(row["end"])
        if row.get("start") is not None and row.get("duration") is not None:
            return float(row["start"]) + float(row["duration"])
        if row.get("start") is not None:
            return float(row["start"])
        return 0.0

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

    def add_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
        allow_expansion: bool = False,
    ) -> None:
        """Embed a child timeline at the specified offset.

        The child timeline will be locked after being added.
        An InterpolationMap is built for O(log n) coordinate conversion.

        From the TTA manuscript (Section 3.4 - Nested Timelines):
        "A timeline can accommodate not only events but also other timelines,
        called Children, as long as they use the same measuring unit."

        For cross-domain relationships, use TimelineGroup instead.

        Args:
            child: The timeline to embed.
            offset: The start coordinate on this timeline.
            allow_expansion: If True, expand this timeline if needed.

        Raises:
            TypeError: If child is not a Timeline.
            ValueError: If units don't match or would exceed bounds.
            RuntimeError: If this timeline is locked.
        """
        self.validate_child(child, offset)

        offset_coord = self._make_coordinate(offset)
        child_end = offset_coord.value + child.length.value

        # Ensure capacity
        self._ensure_capacity(child_end, allow_expansion)

        # Store child reference
        self._children[child.id] = child
        self._child_offsets[child.id] = offset_coord

        # Build InterpolationMap for bidirectional coordinate conversion
        self._interpolation_maps[child.id] = InterpolationMap.from_child_relationship(
            parent=self,
            child=child,
            offset=float(offset_coord.value),
        )

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
        length: CoordinateValue,
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
            length: Length of the child timeline (in parent's unit).
            offset: The start coordinate on this timeline where the child begins.
            uid: Unique identifier for the child. Auto-generated if None.
            name: Human-readable name for the child.
            allow_expansion: If True, expand parent timeline if needed.

        Returns:
            The newly created and embedded child Timeline.

        Raises:
            ValueError: If offset is negative or child would exceed parent bounds.
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

    # endregion

    # region Conversion Maps

    def add_conversion_map(self, cmap: ConversionMap[Any]) -> None:
        """Add a ConversionMap to this timeline.

        If the map has a target_unit and is a TableMap, an InterpolationMap
        is also built for O(log n) unit-based lookup in the unified timestamp system.

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

        # Build InterpolationMap for unit-based lookup if applicable
        if cmap.target_unit is not None and isinstance(cmap, TableMap):
            self._unit_maps[cmap.target_unit] = InterpolationMap.from_table_map(cmap)

        self._logger.debug(f"Added conversion map '{cmap.id}'")

    def get_conversion_map(
        self, target_unit: TimeUnit | str
    ) -> ConversionMap[Any] | None:
        """Get a map converting to the target unit.

        Args:
            target_unit: The desired output unit.

        Returns:
            A matching ConversionMap, or None if not found.
        """
        target = TimeUnit(target_unit)
        for cmap in self._conversion_maps.values():
            if cmap.target_unit == target:
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

    # region Unified Timestamp API (InterpolationMap-based)

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> InterpolationMap | None:
        """Get InterpolationMap for coordinate conversion to target.

        This method is part of the TimeStampSource protocol.

        Args:
            target_id: Target timeline ID.
            source_id: Source timeline ID (ignored for Timeline, always self).

        Returns:
            InterpolationMap for conversion, or None if not available.
        """
        return self._interpolation_maps.get(target_id)

    def _get_unit_map(self, unit: TimeUnit) -> InterpolationMap | None:
        """Get InterpolationMap for unit-based conversion.

        This method is part of the TimeStampSource protocol.

        Args:
            unit: Target unit.

        Returns:
            InterpolationMap for conversion, or None if no C-Map available.
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

        # Add axis column (root timeline coordinate)
        columns["axis"] = axis
        fields.append(
            pa.field(
                "axis",
                pa.float64(),
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
                pa.float64(),
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
            columns[child.id] = child._compute_local_coordinates(
                axis, offset=float(child_offset.value)
            )
            fields.append(
                pa.field(
                    child.id,
                    pa.float64(),
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
            axis_np = axis.to_numpy()
            for cmap in conversion_maps:
                converted = cmap.convert_array(axis_np)
                columns[cmap.id] = pa.array(converted)
                # C-Map columns include target unit from the C-Map
                target_unit = getattr(cmap, "target_unit", None)
                unit_value = target_unit.value if target_unit else "unknown"
                fields.append(
                    pa.field(
                        cmap.id,
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

    def get_timestamp_table(
        self,
        coordinates: pa.Array | np.ndarray | list[float] | None = None,
        conversion_maps: ConversionMapsSpec = None,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
    ) -> pa.Table:
        """Generate a timestamp table as a PyArrow Table.

        A Timestamp is a cross-section through the timeline hierarchy showing
        synchronous coordinates. This method computes local coordinates for
        each timeline in the hierarchy at each axis coordinate.

        Args:
            coordinates: Explicit coordinates to use as the axis. If None,
                coordinates are extracted from events (and optionally boundaries).
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
        # Resolve coordinates
        if coordinates is not None:
            # Use provided coordinates
            if isinstance(coordinates, pa.Array):
                axis = coordinates
            elif isinstance(coordinates, np.ndarray):
                axis = pa.array(coordinates, type=pa.float64())
            else:
                axis = pa.array(coordinates, type=pa.float64())
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
        coordinates: pa.Array | np.ndarray | list[float] | None = None,
        conversion_maps: ConversionMapsSpec = None,
        recursion_limit: int | None = None,
        include_events: bool = True,
        include_boundaries: bool = False,
    ) -> pd.DataFrame:
        """Generate timestamps as a pandas DataFrame.

        Convenience wrapper around get_timestamp_table() for users who
        prefer working with pandas.

        Args:
            coordinates: Explicit coordinates to use as the axis.
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

        Returns:
            pandas DataFrame with the same schema as get_timestamp_table().

        Examples:
            >>> df = timeline.get_timestamps()
            >>> df.head()
               axis    tl:1   notes  measures
            0   0.0     0.0     0.0       0.0
            1   1.5     1.5     1.5       NaN
            2   4.0     4.0     4.0       4.0

            >>> # Include all attached C-Maps
            >>> df = timeline.get_timestamps(conversion_maps=True)

            >>> # Include specific C-Maps
            >>> df = timeline.get_timestamps(conversion_maps=["inches", "cm"])
        """
        table = self.get_timestamp_table(
            coordinates=coordinates,
            conversion_maps=conversion_maps,
            recursion_limit=recursion_limit,
            include_events=include_events,
            include_boundaries=include_boundaries,
        )
        return table.to_pandas()

    def get_boundary_table(
        self,
        conversion_maps: ConversionMapsSpec = None,
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
        conversion_maps: ConversionMapsSpec = None,
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
        conversion_maps: ConversionMapsSpec = None,
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

    # endregion

    # region Regions

    def add_region(
        self,
        name: str,
        start: CoordinateValue | Coordinate,
        end: CoordinateValue | Coordinate,
        meta: dict[str, Any] | None = None,
    ) -> Region:
        """Add a named Region to this timeline.

        A Region is a named part of a timeline defined by a TimeInterval.
        Regions are NOT timelines - they do not hold events or C-Maps.
        However, they can be used for:
        - Referring to parts of a timeline by name (e.g., "Chorus", "Verse")
        - Partitioning: creating a Child corresponding to a Region

        From the TTA manuscript (Section 3.5):
        "A Region is a named part of a timeline that is defined by a TimeInterval.
        Regions are useful for referring to parts of a timeline by name...
        They can be used for partitioning, i.e., creating a Child corresponding to a Region."

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
            >>> timeline.add_region("Chorus", 10.0, 30.0)
            >>> timeline.add_region("Verse", 30.0, 50.0, meta={"repeat": 2})
        """
        self._check_not_locked("add region")

        if name in self._regions:
            raise ValueError(f"Region '{name}' already exists")

        start_coord = self._make_coordinate(start)
        end_coord = self._make_coordinate(end)

        # Region class validates end >= start in __post_init__
        region = Region(
            name=name,
            start=start_coord,
            end=end_coord,
            meta=meta or {},
        )

        self._regions[name] = region
        self._logger.debug(
            f"Added region '{name}' [{start_coord.value}, {end_coord.value})"
        )
        return region

    def get_region(self, name: str) -> dict[str, Any] | None:
        """Get a Region by name as a dictionary.

        For backwards compatibility, returns a dictionary representation.
        Use get_region_object() for the Region instance.

        Args:
            name: The region name.

        Returns:
            Dict with 'name', 'start', 'end', 'meta' keys, or None if not found.
        """
        region = self._regions.get(name)
        if region is None:
            return None
        return {
            "name": region.name,
            "start": float(region.start.value),
            "end": float(region.end.value),
            "meta": region.meta,
        }

    def get_region_object(self, name: str) -> Region | None:
        """Get a Region object by name.

        Args:
            name: Name of the region.

        Returns:
            The Region object, or None if not found.
        """
        return self._regions.get(name)

    def has_region(self, name: str) -> bool:
        """Check if a region exists.

        Args:
            name: Name of the region.

        Returns:
            True if the region exists.
        """
        return name in self._regions

    def iter_regions(self) -> Iterator[Region]:
        """Iterate over all regions (in undefined order).

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
            List of region names in no particular order.
        """
        return list(self._regions.keys())

    def partition(
        self,
        region_name: str,
        copy_events: bool = True,
    ) -> "Timeline":
        """Create a Child timeline from a Region.

        From TTA manuscript (Section 3.5):
        "Regions can be used to partition a timeline into Children."

        This creates a new timeline covering the region's interval,
        optionally copying events from that interval. The new timeline
        is added as a Child at the region's start offset.

        Args:
            region_name: Name of the region to partition.
            copy_events: If True, copy events within the region to the child.

        Returns:
            The created Child timeline.

        Raises:
            KeyError: If region does not exist.
            RuntimeError: If timeline is locked.

        Examples:
            >>> tl.add_region("Verse", start=0, end=16)
            >>> verse_tl = tl.partition("Verse")
            >>> verse_tl.length
            Coordinate(16, quarters)
        """
        region = self._regions.get(region_name)
        if region is None:
            raise KeyError(f"Region '{region_name}' not found on timeline '{self._id}'")

        self._check_not_locked("partition")

        # Create child timeline with the region's length
        child = self.__class__(
            length=region.duration,
            unit=self._unit,
            number_type=self._number_type,
            name=region.name,
        )

        # Copy events if requested
        if copy_events:
            events_in_region = self.get_events(
                min_coord=float(region.start.value),
                max_coord=float(region.end.value),
            )

            # Adjust coordinates to be relative to the region's start
            adjusted_events = []
            for event in events_in_region:
                adjusted = dict(event)
                for coord_col in ("instant", "start", "end"):
                    val = adjusted.get(coord_col)
                    if val is not None:
                        # Handle coordinate struct or raw value
                        if isinstance(val, dict) and "value" in val:
                            adjusted[coord_col] = val["value"] - region.start.value
                        else:
                            adjusted[coord_col] = float(val) - region.start.value
                adjusted_events.append(adjusted)

            if adjusted_events:
                child.add_events(adjusted_events)

        # Add as child at the region's start offset
        self.add_child(child, offset=region.start)

        return child

    def region_to_child(
        self,
        region_name: str,
        transfer_events: bool = False,
        child_name: str | None = None,
    ) -> "Timeline":
        """Create a Child timeline from a Region.

        DEPRECATED: Use partition() instead. This method is kept for
        backwards compatibility.

        Args:
            region_name: Name of the region to convert.
            transfer_events: If True, copy events within the region to the child.
            child_name: Name for the child timeline (defaults to region name).

        Returns:
            The newly created Child timeline.

        Raises:
            KeyError: If region not found.
        """
        import warnings

        warnings.warn(
            "region_to_child() is deprecated, use partition() instead",
            DeprecationWarning,
            stacklevel=2,
        )

        region = self._regions.get(region_name)
        if region is None:
            raise KeyError(f"Region '{region_name}' not found")

        # Create child of same type
        child = self.__class__(
            length=region.duration,
            unit=self._unit,
            number_type=self._number_type,
            name=child_name or region_name,
        )

        # Add as child
        self.add_child(child, offset=region.start)

        # Copy events if requested
        if transfer_events:
            events_in_region = self.get_events(
                min_coord=float(region.start.value),
                max_coord=float(region.end.value),
            )

            # Adjust coordinates to be relative to the region's start
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

        return child

    # endregion

    # region FlowMaps (Phase 3.9)

    def attach_flow_map(self, flow_map: "FlowMap", id: str | None = None) -> None:
        """Attach a FlowMap to this timeline.

        FlowMaps enable coordinate transformation for timelines with flow
        control (repeats, jumps, D.S., D.C., etc.). They are created by
        FlowController and attached to the timeline for later use.

        Design Decision (Phase 3.9): Timelines store FlowMaps, NOT
        FlowControllers. FlowControllers are factories that produce FlowMaps.

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
            NotImplementedError: Alignment will be implemented in Phase 6.
        """
        raise NotImplementedError("Alignment will be implemented in Phase 6")

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
    ) -> str:
        """Generate ASCII diagram for this timeline.

        Args:
            width: Total width of the diagram in characters.
            show_children: Whether to show child timelines (one per row).
            max_children: Maximum children to show before truncating.
            unicode: Use Unicode characters (True) or ASCII fallback (False).

        Returns:
            Multi-line string with ASCII diagram.

        Examples:
            >>> print(timeline.diagram())
            DiscreteGraphicalTimeline[dgt1:1] (11 events, 5 children)
            0 :::::::::::::::::::::::::::::::::::::::::::::: 4835 pixels
              ├─ system_1     0   :::::::                        967
              ├─ system_2   967          ::::::::               1934
              └─ ...
        """
        from timetoalign.display.ascii import timeline_diagram

        return timeline_diagram(
            self,
            width=width,
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
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
        return self.diagram()

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the ASCII diagram in a monospace pre block so it
        renders correctly in notebook output cells.
        """
        import html

        diagram_text = html.escape(self.diagram())
        return f'<pre style="font-family: monospace; line-height: 1.2;">{diagram_text}</pre>'

    def __contains__(self, item: str | Timeline) -> bool:
        """Check if a child (by ID or object) is in this timeline."""
        if isinstance(item, Timeline):
            return item.id in self._children
        return item in self._children

    # endregion
