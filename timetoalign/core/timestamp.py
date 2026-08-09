"""Unified TimeStamp: Cross-section through timeline hierarchies.

This module provides Stamp, TimeStamp, and TimeIntervalStamp, the unified mechanism
for coordinate resolution across both Timeline (with children) and
TimelineGroup (with member timelines).

Design rationale (from unified_timestamp_architecture.md):
- TimeStamp is a lightweight view object that computes coordinates on access
- InterpolationMap gives TimelineGroup members O(log n) coordinate conversion
- Every attached C-Map (whatever its concrete type) is called directly via
  the shared ConversionMap interface, so unit-based conversions honor each
  map's own interpolation kind and extrapolation policy
- Works identically for Timeline.get_timestamp() and TimelineGroup.get_timestamp()

Key insight: parent<->child coordinates use exact offset arithmetic;
timeline<->group and unit-based conversions are resolved through whichever
ConversionMap was registered for that relationship.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fractions import Fraction
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
    Literal,
    Protocol,
    runtime_checkable,
)

from ..maps.base import ConversionMap
from .enums import NumberType, TimeUnit
from .fields import field_metadata
from .time import format_number, quantize_to_unit

if TYPE_CHECKING:
    import pandas as pd
    import pyarrow as pa

    from ..core.enums import ColumnNaming
    from ..core.time import Coordinate
    from ..maps.interpolation import InterpolationMap
else:
    from ..maps.interpolation import InterpolationMap

module_logger = logging.getLogger(__name__)


# Type alias for flexible conversion_maps parameters.
# Accepts: True (all), single cmap/str, or a list of cmaps/strs.
ConversionMapsSpec = (
    bool
    | str
    | TimeUnit
    | ConversionMap[Any]
    | list[ConversionMap[Any] | str | TimeUnit]
    | None
)


def _conversion_map_enabled_for_spec(
    cmap: "ConversionMap[Any]", spec: "ConversionMapsSpec"
) -> bool:
    """Return whether a ``conversion_maps`` *spec* surfaces *cmap*.

    Pure predicate over a spec and a single map — shared by every
    :class:`Stamp` and by table assembly, which holds a spec but no stamp.
    """
    if spec is True:
        return True
    if spec is False or spec is None:
        return False
    requested = spec if isinstance(spec, list) else [spec]
    for allowed in requested:
        if isinstance(allowed, TimeUnit):
            if cmap.target_unit == allowed:
                return True
        elif isinstance(allowed, str):
            try:
                if cmap.target_unit is not None and TimeUnit(allowed) == (
                    cmap.target_unit
                ):
                    return True
            except ValueError:
                pass
            if cmap.matches_selector(allowed):
                return True
        elif isinstance(allowed, ConversionMap):
            if allowed is cmap or allowed.id == cmap.id:
                return True
    return False


# region Coordinate Formatting


def _names_discrete_unit(unit_str: str) -> bool:
    """Whether *unit_str* names a unit whose values must display as integers.

    Displays receive units as free text — a unit name, an alias like ``px``,
    a C-Map's label, or nothing at all — so the name is resolved through
    :class:`TimeUnit` rather than matched against a list. Anything that is
    not a unit is simply not discrete.
    """
    try:
        return TimeUnit(unit_str.strip()).is_discrete
    except ValueError:
        return False


def _format_coordinate_value(value: int | float | Fraction, unit_str: str = "") -> str:
    """Format a coordinate value without rounding or scientific notation.

    Rules:
    - Discrete units (ticks, samples, pixels, frames): Always integer
    - Exact ratios: their own notation (``2/3``), never a decimal that
      would misrepresent them as terminating
    - Continuous floats: Their shortest lossless representation in fixed-point
      notation
    - Exact integers: Show as integer (no decimal point)

    Args:
        value: The numeric coordinate value.
        unit_str: The unit name (used to detect discrete vs continuous).

    Returns:
        Formatted string, never in scientific notation.
    """
    suffix = f" {unit_str}" if unit_str else ""
    return format_number(value, discrete=_names_discrete_unit(unit_str)) + suffix


def _format_stamp_value(value: Any, unit_str: str = "") -> str:
    """Format any C-Map output for display.

    Numeric outputs reuse :func:`_format_coordinate_value` (optionally
    suffixed with a unit); every other output -- string labels, mappings,
    tuples -- renders via ``str`` so structured conversions surface intact.

    Args:
        value: The C-Map output to format.
        unit_str: Unit appended to numeric values (empty for label maps).

    Returns:
        A display string, never in scientific notation for numeric values.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Fraction):
        suffix = f" {unit_str}" if unit_str else ""
        return f"{value}{suffix}"
    if isinstance(value, (int, float)):
        return _format_coordinate_value(value, unit_str)
    return str(value)


def _format_coordinate(coordinate: Coordinate) -> str:
    """Format a coordinate's value together with its unit.

    Args:
        coordinate: Unit-bearing coordinate to display.

    Returns:
        The coordinate's shared stamp formatting with its unit suffix.
    """
    return _format_stamp_value(coordinate.value, coordinate.unit.value)


# endregion


