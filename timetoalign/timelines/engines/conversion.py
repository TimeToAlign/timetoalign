"""Provide coordinate conversion operations for timeline instances."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any, Iterator

import numpy as np

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    CoordinateValue,
    NumberType,
    TimeUnit,
    resolve_coordinate_spec,
)
from timetoalign.maps import ConversionMap, InterpolationMap

from .coordinate_ops import coordinate_numeric_value, exact_coordinate_value

if TYPE_CHECKING:
    from ..base import Timeline

SEGMENT_EVENT_TYPE = "Segment"


class ConversionMapsMixin:
    """Provide coordinate conversion operations for timeline instances."""

    @property
    def n_conversion_maps(self) -> int:
        """Number of attached conversion maps."""
        return len(self._conversion_maps)

    def add_conversion_map(self, cmap: ConversionMap[Any]) -> None:
        """Add a ConversionMap to this timeline.

        Any map with a ``target_unit`` is automatically registered in the
        unified timestamp system so that :meth:`get_timestamp` can resolve
        coordinates in that unit. The map is stored as-is: ``TableMap``
        instances honor their own ``kind`` (nearest/previous/next/linear)
        and ``extrapolate`` policy directly, and analytical maps (e.g.
        ``ScalarMap``, ``LinearMap``) are likewise stored directly.

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

        # Register in the unified timestamp system for unit-based lookup
        if cmap.target_unit is not None:
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
            if target.is_discrete:
                return np.vectorize(round, otypes=[int])(converted_value)
            return converted_value
        return Coordinate(converted_value, target)

    def derive(
        self,
        target_unit: TimeUnit | str,
        name: str | None = None,
        copy_events: bool = False,
    ) -> "Timeline":
        """Create a derivative timeline in a different unit via C-Map conversion.

        A ConversionMap implies the presence of a derived timeline in the
        target unit. The derive() method makes this implicit timeline explicit.

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
        from ..types import get_timeline_class

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
            coordinate_values = {
                name: self._events.column_values(name)
                for name in ("instant", "start", "end", "duration")
            }
            for index, event in enumerate(self._events):
                # Skip segment events
                if event.get("event_type") == SEGMENT_EVENT_TYPE:
                    continue

                converted = dict(event)
                for coord_col in ("instant", "start", "end"):
                    val = coordinate_values[coord_col][index]
                    if val is not None:
                        converted[coord_col] = float(cmap(val))

                # Convert duration if present
                duration_val = coordinate_values["duration"][index]
                if duration_val is not None:
                    converted["duration"] = float(cmap(duration_val)) - float(cmap(0))

                converted_events.append(converted)

            if converted_events:
                derived.add_events(converted_events)

        self._logger.debug(
            f"Derived timeline '{derived.id}' in {target} from '{self._id}'"
        )

        return derived

    def _get_child_coordinate(
        self, child_id: str, parent_coord: CoordinateValue
    ) -> CoordinateValue | None:
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
        path = self._descendant_offset_path(child_id)
        if path is None or not path[0]:
            return None
        offsets, child = path
        child_coord = parent_coord
        for offset in offsets:
            child_exact = exact_coordinate_value(child_coord)
            offset_exact = exact_coordinate_value(offset.value)
            child_coord = (
                child_exact - offset_exact
                if child_exact is not None and offset_exact is not None
                else float(coordinate_numeric_value(child_coord)) - float(offset.value)
            )
        child_length = child.length.value
        if child_coord < 0 or (child_length > 0 and child_coord >= child_length):
            return None
        return child_coord

    def _get_parent_coordinate_from_child(
        self, child_id: str, child_coord: CoordinateValue
    ) -> CoordinateValue:
        """Convert a child coordinate to a parent coordinate via exact offset arithmetic.

        ``parent_coord = child_coord + offset``

        Args:
            child_id: The child timeline ID.
            child_coord: Coordinate on the child timeline.

        Returns:
            Coordinate on this (parent) timeline.

        Raises:
            KeyError: If *child_id* is not a descendant of this timeline.
        """
        path = self._descendant_offset_path(child_id)
        if path is None or not path[0]:
            raise KeyError(child_id)
        parent_coord = child_coord
        for offset in reversed(path[0]):
            parent_exact = exact_coordinate_value(parent_coord)
            offset_exact = exact_coordinate_value(offset.value)
            parent_coord = (
                parent_exact + offset_exact
                if parent_exact is not None and offset_exact is not None
                else float(coordinate_numeric_value(parent_coord)) + float(offset.value)
            )
        return parent_coord

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> InterpolationMap | None:
        """Get InterpolationMap for coordinate conversion to target.

        This method is part of the `TimeStampSource` protocol.

        For parent-child relationships, returns None: child coordinates are
        resolved via exact offset arithmetic in ``_get_child_coordinate()``
        instead. InterpolationMaps are only used by `TimelineGroup` for
        inter-member conversions and, for unit-based conversions, by
        ``_get_unit_map`` (which returns whichever ConversionMap type was
        registered, not necessarily an InterpolationMap).

        Args:
            target_id: Target timeline ID.
            source_id: Source timeline ID (ignored for Timeline, always self).

        Returns:
            None. Child conversion uses offset arithmetic.
        """
        return None

    def _get_unit_map(self, unit: TimeUnit) -> ConversionMap[Any] | None:
        """Get a map for unit-based conversion.

        Returns whichever ``ConversionMap`` was registered by
        :meth:`add_conversion_map` for this unit, called directly regardless
        of its concrete type (``TableMap``, ``ScalarMap``, ``LinearMap``,
        ...).

        This method is part of the TimeStampSource protocol.

        Args:
            unit: Target unit.

        Returns:
            A map for conversion, or None if no C-Map available.
        """
        return self._unit_maps.get(unit)

    def _get_unit_map_for_timeline(
        self, timeline_id: str, unit: TimeUnit
    ) -> ConversionMap[Any] | None:
        """Get a unit C-Map attached to this timeline or any descendant.

        A timestamp is a cross-section, so a C-Map registered on a child
        (or deeper descendant) is reachable through the ancestor whose
        ``get_timestamp`` produced the stamp.
        """
        timeline = self._find_descendant(timeline_id)
        if timeline is None:
            return None
        return timeline._get_unit_map(unit)

    def _get_number_type_for_timeline(self, timeline_id: str) -> NumberType | None:
        """Get the numeric representation used by this timeline or a descendant."""
        timeline = self._find_descendant(timeline_id)
        return timeline.number_type if timeline is not None else None

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of the direct child timelines.

        This method is part of the TimeStampSource protocol. It reports only
        the immediate children (the rows a timestamp lists as its
        cross-section); deeper descendants are reached through
        :meth:`_get_descendant_timeline_ids`.

        Returns:
            List of direct child timeline IDs.
        """
        return list(self._children.keys())

    def _iter_descendants(self) -> "Iterator[tuple[str, Timeline]]":
        """Yield ``(id, timeline)`` for every descendant, depth-first."""
        for child_id, child in self._children.items():
            yield child_id, child
            yield from child._iter_descendants()

    def _find_descendant(self, timeline_id: str) -> "Timeline | None":
        """Return this timeline or the descendant with *timeline_id*, else None."""
        path = self._descendant_offset_path(timeline_id)
        return path[1] if path is not None else None

    def _descendant_offset_path(
        self, timeline_id: str
    ) -> tuple[list[Coordinate], Timeline] | None:
        """Find the offset path to a timeline in this subtree.

        Args:
            timeline_id: Timeline ID to find.

        Returns:
            The offsets from this timeline to the owner and the owner itself,
            or None when the ID is unknown.
        """
        if timeline_id == self._id:
            return [], self  # type: ignore[return-value]
        for child_id, child in self._children.items():
            child_path = child._descendant_offset_path(timeline_id)
            if child_path is not None:
                offsets, owner = child_path
                return [self._child_offsets[child_id], *offsets], owner
        return None

    def _get_descendant_timeline_ids(self) -> list[str]:
        """Get IDs of every descendant timeline (children, recursively).

        This method is part of the TimeStampSource protocol. Timestamps use
        it to surface conversions from the full subtree, not just the direct
        children reported by :meth:`_get_related_timeline_ids`.
        """
        return [descendant_id for descendant_id, _ in self._iter_descendants()]

    def _get_conversion_maps_for_timeline(
        self, timeline_id: str
    ) -> list[ConversionMap[Any]]:
        """Get every conversion map attached to a timeline in the subtree.

        This method is part of the TimeStampSource protocol. Unlike
        :meth:`_get_unit_map_for_timeline`, it returns C-Maps of *all* kinds
        -- including those with no ``target_unit`` (label and structured-value
        maps) -- so a timestamp exposes them as a full cross-section.
        """
        timeline = self._find_descendant(timeline_id)
        if timeline is None:
            return []
        return list(timeline._conversion_maps.values())

    def _get_available_units(self) -> list[TimeUnit]:
        """Get all target units available via C-Maps across the subtree.

        This method is part of the TimeStampSource protocol. It aggregates the
        target units of this timeline and every descendant so that unit-based
        conversions surface regardless of which level registered the C-Map.

        Returns:
            List of target units available for conversion.
        """
        units: list[TimeUnit] = list(self._unit_maps.keys())
        for _, descendant in self._iter_descendants():
            for unit in descendant._unit_maps.keys():
                if unit not in units:
                    units.append(unit)
        return units

    def _get_unit_for_timeline(self, timeline_id: str) -> TimeUnit | None:
        """Get the TimeUnit for a timeline anywhere in the subtree.

        This method is part of the TimeStampSource protocol. It enables
        TimeStamp to construct proper Coordinate objects with correct units.

        Args:
            timeline_id: The timeline ID to look up.

        Returns:
            The TimeUnit for the timeline, or None if not found.
        """
        timeline = self._find_descendant(timeline_id)
        return timeline._unit if timeline is not None else None

    def _contains_coordinate(
        self, timeline_id: str, axis: float, source_id: str | None = None
    ) -> bool:
        """Check whether *axis* falls within the span of a child timeline.

        A child embedded at *offset* with *length* spans
        ``[offset, offset + length)`` on this (parent) timeline.

        This method is part of the TimeStampSource protocol.

        Args:
            timeline_id: Child timeline ID.
            axis: Coordinate on the parent (source) timeline.
            source_id: Source timeline ID (ignored for Timeline, used by TimelineGroup).

        Returns:
            True if *axis* is inside the child's span, or if
            *timeline_id* is the source itself.
        """
        if timeline_id == self._id:
            return True
        return self._get_child_coordinate(timeline_id, axis) is not None

    def get_coordinate(
        self, value: CoordinateSpec, timeline_id: str | None = None
    ) -> Coordinate:
        """Resolve a coordinate into this timeline's coordinate system.

        Args:
            value: Numeric, unit-qualified, or timeline-qualified coordinate. A
                bare number with ``timeline_id`` is expressed in that descendant
                timeline's native coordinate system.
            timeline_id: Timeline that owns ``value``. An embedded ID on an
                ``IdCoordinate`` must match this value when both are provided.

        Returns:
            A coordinate expressed in this timeline's native unit.

        Raises:
            ValueError: If a timeline ID is unknown or no unit conversion path exists.
        """
        resolved = resolve_coordinate_spec(value, timeline_id=timeline_id)
        owner_id = resolved.timeline_id or self._id
        path = self._descendant_offset_path(owner_id)
        if path is None:
            raise ValueError(
                f"Timeline ID '{owner_id}' is not this timeline "
                f"'{self._id}' or one of its descendants"
            )
        offsets, owner = path
        native_value = resolved.value
        if resolved.unit is not None and resolved.unit != self._unit:
            candidates: list[tuple[int, Timeline]] = [(0, owner)]
            for _, candidate in self._iter_descendants():
                if candidate is owner:
                    continue
                candidate_path = candidate._descendant_offset_path(owner_id)
                if candidate_path is not None:
                    candidates.append((len(candidate_path[0]), candidate))
            if self is not owner:
                candidates.append((len(offsets), self))
            unit_map = None
            for _, candidate in sorted(candidates, key=lambda item: item[0]):
                unit_map = candidate._get_unit_map(resolved.unit)
                if unit_map is not None:
                    break
            if unit_map is None:
                raise ValueError(
                    f"No C-Map available to convert coordinate from unit "
                    f"'{resolved.unit}' to '{self._unit}' on timeline '{self._id}'"
                )
            try:
                inverse_map = unit_map.inverse()
            except (NotImplementedError, ValueError):
                raise ValueError(
                    f"No invertible C-Map available to convert coordinate from unit "
                    f"'{resolved.unit}' to '{self._unit}' on timeline '{self._id}'"
                ) from None
            native_value = inverse_map(resolved.value)

        for offset in reversed(offsets):
            native_exact = exact_coordinate_value(native_value)
            offset_exact = exact_coordinate_value(offset.value)
            native_value = (
                native_exact + offset_exact
                if native_exact is not None and offset_exact is not None
                else float(coordinate_numeric_value(native_value)) + float(offset.value)
            )

        return Coordinate(native_value, self._unit)

    def _resolve_axis_value(self, coord: CoordinateSpec) -> int | float | Fraction:
        """Resolve a coordinate and return its native numeric value."""
        return self.get_coordinate(coord).value
