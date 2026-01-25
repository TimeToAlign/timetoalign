"""Timeline: The central object of TimeToAlign!

A Timeline is a positive coordinate axis defined by an origin (zero) and a
measuring unit. It can hold events (via an EventStore) and nested child
timelines (segments) that share the same coordinate type.

Design principles:
- Events stored in PyArrow-based EventStore (no flyweight pattern)
- Children stored as direct object references AND as segment events
- Unit validation at add-time prevents coordinate type mismatches
- Locking mechanism prevents modification when embedded as child
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Iterator, Literal

from typing_extensions import Self

from timetoalign.core import Coordinate, CoordinateValue, Domain, NumberType, TimeUnit
from timetoalign.loader import EventStore
from timetoalign.maps import ConversionMap

if TYPE_CHECKING:
    pass

module_logger = logging.getLogger(__name__)

# Module-level counter for unique ID generation
_TIMELINE_COUNTER: dict[str, int] = {}

# region Constants

# Event type name for segment events in the EventStore
SEGMENT_EVENT_TYPE = "Segment"

# Traversal order options for iterating children
TraversalOrder = Literal["sorted", "depth_first", "breadth_first"]

# endregion


class Timeline:
    """A positive coordinate axis with events and nested child timelines.

    A Timeline represents a temporal dimension in one of three domains
    (Logical, Physical, Graphical) with either continuous or discrete
    coordinates. It stores events in an EventStore and can contain
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

    # EventStore class to use (subclasses can override for domain-specific stores)
    _event_store_class: ClassVar[type[EventStore]] = EventStore

    # endregion

    # region Initialization

    def __init__(
        self,
        length: CoordinateValue = 0,
        unit: TimeUnit | str | None = None,
        number_type: NumberType | str | None = None,
        id_prefix: str = "tl",
        uid: str | None = None,
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
        self._meta = dict(meta) if meta else {}

        # Event storage
        self._events = self._event_store_class.empty(self._unit, self._number_type)

        # Child timeline storage
        self._children: dict[str, Timeline] = {}
        self._child_offsets: dict[str, Coordinate] = {}

        # Conversion maps
        self._conversion_maps: dict[str, ConversionMap[Any]] = {}

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
    def from_event_store(
        cls,
        store: EventStore,
        **kwargs: Any,
    ) -> Self:
        """Create a Timeline from an existing EventStore.

        Args:
            store: The EventStore containing events.
            **kwargs: Additional arguments passed to __init__ (except unit/number_type).

        Returns:
            A new Timeline wrapping the EventStore.
        """
        coord_range = store.coordinate_range()
        length = coord_range[1] if coord_range else 0

        timeline = cls(
            length=length,
            unit=store.unit,
            number_type=store.number_type,
            **kwargs,
        )
        timeline._events = store
        return timeline

    # endregion

    # region Properties - Identity

    @property
    def id(self) -> str:
        """Unique identifier for this timeline."""
        return self._id

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
    def events(self) -> EventStore:
        """The underlying EventStore (read-only access)."""
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

        new_store = self._event_store_class.from_dicts(
            rows, self._unit, self._number_type
        )
        self._events.extend(new_store)

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
    ) -> EventStore:
        """Filter and retrieve events.

        Args:
            temporal_type: Filter by "instant" or "interval".
            event_type: Filter by event type name.
            include_segments: If True, include segment events. Default False.
            min_coord: Minimum coordinate (inclusive).
            max_coord: Maximum coordinate (exclusive).

        Returns:
            A filtered EventStore.
        """
        result = self._events

        if temporal_type is not None:
            result = result.filter(temporal_type=temporal_type)

        if event_type is not None:
            result = result.filter(event_type=event_type)

        if not include_segments:
            # Exclude segment events by getting all and filtering
            # Note: This could be optimized with a NOT filter
            segment_store = result.filter(event_type=SEGMENT_EVENT_TYPE)
            if len(segment_store) > 0:
                # Filter by getting non-segment events
                result = EventStore.from_dicts(
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

    # endregion

    # region Child Management

    def validate_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
    ) -> None:
        """Validate that a child can be added at the given offset.

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
                f"parent unit '{self._unit}'"
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

        # Lock the child
        child._locked = True

        # Add segment event to EventStore
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

        Args:
            cmap: The ConversionMap to add.

        Raises:
            ValueError: If the map's source unit is incompatible.
        """
        if cmap.source_unit is not None and cmap.source_unit != self._unit:
            raise ValueError(
                f"Map source unit '{cmap.source_unit}' does not match "
                f"timeline unit '{self._unit}'"
            )
        self._conversion_maps[cmap.id] = cmap
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
        values: Any,
        target_unit: TimeUnit | str,
    ) -> Any:
        """Convert coordinates to another unit using attached C-Maps.

        Args:
            values: Coordinates to convert (scalar, array, or Coordinate).
            target_unit: Target unit.

        Returns:
            Converted values in the target unit.

        Raises:
            ValueError: If no suitable map is found.
        """
        target = TimeUnit(target_unit)
        cmap = self.get_conversion_map(target)
        if cmap is None:
            raise ValueError(
                f"No conversion map found from '{self._unit}' to '{target}'"
            )
        return cmap(values)

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
        """Return human-readable string."""
        return f"{self.class_name}[{self._id}]: 0-{self._length.value} {self._unit}"

    def __contains__(self, item: str | Timeline) -> bool:
        """Check if a child (by ID or object) is in this timeline."""
        if isinstance(item, Timeline):
            return item.id in self._children
        return item in self._children

    # endregion