def _as_float_lane(value: Any) -> Any:
    """Coerce a numeric value to the float lane, passing anything else through.

    Stamps answer in two currencies. ``get_coordinate()``, ``get_unit()`` and
    the conversion paths are the **exact lane**: they carry whatever
    representation the coordinate actually has, so a tick position converts
    to exactly a third of a quarter. ``get()``, subscript access and the raw
    stamp table are the **float lane**: their job is a uniform numeric
    currency that tables, dataframes and arithmetic downstream can rely on,
    and handing those an exact ratio would turn a float column into an object
    column. Non-numeric conversion outputs -- labels, mappings -- are not
    numbers in either currency and pass through untouched.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Fraction):
        return float(value)
    return value


# region TimeStampSource Protocol


@runtime_checkable
class TimeStampSource(Protocol):
    """Protocol for objects that can be TimeStamp sources.

    Both Timeline and TimelineGroup implement this protocol,
    allowing TimeStamp to work with either.
    """

    @property
    def id(self) -> str:
        """Unique identifier."""
        ...

    def _get_interpolation_map(
        self, target_id: str, source_id: str | None = None
    ) -> "InterpolationMap | None":
        """Get InterpolationMap for coordinate conversion to target.

        Args:
            target_id: Target timeline/entity ID.
            source_id: Source timeline ID (optional, for multi-source containers).

        Returns:
            InterpolationMap for conversion, or None if not available.
        """
        ...

    def _get_unit_map(self, unit: "TimeUnit") -> "Any":
        """Get a map for unit-based conversion (InterpolationMap or ConversionMap)."""
        ...

    def _get_unit_map_for_timeline(self, timeline_id: str, unit: "TimeUnit") -> "Any":
        """Get a unit map associated with a specific timeline."""
        ...

    def _get_related_timeline_ids(self) -> list[str]:
        """Get IDs of the direct related timelines (children/members)."""
        ...

    def _get_descendant_timeline_ids(self) -> list[str]:
        """Get IDs of every timeline in the subtree (descendants/members).

        Unlike ``_get_related_timeline_ids`` (direct relations only), this
        reaches the full subtree so a timestamp can surface conversions
        registered at any depth.
        """
        ...

    def _get_conversion_maps_for_timeline(
        self, timeline_id: str
    ) -> "list[ConversionMap[Any]]":
        """Get every conversion map attached to a timeline in the subtree.

        Returns C-Maps of all kinds, including those with no ``target_unit``
        (label and structured-value maps), so timestamps expose them.
        """
        ...

    def _get_available_units(self) -> list["TimeUnit"]:
        """Get all units available via C-Maps across the subtree."""
        ...

    def _get_unit_for_timeline(self, timeline_id: str) -> "TimeUnit | None":
        """Get the TimeUnit for a timeline in the hierarchy.

        Args:
            timeline_id: The timeline ID to look up.

        Returns:
            The TimeUnit for the timeline, or None if not found.
        """
        ...

    def _contains_coordinate(
        self, timeline_id: str, axis: float, source_id: str | None = None
    ) -> bool:
        """Check whether *axis* falls within the span of a related timeline.

        For a child embedded at *offset* with *length*, the span on the
        parent is ``[offset, offset + length)``.  Returns ``True`` for
        the source timeline itself and for any related timeline whose
        span includes *axis*.

        Args:
            timeline_id: The related timeline to check.
            axis: The coordinate on the source timeline.
            source_id: The source timeline ID (required for TimelineGroup,
                optional for Timeline where it defaults to the parent).

        Returns:
            True if *axis* is inside the related timeline's span.
        """
        ...


# endregion


# region Stamp


class Stamp(ABC):
    """Common contract for every synchronized stamp.

    Any stamp, from any source, has identical structure and behaviour: an axis
    coordinate, a source identity, timeline and unit accessors, coordinate
    materialization, and dictionary/subscript views.
    """

    @property
    @abstractmethod
    def axis(self) -> float:
        """Reference coordinate value."""
        ...

    @property
    @abstractmethod
    def source(self) -> object | None:
        """Object that provides the stamp's coordinate relationships."""
        ...

    @property
    @abstractmethod
    def source_id(self) -> str | None:
        """Identifier of the source timeline or group."""
        ...

    @property
    @abstractmethod
    def present_timelines(self) -> list[str]:
        """Timeline IDs that have coordinates at this instant."""
        ...

    @property
    @abstractmethod
    def is_interpolated(self) -> bool:
        """Whether this stamp was computed by interpolation."""
        ...

    @abstractmethod
    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get a coordinate on a related timeline."""
        ...

    @abstractmethod
    def get_unit(self, unit: TimeUnit) -> int | float | Fraction | None:
        """Get a coordinate converted to a unit."""
        ...

    @abstractmethod
    def to_dict(
        self,
        include_children: bool = True,
        conversion_units: list[TimeUnit] | Literal["all"] | None = None,
    ) -> dict[str, float | None]:
        """Materialize the stamp as a coordinate dictionary."""
        ...

    def _on_axis(self, value: Any, timeline_id: str) -> "Coordinate":
        """Express *value* in the declared representation of *timeline_id*.

        Every coordinate this stamp hands out crosses an axis boundary, and
        the axis decides how its numbers are written — the same rule whether
        the value was queried, offset-computed, converted or interpolated.
        Preserving the declared type is what lets a caller reason about a
        fraction-canonical timeline without inspecting each value's kind;
        whether a position was estimated is a separate question, answered by
        ``is_interpolated`` rather than by a number's type.
        """
        from ..core.time import Coordinate, express_as

        unit = self._unit_for(timeline_id)
        declared = self._number_type_enum_for(timeline_id)
        if declared is None:
            declared = unit.default_number_type
        return Coordinate(express_as(value, declared), unit, number_type=declared)

    def _number_type_enum_for(self, timeline_id: str) -> "NumberType | None":
        """The declared :class:`NumberType` of *timeline_id*, if it has one."""
        name = self._number_type_for(timeline_id)
        return None if name is None else NumberType(name)

    def _number_type_for(self, timeline_id: str) -> str | None:
        """Name of the declared numeric type of *timeline_id*, if it has one.

        Subclasses that know their source's timelines override this; the
        base has nothing to look in, so it declines.
        """
        return None

    @abstractmethod
    def _unit_for(self, timeline_id: str) -> TimeUnit | None:
        """Get the unit associated with a timeline ID."""
        ...

    def get_coordinate(self, timeline_id: str) -> "Coordinate | None":
        """Get a coordinate value with its timeline unit attached.

        Args:
            timeline_id: The timeline to get a coordinate for.

        Returns:
            A Coordinate object, or None when the timeline or unit is unavailable.
        """
        raw = self.get(timeline_id)
        unit = self._unit_for(timeline_id)
        if raw is None or unit is None:
            return None

        exact_getter = getattr(self.source, "_get_exact_coordinate_value", None)
        if exact_getter is not None:
            exact = exact_getter(timeline_id, self.axis)
            if exact is not None:
                return self._on_axis(exact, timeline_id)
        # *raw* came off the float lane; the axis decides how it is written.
        return self._on_axis(raw, timeline_id)

    @property
    def axis_coordinate(self) -> "Coordinate":
        """Get the axis value as a Coordinate with its source unit."""
        from ..core.time import Coordinate

        unit = self._unit_for(self.source_id or "")
        if unit is None:
            unit = TimeUnit.seconds
        return Coordinate(self.axis, unit)

    def get_conversion(self, key: str) -> Any:
        """Get the raw output of a conversion map addressed by name/selector.

        Base implementation resolves nothing; stamps backed by a timeline
        subtree override this to expose every attached C-Map -- including
        label and structured-value maps -- by name, id, selector, or
        target-unit name.

        Args:
            key: A conversion-map name, id, selector, or target-unit name.

        Returns:
            The C-Map's output at this instant, or None if unreachable.
        """
        return None

    def __getitem__(self, key: str) -> Any:
        """Get a timeline coordinate, a converted unit, or a C-Map output.

        Resolution order: timeline ID, then unit name, then conversion-map
        name/selector. This makes every attached C-Map -- numeric or not --
        reachable by subscript.

        Args:
            key: Timeline ID, unit name, or conversion-map name/selector.

        Returns:
            The resolved coordinate, unit conversion, or C-Map output. None
            for an existing timeline/unit that has no value at this instant.

        Raises:
            KeyError: If key names nothing reachable at this instant.
        """
        result = self.get(key)
        if result is not None:
            return result
        if self._is_timeline_id(key):
            return result

        try:
            unit = TimeUnit(key)
        except ValueError:
            conversion = self.get_conversion(key)
            if conversion is not None:
                return conversion
            raise KeyError(
                f"{key!r} names no timeline, unit, or conversion map on this "
                f"stamp. Present timelines: {self.present_timelines}"
            ) from None

        if self._unit_resolution_enabled(unit):
            unit_value = self.get_unit(unit)
            if unit_value is not None:
                # Subscript is ``get``'s other spelling, so it answers in the
                # same float lane; ``get_unit`` is the exact one.
                return _as_float_lane(unit_value)
        conversion = self.get_conversion(key)
        if conversion is not None:
            return _as_float_lane(conversion)
        raise KeyError(
            f"{key!r} names no timeline, unit, or conversion map on this "
            f"stamp. Present timelines: {self.present_timelines}"
        )

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether the stamp's conversion-map spec permits a unit."""
        return True

    def _is_timeline_id(self, key: str) -> bool:
        """Return whether key names the source or a subtree timeline."""
        if self.source is None:
            return key == self.source_id
        if key == self.source_id:
            return True
        if key in self.source._get_related_timeline_ids():  # type: ignore[attr-defined]
            return True
        getter = getattr(self.source, "_get_descendant_timeline_ids", None)
        return getter is not None and key in getter()

    def _conversion_map_enabled(self, cmap: "ConversionMap[Any]") -> bool:
        """Return whether this stamp's spec surfaces *cmap*."""
        return _conversion_map_enabled_for_spec(
            cmap, getattr(self, "conversion_maps", True)
        )

    @staticmethod
    def _qualify_conversion_rows(
        collected: list[tuple[str, Any, str, str]],
    ) -> list[tuple[str, Any, str]]:
        """Qualify colliding conversion-row labels with their owning timeline id.

        Each *collected* entry is ``(label, value, suffix, owner)``. A label that
        appears once keeps its bare form; a label shared by several owners is
        prefixed ``owner:label`` so displays stay unambiguous.
        """
        counts: dict[str, int] = {}
        for label, _value, _suffix, _owner in collected:
            counts[label] = counts.get(label, 0) + 1
        rows: list[tuple[str, Any, str]] = []
        for label, value, suffix, owner in collected:
            final_label = label if counts[label] == 1 else f"{owner}:{label}"
            rows.append((final_label, value, suffix))
        return rows


