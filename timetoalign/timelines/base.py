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

from typing_extensions import Self

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    Domain,
    NumberType,
    TimeUnit,
    rational_to_wire,
    wire_to_rational,
)
from timetoalign.maps import ConversionMap
from timetoalign.storage import EventData

from .engines import (
    ChildrenMixin,
    ConversionMapsMixin,
    EventsMixin,
    ExternalReferencesMixin,
    RegionsMixin,
    SegmentsMixin,
    TabularExportMixin,
)
from .engines import children as _children_engine
from .engines import conversion as _conversion_engine
from .engines import (
    empty_external_reference_table,
)
from .regions import Region

if TYPE_CHECKING:
    from timetoalign.display.ascii import Diagram

module_logger = logging.getLogger(__name__)

# Module-level counter for unique ID generation
_TIMELINE_COUNTER: dict[str, int] = {}

# region Constants

# Event type name for segment events in the EventData
SEGMENT_EVENT_TYPE = "Segment"

# Traversal order options for iterating children
TraversalOrder = Literal["sorted", "depth_first", "breadth_first"]

# endregion


class Timeline(
    EventsMixin,
    ExternalReferencesMixin,
    ChildrenMixin,
    ConversionMapsMixin,
    TabularExportMixin,
    RegionsMixin,
    SegmentsMixin,
):
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

    # Serialized class tag -> timeline subclass. Timeline itself is handled
    # directly; every subclass registers automatically when defined.
    _registry: ClassVar[dict[str, type["Timeline"]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Register a timeline subclass under its serialized class tag."""
        super().__init_subclass__(**kwargs)
        tag = cls.__name__
        registered = Timeline._registry.get(tag)
        if registered is not None and registered is not cls:
            raise ValueError(
                f"Timeline tag {tag!r} is already registered to {registered!r}; "
                f"cannot register {cls!r}."
            )
        Timeline._registry[tag] = cls

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

        # Incoming external references (annotations pointing at own events)
        self._external_references = empty_external_reference_table()

        # Child timeline storage
        self._children: dict[str, Timeline] = {}
        self._child_offsets: dict[str, Coordinate] = {}

        # Conversion maps
        self._conversion_maps: dict[str, ConversionMap[Any]] = {}

        # Maps TimeUnit -> the ConversionMap registered for that unit via
        # add_conversion_map(), so that any C-Map with a target_unit is
        # available in the TimeStamp system.
        self._unit_maps: dict[TimeUnit, ConversionMap[Any]] = {}

        # Region storage (named TimeIntervals)
        # From TTA manuscript: "A Region is a named part of a timeline that is
        # defined by a TimeInterval. Regions are useful for referring to parts
        # of a timeline by name."
        self._regions: dict[str, Region] = {}

        # FlowMap storage (coordinate transformations for flow control)
        # Timelines store FlowMaps (not FlowControllers).
        # FlowMaps enable unfold/fold coordinate conversion for timelines
        # that have flow control (repeats, jumps, etc.).
        self._flow_maps = {}

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
        max_coord: Any = 0
        for row in rows:
            if row.get("instant") is not None:
                max_coord = max(max_coord, cls._coord_to_value(row["instant"]))
            if row.get("end") is not None:
                max_coord = max(max_coord, cls._coord_to_value(row["end"]))
            elif row.get("start") is not None and row.get("duration") is not None:
                start = cls._coord_to_value(row["start"])
                duration = cls._coord_to_value(row["duration"])
                max_coord = max(max_coord, start + duration)

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
        Use this for user-facing displays (e.g., timestamp field headers).
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
    def length(self, value: CoordinateSpec) -> None:
        """Set the timeline length.

        Args:
            value: New length value.

        Raises:
            RuntimeError: If timeline is locked.
            ValueError: If new length is less than current content.
        """
        self._check_not_locked("set length")

        new_length = self.resolve_coordinate(value)

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

    # endregion

    # region Event Management

    @staticmethod
    def _coord_to_value(value: Any) -> Any:
        """Return a coordinate value without discarding an exact ratio."""
        if isinstance(value, dict):
            if (
                value.get("numerator") is not None
                and value.get("denominator") is not None
            ):
                return wire_to_rational(value)
            return value["value"]
        return value

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

    # endregion

    # region Content Inspection

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

    def to_dict(
        self,
        *,
        events: bool = False,
        external_references: bool = False,
    ) -> dict[str, Any]:
        """Convert timeline to a dictionary for serialization.

        The default output describes the timeline's structure only: the
        ``"events"`` and ``"external_references"`` keys are **absent**
        unless explicitly requested, which keeps the payload small for the
        common case of persisting a hierarchy rather than its contents.

        Coordinate-valued members — ``length`` and every child
        ``offset`` — are emitted as the canonical rational wire dict
        (:func:`~timetoalign.core.rational_to_wire`), so the result is
        JSON-serializable whatever the timeline's number type, and
        ``Fraction`` coordinates survive the round trip exactly.

        Args:
            events: If True, include an ``"events"`` key holding this
                timeline's event rows.
            external_references: If True, include an
                ``"external_references"`` key holding the reference table
                as a list of row dicts (``access_points`` as a nested list
                of ``{"uri": ..., "kind": ...}`` dicts). Included even
                when the table is empty.

        Returns:
            A JSON-serializable dictionary representation of the timeline.

        Examples:
            >>> "events" in tl.to_dict()
            False
            >>> "events" in tl.to_dict(events=True)
            True
        """
        children_data = {}
        for child_id, child in self._children.items():
            children_data[child_id] = {
                "offset": rational_to_wire(self._child_offsets[child_id].value),
                "timeline": child.to_dict(
                    events=events,
                    external_references=external_references,
                ),
            }

        data: dict[str, Any] = {
            "id": self._id,
            "name": self._name,
            "class": self.class_name,
            "unit": str(self._unit),
            "number_type": str(self._number_type),
            "length": rational_to_wire(self._length.value),
            "locked": self._locked,
            "meta": self._meta,
            "children": children_data,
            "conversion_maps": [
                cmap.to_dict() for cmap in self._conversion_maps.values()
            ],
        }

        if events:
            data["events"] = list(self._events)
        if external_references:
            data["external_references"] = self._external_references.to_pylist()

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a Timeline from a dictionary.

        Every rational wire dict in *data* — ``length``, the child
        ``offset``s, and the event coordinate structs — is decoded by
        :func:`~timetoalign.core.wire_to_rational`, so an exact ratio
        comes back as a ``Fraction`` and an inexact one as a ``float``.
        Feeding the result back through :meth:`to_dict` with the same
        flags reproduces the input dictionary.

        The ``"events"`` and ``"external_references"`` keys are optional:
        a dictionary produced without them reconstructs a timeline with
        zero events and an empty reference table. External references are
        restored without event validation, so a payload carrying
        references but no events round-trips intact.

        Args:
            data: Dictionary from to_dict().

        Returns:
            A new Timeline instance.
        """
        class_tag = data.get("class")
        if not isinstance(class_tag, str):
            raise ValueError("Serialized timeline is missing a string 'class' tag")

        if cls is Timeline and class_tag != Timeline.__name__:
            timeline_class = Timeline._registry.get(class_tag)
            if timeline_class is None:
                raise ValueError(f"Unknown serialized timeline class '{class_tag}'")
            return timeline_class.from_dict(data)

        if class_tag != cls.__name__:
            raise ValueError(
                f"Serialized timeline class '{class_tag}' does not match "
                f"receiving subclass '{cls.__name__}'"
            )

        timeline = cls(
            length=wire_to_rational(data["length"]),
            unit=data["unit"],
            number_type=data["number_type"],
            uid=data["id"],
            name=data.get("name"),
            locked=data.get("locked", False),
            meta=data.get("meta"),
        )

        # Add events (filter out segment events - they'll be recreated).
        # Event coordinates arrive as rational wire dicts; decode them
        # back to the numbers the EventData builder expects.
        events = []
        for e in data.get("events", []):
            if e.get("event_type") == SEGMENT_EVENT_TYPE:
                continue
            event = dict(e)
            for coord_col in ("instant", "start", "end", "duration"):
                if event.get(coord_col) is not None:
                    event[coord_col] = wire_to_rational(event[coord_col])
            events.append(event)

        if events:
            timeline._add_events_unchecked(events)

        # Restore incoming external references. Validation is skipped: the
        # payload may legitimately carry references without events.
        references = data.get("external_references")
        if references:
            timeline.add_external_references(references, validate=False)

        # Add children
        for child_id, child_data in data.get("children", {}).items():
            child = Timeline.from_dict(child_data["timeline"])
            timeline.add_child(child, offset=wire_to_rational(child_data["offset"]))

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

        Note: Only the timeline object itself is re-typed. Events, external
        references, children, conversion maps, regions, and metadata are
        preserved. Children are transferred as-is (not recursively re-typed).

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

        # Transfer external references (Arrow tables are immutable, so the
        # table object can be shared between the two timelines)
        typed._external_references = self._external_references

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
        parts = [
            f"id={self._id!r}",
            f"length={self._length.value}",
            f"unit={self._unit}",
            f"events={self.n_events}",
            f"children={self.n_children}",
        ]
        if self.n_conversion_maps > 0:
            parts.append(f"cmaps={self.n_conversion_maps}")
        return f"{self.class_name}({', '.join(parts)})"

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


# Runtime type binding avoids a circular module dependency.
_children_engine.Timeline = Timeline
_conversion_engine.Timeline = Timeline