# endregion


# region TimeStamp


@dataclass(frozen=True, slots=True)
class TimeStamp(Stamp):
    """A synchronized instant across a timeline hierarchy.

    Lightweight object that computes coordinates on access via InterpolationMaps.
    Works identically for Timeline (with children) and TimelineGroup (with members).

    The TimeStamp represents a cross-section through the timeline structure at
    a specific axis coordinate. All related timelines' coordinates can be
    retrieved via get() or subscript access.

    Attributes:
        axis: The root/reference coordinate value.
        source: The Timeline or TimelineGroup this timestamp belongs to.
        source_id: ID of the source (for serialization).
        row_index: If from a table row, the index. ``-1`` if interpolated and
            ``None`` for a direct query on the source axis.

    Examples:
        >>> ts = timeline.get_timestamp(5.0)
        >>> ts.axis  # The root coordinate
        5.0
        >>> ts["child:1"]  # Get coordinate on child timeline
        2.5
        >>> ts.get("child:2", default=0.0)  # With default
        0.0

        >>> # Convert to different unit
        >>> ts.get_unit(TimeUnit.seconds)
        10.5
    """

    axis: int | float | Fraction
    source: TimeStampSource
    source_id: str
    row_index: int | None = field(default=None)
    conversion_maps: ConversionMapsSpec = field(default=True)

    def get(self, timeline_id: str, default: float | None = None) -> float | None:
        """Get coordinate on another timeline.

        Returns ``default`` (None) when the queried coordinate falls
        outside the related timeline's span -- for instance, asking a
        child whose parent-side interval is ``[10, 30)`` for the
        coordinate at axis 5.

        For `Timeline` sources, child coordinates are resolved via exact
        offset arithmetic (no interpolation). For `TimelineGroup` sources,
        coordinates are resolved via `InterpolationMap`.

        Args:
            timeline_id: The timeline to get coordinate for.
            default: Value to return if timeline not reachable or out of span.

        Returns:
            Coordinate on the target timeline, or *default* if not
            reachable or the axis is outside the target's span.
        """
        if timeline_id == self.source_id:
            # Round for discrete timelines (TimelineGroup members)
            if self._number_type_for(timeline_id) == "int":
                return round(self.axis)
            return _as_float_lane(self.axis)

        # Bounds check: is axis inside the related timeline's span?
        if not self.source._contains_coordinate(timeline_id, self.axis, self.source_id):
            return default

        # Strategy 1: exact offset arithmetic (Timeline with children)
        _get_child = getattr(self.source, "_get_child_coordinate", None)
        if _get_child is not None:
            result = _get_child(timeline_id, self.axis)
            if result is not None:
                return float(result)
            # If child coordinate returned None but _contains_coordinate
            # said True, fall through to interpolation (should not happen
            # for Timeline, but is safe).

        # Strategy 2: InterpolationMap (TimelineGroup or fallback)
        imap = self.source._get_interpolation_map(timeline_id, source_id=self.source_id)
        if imap is None:
            return default

        # Determine direction based on source/target IDs
        if imap.source_id == self.source_id:
            result = float(imap(self.axis))
        else:
            result = float(imap.inverse()(self.axis))

        # Round for discrete timelines (TimelineGroup members)
        if self._number_type_for(timeline_id) == "int":
            result = round(result)

        return result

    def get_coordinate(self, timeline_id: str) -> "Coordinate | None":
        """Get a coordinate while retaining exact scalar information.

        Raw access through :meth:`get` remains float-valued. This accessor
        evaluates exact parent/child and group relationships separately so a
        rational query is not approximated at the typed boundary.

        Args:
            timeline_id: The timeline to get a coordinate for.

        Returns:
            A Coordinate object, or None when the timeline is unavailable.
        """
        unit = self._unit_for(timeline_id)
        if unit is None:
            return None

        # Each branch resolves a coordinate a different way -- a stored row,
        # offset arithmetic, group interpolation -- and every one of them
        # then crosses the target axis, which is where its representation is
        # decided. Computation stays as exact as its inputs allow; expressing
        # the answer is a separate and final step.
        if timeline_id == self.source_id:
            # A stamp queried with a float may still sit on a stored row whose
            # value is exact; the row is the better answer, and the axis is
            # only a way of finding it.
            exact_getter = getattr(self.source, "_get_exact_coordinate_value", None)
            if exact_getter is not None:
                stored = exact_getter(timeline_id, self.axis)
                if stored is not None:
                    return self._on_axis(stored, timeline_id)
            return self._on_axis(self.axis, timeline_id)

        child_getter = getattr(self.source, "_get_child_coordinate", None)
        if child_getter is not None:
            offset_result = child_getter(timeline_id, self.axis)
            if offset_result is not None:
                return self._on_axis(offset_result, timeline_id)

        group_getter = getattr(self.source, "_get_exact_interpolated_coordinate", None)
        if group_getter is not None:
            structural = group_getter(timeline_id, self.source_id, self.axis)
            if structural is not None:
                return self._on_axis(structural, timeline_id)

        return Stamp.get_coordinate(self, timeline_id)

    def get_unit(self, unit: "TimeUnit") -> int | float | Fraction | None:
        """Get coordinate converted to a specific unit.

        Works with any map registered by ``add_conversion_map``, called
        directly regardless of concrete type (``TableMap``, ``ScalarMap``,
        ``LinearMap``, ``InterpolationMap``, ...).

        Searches the source and every descendant/member timeline for a C-Map
        with this target unit, evaluating it at the timeline's own coordinate.
        A timestamp therefore surfaces unit conversions registered at any
        depth of the hierarchy, not just on the queried timeline.

        Args:
            unit: The target unit for conversion.

        Returns:
            Converted coordinate, or None if no C-Map available.
        """
        if not self._unit_resolution_enabled(unit):
            return None

        from ..core.time import Coordinate

        for timeline_id in self._surfaceable_ids():
            umap = self.source._get_unit_map_for_timeline(timeline_id, unit)
            if umap is None:
                continue
            value = self._coordinate_on(timeline_id)
            if value is None:
                continue
            return Coordinate(quantize_to_unit(umap(value), unit), unit).value
        return None

    def _surfaceable_ids(self) -> list[str]:
        """Timeline IDs whose C-Maps this stamp surfaces: source, then subtree.

        The source comes first, followed by every descendant (Timeline) or
        member and member-descendant (TimelineGroup). Deeper relations are
        gathered via ``_get_descendant_timeline_ids`` when the source exposes
        it, otherwise the direct relations are used.
        """
        ids = [self.source_id]
        getter = getattr(self.source, "_get_descendant_timeline_ids", None)
        related = (
            getter() if getter is not None else self.source._get_related_timeline_ids()
        )
        for timeline_id in related:
            if timeline_id not in ids:
                ids.append(timeline_id)
        return ids

    def _coordinate_on(self, timeline_id: str) -> int | float | Fraction | None:
        """Resolve this stamp's coordinate on *timeline_id* (source or subtree).

        Returns the coordinate in whatever representation it actually has,
        so a C-Map applied to it converts exactly. ``get`` stays float --
        that is its documented currency -- which is why this reaches for
        the typed coordinate first and falls back to ``get`` only when
        there is no exact answer to be had.
        """
        if timeline_id == self.source_id:
            return self.axis
        coordinate = self.get_coordinate(timeline_id)
        if coordinate is not None:
            return coordinate.value
        value = self.get(timeline_id)
        if value is not None:
            return value
        resolver = getattr(self.source, "_descendant_coordinate", None)
        if resolver is not None:
            return resolver(timeline_id, self.axis, self.source_id)
        return None

    def _conversion_rows(self) -> list[tuple[str, Any, str]]:
        """Surface every C-Map across the cross-section.

        Returns ``(label, value, suffix)`` for each conversion map attached to
        the source or any descendant present at this axis, evaluated at that
        timeline's coordinate. ``label`` is the map's target-unit name when it
        has one, else the map's name; labels that collide across owners are
        qualified with the owning timeline id. ``suffix`` is the unit appended
        to numeric values in displays (empty for label/structured maps).
        """
        getter = getattr(self.source, "_get_conversion_maps_for_timeline", None)
        if getter is None:
            return []

        collected: list[tuple[str, Any, str, str]] = []  # (label, value, suffix, owner)
        for timeline_id in self._surfaceable_ids():
            coord = self._coordinate_on(timeline_id)
            if coord is None:
                continue
            for cmap in getter(timeline_id):
                if not self._conversion_map_enabled(cmap):
                    continue
                try:
                    value = cmap(coord)
                except Exception:
                    # A display cross-section never propagates a single map's
                    # evaluation failure (e.g. a coordinate outside a map's
                    # domain): that map is simply omitted from the row set.
                    continue
                if cmap.target_unit is not None:
                    from ..core.time import Coordinate

                    value = Coordinate(value, cmap.target_unit).value
                    label = cmap.target_unit.value
                    suffix = cmap.target_unit.value
                else:
                    label = cmap.name
                    suffix = ""
                collected.append((label, value, suffix, timeline_id))

        return self._qualify_conversion_rows(collected)

    def get_conversion(self, key: str) -> Any:
        """Get the raw output of a conversion map addressed by name/selector.

        Searches the source and every descendant/member present at this axis
        for a C-Map whose name, id, selector, or target-unit name is *key*, and
        evaluates it at that timeline's coordinate.

        Args:
            key: A conversion-map name, id, selector, or target-unit name.

        Returns:
            The C-Map's output at this instant, or None if unreachable.
        """
        getter = getattr(self.source, "_get_conversion_maps_for_timeline", None)
        if getter is None:
            return None
        for timeline_id in self._surfaceable_ids():
            coord = self._coordinate_on(timeline_id)
            if coord is None:
                continue
            for cmap in getter(timeline_id):
                if not self._conversion_map_enabled(cmap):
                    continue
                matches = cmap.matches_selector(key) or cmap.name == key
                if not matches and cmap.target_unit is not None:
                    matches = cmap.target_unit.value == key
                if matches:
                    value = cmap(coord)
                    if cmap.target_unit is not None:
                        from ..core.time import Coordinate

                        value = Coordinate(value, cmap.target_unit).value
                    return value
        return None

    def to_dict(
        self,
        include_children: bool = True,
        conversion_units: list["TimeUnit"] | Literal["all"] | None = None,
        format: Literal["flat", "prefix", "nested", "graph"] = "flat",
    ) -> dict[str, Any]:
        """Materialize all coordinates in a flat or structured dictionary.

        Args:
            include_children: Include child/member timeline coordinates.
            conversion_units: C-Map conversions to include.
                - None: Every C-Map enabled on this stamp
                - "all": Every C-Map across the subtree, of every kind
                  (unit conversions, labels, structured values)
                - list: Specific units only
            format: Output representation. ``"flat"`` retains the legacy
                one-level mapping, ``"prefix"`` prefixes keys with the source
                container ID, ``"nested"`` groups them under that ID, and
                ``"graph"`` separates timeline coordinates from conversions.

        Returns:
            Dict mapping timeline_id/unit_name/cmap-label to value.
        """
        # to_dict is the dict-shaped sibling of the raw stamp table, so it
        # answers in the float lane throughout -- see :func:`_as_float_lane`.
        # The exact values remain one call away via ``get_coordinate()`` and
        # ``get_unit()``, and the rendered forms (``__str__`` / HTML) show
        # them exactly.
        coordinates: dict[str, Any] = {self.source_id: self.get(self.source_id)}

        # Add child/member coordinates
        if include_children:
            for tid in self.source._get_related_timeline_ids():
                coordinates[tid] = self.get(tid)

        conversions: dict[str, Any] = {}
        if conversion_units is None or conversion_units == "all":
            for label, value, _suffix in self._conversion_rows():
                conversions[label] = _as_float_lane(value)
        elif conversion_units:
            for unit in conversion_units:
                value = self.get_unit(unit)
                if value is not None:
                    conversions[unit.value] = _as_float_lane(value)

        if format == "graph":
            return {"coordinates": coordinates, "conversions": conversions}

        if format not in ("flat", "prefix", "nested"):
            raise ValueError(
                f"Unknown format: {format!r}. Use 'flat', 'prefix', "
                "'nested', or 'graph'"
            )

        result = {**coordinates, **conversions}
        if format == "flat":
            return result

        container_id = getattr(self.source, "id", self.source_id)
        if format == "nested":
            return {container_id: result}

        return {f"{container_id}/{key}": value for key, value in result.items()}

    def _unit_for(self, timeline_id: str) -> "TimeUnit | None":
        """Get the unit associated with a timeline ID."""
        return self.source._get_unit_for_timeline(timeline_id)

    def _unit_resolution_enabled(self, unit: TimeUnit) -> bool:
        """Return whether conversion-map specification permits a unit."""
        spec = self.conversion_maps
        if spec is True:
            return True
        if spec is False or spec is None:
            return False

        requested = spec if isinstance(spec, list) else [spec]
        maps = [
            self.source._get_unit_map_for_timeline(timeline_id, unit)
            for timeline_id in self._surfaceable_ids()
        ]
        maps = [cmap for cmap in maps if cmap is not None]

        for allowed in requested:
            if isinstance(allowed, TimeUnit) and allowed == unit:
                return True
            if isinstance(allowed, str):
                try:
                    if TimeUnit(allowed) == unit:
                        return True
                except ValueError:
                    pass
                for cmap in maps:
                    if cmap.matches_selector(allowed):
                        return True
            elif isinstance(allowed, ConversionMap):
                if allowed.target_unit == unit:
                    return True
                if any(cmap.matches_selector(allowed.id) for cmap in maps):
                    return True
        return False

    def _number_type_for(self, timeline_id: str) -> str | None:
        """Get the numeric type name, retaining group compatibility."""
        try:
            number_type = self.source._get_number_type_for_timeline(timeline_id)
        except AttributeError:
            try:
                timelines = self.source._timelines  # type: ignore[attr-defined]
            except AttributeError:
                return None
            timeline = timelines.get(timeline_id)
            number_type = timeline.number_type if timeline is not None else None
        return number_type.name if number_type is not None else None

    @property
    def is_interpolated(self) -> bool:
        """True if this timestamp was computed via interpolation."""
        return self.row_index == -1

    @property
    def present_timelines(self) -> list[str]:
        """Timeline IDs that have coordinates at this instant."""
        result = [self.source_id]
        for tid in self.source._get_related_timeline_ids():
            if self.get(tid) is not None:
                result.append(tid)
        return result

    def __repr__(self) -> str:
        interp = " (interpolated)" if self.is_interpolated else ""
        conversions = "".join(
            f", {label}={value!r}" for label, value, _suffix in self._conversion_rows()
        )
        return (
            f"TimeStamp(axis={self.axis}, source={self.source_id!r}"
            f"{conversions}{interp})"
        )

    def __str__(self) -> str:
        """Readable cross-section showing all reachable coordinates and units.

        Examples:
            >>> print(timeline.get_timestamp(25.0))
            TimeStamp @25 seconds
              audio      25 seconds
              intro      25 seconds
              verse      15 seconds
              chorus     -5 seconds
              milliseconds   25000
              samples  1200000
        """

        lines: list[str] = []

        # Header: axis value with unit
        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        unit_str = axis_unit.value if axis_unit else ""
        lines.append(f"TimeStamp @{_format_coordinate_value(self.axis, unit_str)}")

        # Collect all entries: (label, value_str)
        entries: list[tuple[str, str]] = []

        # Source timeline
        entries.append((self.source_id, _format_coordinate_value(self.axis, unit_str)))

        # Children / related timelines (skip source_id to avoid duplicate)
        for tid in self.source._get_related_timeline_ids():
            if tid == self.source_id:
                continue  # Already added above
            val = self.get(tid)
            if val is not None:
                t_unit = self.source._get_unit_for_timeline(tid)
                entries.append(
                    (tid, _format_coordinate_value(val, t_unit.value if t_unit else ""))
                )

        # C-Map conversions (all kinds, across the whole subtree)
        for label, value, suffix in self._conversion_rows():
            entries.append((label, _format_stamp_value(value, suffix)))

        # Align fields
        if entries:
            max_label = max(len(e[0]) for e in entries)
            for label, value_str in entries:
                lines.append(f"  {label:<{max_label}}  {value_str}")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the timestamp as an HTML table showing all coordinates
        with their units, organized by timeline and C-Map.
        """
        import html

        from timetoalign.display.html import affordance_line

        def _fmt_html(value: float, unit_name: str = "") -> str:
            """Format for HTML display, keeping unit separate."""
            return _format_coordinate_value(value, unit_name)

        rows = []

        # Add axis coordinate
        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        axis_unit_name = axis_unit.value if axis_unit else ""
        rows.append(
            f"<tr><td><strong>{html.escape(self.source_id)}</strong></td>"
            f"<td style='text-align: right;'>{_fmt_html(self.axis, axis_unit_name)}</td>"
            f"<td><em>axis</em></td></tr>"
        )

        # Add related timeline coordinates (children) - skip source_id to avoid duplicate
        for tid in self.source._get_related_timeline_ids():
            if tid == self.source_id:
                continue  # Already added above
            val = self.get(tid)
            if val is not None:
                unit = self.source._get_unit_for_timeline(tid)
                unit_name = unit.value if unit else ""
                rows.append(
                    f"<tr><td>{html.escape(tid)}</td>"
                    f"<td style='text-align: right;'>{_fmt_html(val, unit_name)}</td>"
                    f"<td><em>child</em></td></tr>"
                )

        # Add C-Map conversions (all kinds, across the whole subtree)
        for label, value, suffix in self._conversion_rows():
            rows.append(
                f"<tr><td style='color: #666;'>{html.escape(label)}</td>"
                f"<td style='text-align: right;'>"
                f"{html.escape(_format_stamp_value(value, suffix))}</td>"
                f"<td style='color: #666;'><em>cmap</em></td></tr>"
            )

        interp_badge = (
            " <span style='background: #ffeb3b; padding: 0 4px; "
            "border-radius: 3px; font-size: 0.8em;'>interpolated</span>"
            if self.is_interpolated
            else ""
        )

        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>TimeStamp</strong>{interp_badge}"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<thead><tr style='border-bottom: 1px solid #ccc;'>"
            f"<th style='text-align: left; padding: 2px 8px;'>ID</th>"
            f"<th style='text-align: right; padding: 2px 8px;'>Coordinate</th>"
            f"<th style='text-align: left; padding: 2px 8px;'>Type</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
            f"{affordance_line(['ts.get(<tl_id>)', 'ts.get_unit(<unit>)', 'ts[<cmap>]'])}"
            f"</div>"
        )


# endregion


# region TimeIntervalStamp


@dataclass(frozen=True, slots=True)
class TimeIntervalStamp:
    """An interval defined by start and end TimeStamps.

    Provides facilities for zipping corresponding (start, end) pairs
    across all related timelines.

    Attributes:
        start: TimeStamp at interval start.
        end: TimeStamp at interval end.

    Examples:
        >>> interval = timeline.get_interval_stamp(0.0, 10.0)
        >>> interval.duration  # On axis timeline
        10.0
        >>> interval.get_interval("child:1")  # (start, end) tuple
        (0.0, 7.5)
        >>> interval.get_duration("child:1")
        7.5

        >>> # Get all intervals at once
        >>> interval.zip_intervals()
        {'tl:1': (0.0, 10.0), 'child:1': (0.0, 7.5)}
    """

    start: TimeStamp
    end: TimeStamp

    def __post_init__(self) -> None:
        """Validate that start and end are from the same source."""
        if self.start.source_id != self.end.source_id:
            raise ValueError(
                f"Start and end must be from the same source: "
                f"got {self.start.source_id!r} and {self.end.source_id!r}"
            )

    @property
    def duration(self) -> float:
        """Duration on the axis timeline."""
        return self.end.axis - self.start.axis

    @property
    def source(self) -> TimeStampSource:
        """The source Timeline/Group."""
        return self.start.source

    @property
    def source_id(self) -> str:
        """ID of the source."""
        return self.start.source_id

    def get_interval(self, timeline_id: str) -> tuple[float, float] | None:
        """Get (start, end) pair for a specific timeline.

        Args:
            timeline_id: The timeline to get interval for.

        Returns:
            Tuple of (start, end) coordinates, or None if timeline not reachable.
        """
        s = self.start.get(timeline_id)
        e = self.end.get(timeline_id)
        if s is not None and e is not None:
            return (s, e)
        return None

    def get_duration(self, timeline_id: str) -> float | None:
        """Get duration on a specific timeline.

        Args:
            timeline_id: The timeline to get duration for.

        Returns:
            Duration (end - start), or None if timeline not reachable.
        """
        interval = self.get_interval(timeline_id)
        if interval:
            return interval[1] - interval[0]
        return None

    def get_unit_interval(self, unit: "TimeUnit") -> tuple[float, float] | None:
        """Get (start, end) pair for a specific unit.

        Args:
            unit: The target unit.

        Returns:
            Tuple of (start, end) in the target unit, or None if no C-Map.
        """
        s = self.start.get_unit(unit)
        e = self.end.get_unit(unit)
        if s is not None and e is not None:
            return (s, e)
        return None

    def get_coordinate_interval(
        self, timeline_id: str
    ) -> "tuple[Coordinate, Coordinate] | None":
        """Get (start, end) as proper Coordinate objects.

        Unlike get_interval() which returns floats, this returns Coordinates
        with the correct TimeUnit attached.

        Args:
            timeline_id: The timeline to get interval for.

        Returns:
            Tuple of (start, end) Coordinates, or None if not reachable.

        Examples:
            >>> interval = timeline.get_interval_stamp(10.0, 50.0)
            >>> start, end = interval.get_coordinate_interval("child:1")
            >>> start.unit
            <TimeUnit.seconds: 'seconds'>
        """
        start_coord = self.start.get_coordinate(timeline_id)
        end_coord = self.end.get_coordinate(timeline_id)
        if start_coord is not None and end_coord is not None:
            return (start_coord, end_coord)
        return None

    def zip_intervals(
        self,
        timeline_ids: list[str] | None = None,
        include_units: list["TimeUnit"] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """Get all (start, end) pairs across timelines.

        Args:
            timeline_ids: Specific timelines to include (None = all).
            include_units: C-Map units to include as well.

        Returns:
            Dict mapping timeline_id/unit to (start, end) tuple.
        """
        result: dict[str, tuple[float, float]] = {}

        # Add source timeline
        result[self.source_id] = (self.start.axis, self.end.axis)

        # Get timeline intervals
        ids = timeline_ids or self.source._get_related_timeline_ids()
        for tid in ids:
            interval = self.get_interval(tid)
            if interval:
                result[tid] = interval

        # Get unit intervals
        if include_units:
            for unit in include_units:
                interval = self.get_unit_interval(unit)
                if interval:
                    result[unit.name] = interval

        return result

    def __iter__(self) -> Iterator[TimeStamp]:
        """Iterate as (start, end) pair."""
        return iter((self.start, self.end))

    def __getitem__(self, key: str) -> tuple[float, float] | None:
        """Subscript access for intervals."""
        return self.get_interval(key)

    def __repr__(self) -> str:
        return (
            f"TimeIntervalStamp(start={self.start.axis}, end={self.end.axis}, "
            f"source={self.source_id!r})"
        )

    def __str__(self) -> str:
        """Readable cross-section showing start/end across all reachable timelines.

        Entries where only one endpoint is in range display ``-`` for the
        missing side, making it easy to see events that straddle children.

        Examples:
            >>> print(timeline.get_interval_stamp(8.0, 12.0))
            TimeIntervalStamp [8, 12) seconds
                          start    end
              audio           8     12 seconds
              intro           8      - seconds
              verse           -      2 seconds
              milliseconds 8000  12000
              samples    384000 576000
        """

        def _fmt(v: float | None, unit_name: str = "") -> str:
            """Format a coordinate value; ``None`` becomes ``-``."""
            if v is None:
                return "-"
            # Use the module-level formatter but strip unit suffix (we add it separately)
            formatted = _format_coordinate_value(v, unit_name)
            # Remove the unit suffix since we display it at the end of the row
            if unit_name and formatted.endswith(f" {unit_name}"):
                formatted = formatted[: -(len(unit_name) + 1)]
            return formatted

        axis_unit = self.source._get_unit_for_timeline(self.source_id)
        unit_str = f" {axis_unit.value}" if axis_unit else ""
        unit_name = axis_unit.value if axis_unit else ""

        # Header - format axis values properly
        start_fmt = _format_coordinate_value(self.start.axis, unit_name)
        end_fmt = _format_coordinate_value(self.end.axis, unit_name)
        # Strip unit from these since we show it at end
        if unit_name:
            if start_fmt.endswith(f" {unit_name}"):
                start_fmt = start_fmt[: -(len(unit_name) + 1)]
            if end_fmt.endswith(f" {unit_name}"):
                end_fmt = end_fmt[: -(len(unit_name) + 1)]

        # Header
        lines: list[str] = [f"TimeIntervalStamp [{start_fmt}, {end_fmt}){unit_str}"]

        # Collect rows: (label, start_str, end_str, suffix)
        rows: list[tuple[str, str, str, str]] = []

        # Axis / source timeline
        rows.append(
            (
                self.source_id,
                _fmt(self.start.axis, unit_name),
                _fmt(self.end.axis, unit_name),
                unit_str.strip(),
            )
        )

        # Children / related timelines
        for tid in self.source._get_related_timeline_ids():
            s = self.start.get(tid)
            e = self.end.get(tid)
            if s is None and e is None:
                continue
            t_unit = self.source._get_unit_for_timeline(tid)
            suffix = t_unit.value if t_unit else ""
            rows.append((tid, _fmt(s, suffix), _fmt(e, suffix), suffix))

        # C-Map conversions (all kinds, across the whole subtree)
        def _fmt_any(value: object | None, suffix: str) -> str:
            """Format a C-Map endpoint; ``None`` becomes ``-``."""
            if value is None:
                return "-"
            if isinstance(value, bool):
                return str(value)
            if isinstance(value, (int, float)):
                return _fmt(value, suffix)
            return str(value)

        start_rows = {
            label: (value, suffix)
            for label, value, suffix in self.start._conversion_rows()
        }
        end_rows = {
            label: (value, suffix)
            for label, value, suffix in self.end._conversion_rows()
        }
        ordered_labels = list(start_rows) + [
            label for label in end_rows if label not in start_rows
        ]
        for label in ordered_labels:
            s_val, suffix = start_rows.get(label, (None, end_rows[label][1]))
            e_val = end_rows.get(label, (None, ""))[0]
            rows.append((label, _fmt_any(s_val, suffix), _fmt_any(e_val, suffix), ""))

        # Align fields
        if rows:
            max_label = max(len(r[0]) for r in rows)
            max_start = max(len(r[1]) for r in rows)
            max_end = max(len(r[2]) for r in rows)

            # Column headers
            lines.append(
                f"  {'':>{max_label}}  {'start':>{max_start}}  {'end':>{max_end}}"
            )

            for label, s_str, e_str, suffix in rows:
                suffix_part = f" {suffix}" if suffix else ""
                lines.append(
                    f"  {label:<{max_label}}  {s_str:>{max_start}}  "
                    f"{e_str:>{max_end}}{suffix_part}"
                )

        return "\n".join(lines)


# endregion


# region Timestamp Table Conversion Utilities


def timestamp_table_to_dataframe(
    table: "pa.Table",
    fields: "ColumnNaming | Callable[[str, dict], str] | list[str] | None" = None,
    units: bool = True,
    format: str = "pandas",
) -> "pd.DataFrame":
    """Convert a PyArrow timestamp table to a pandas DataFrame with proper formatting.

    This utility function processes timestamp tables (from Timeline.get_timestamp_table()
    or TimelineGroup.get_timestamp_table()) and applies field naming and type conversions.

    Args:
        table: PyArrow table with field-level metadata including 'unit' and
            'timeline_id' or 'cmap_id'.
        fields: How to name the DataFrame fields. Options:
            - None or ColumnNaming.name (default): Use timeline/cmap name property,
              falling back to id if name is not available.
            - ColumnNaming.id: Use timeline/cmap id.
            - Callable[[str, dict], str]: Function taking (field_name, metadata_dict)
              and returning the new field name.
            - list[str]: Explicit list of field names (must match table length).
        units: If True (default), append units to field names like "name (unit)".
        format: Output format. Currently only "pandas" is supported.

    Returns:
        pandas DataFrame with:
        - Fields named according to the ``fields`` parameter
        - Units appended if ``units=True``
        - Integer fields using pandas nullable Int64 dtype
        - Float fields as float64

    Examples:
        >>> table = timeline.get_timestamp_table()
        >>> df = timestamp_table_to_dataframe(table, units=True)
        >>> df.columns
        Index(['axis (pixels)', 'dgt1 (pixels)', 'pixels_to_inches (inches)'])

        >>> # Use IDs instead of names
        >>> from timetoalign import ColumnNaming
        >>> df = timestamp_table_to_dataframe(table, fields=ColumnNaming.id)

        >>> # Custom field naming
        >>> df = timestamp_table_to_dataframe(
        ...     table,
        ...     fields=lambda name, meta: meta.get('timeline_id', name)
        ... )
    """
    import pandas as pd
    import pyarrow as pa

    from .enums import ColumnNaming

    if format != "pandas":
        raise ValueError(f"Unsupported format: {format!r}. Only 'pandas' is supported.")

    if table.num_rows == 0:
        return pd.DataFrame()

    # Build field name mapping
    new_field_names: list[str] = []

    for i, data_field in enumerate(table.schema):
        field_name = data_field.name
        meta_dict = field_metadata(data_field)

        # Determine base name
        if isinstance(fields, list):
            if i < len(fields):
                base_name = fields[i]
            else:
                base_name = field_name
        elif callable(fields) and not isinstance(fields, ColumnNaming):
            base_name = fields(field_name, meta_dict)
        elif isinstance(fields, ColumnNaming) and str(fields) == "id":
            # Use timeline_id or cmap_id from metadata
            base_name = (
                meta_dict.get("timeline_id") or meta_dict.get("cmap_id") or field_name
            )
        else:  # ColumnNaming.name, None, or default
            # For now, use field name directly (names are already set by Timeline)
            # In future, could look up timeline.name property
            base_name = field_name

        # Append unit if requested
        if units:
            unit = meta_dict.get("unit")
            if unit:
                final_name = f"{base_name} ({unit})"
            else:
                final_name = base_name
        else:
            final_name = base_name

        new_field_names.append(str(final_name))

    # Convert to pandas with appropriate dtypes
    df = table.to_pandas()
    df.columns = new_field_names

    # Convert integer fields to nullable Int64
    for i, data_field in enumerate(table.schema):
        field_name = new_field_names[i]
        if pa.types.is_integer(data_field.type):
            # Convert to nullable integer
            df[field_name] = df[field_name].astype("Int64")
        elif pa.types.is_int64(data_field.type):
            df[field_name] = df[field_name].astype("Int64")

    return df


# endregion
