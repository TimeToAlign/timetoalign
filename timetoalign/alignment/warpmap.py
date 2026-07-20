"""WarpMap: bidirectional coordinate warping from alignment data.

This module implements the WarpMap class, which produces a materialised
copy of a source timeline warped to a target timeline's coordinate
system. It is the final step in the alignment pipeline:

    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine -> **WarpMap**

A WarpMap wraps an `InterpolationMap` and provides:

- ``forward(coord)``: source coord -> target coord
- ``inverse(coord)``: target coord -> source coord
- ``materialise(source_timeline)``: produce a new Timeline with all
  contents (events, children, regions) warped to the target's
  coordinate system.

Design principle 6 from the overhaul plan:
    "WarpMap materialises a complete timeline copy (events, children,
    regions) from a MatchLine. It IS an InterpolationMap under the hood."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from timetoalign.maps.interpolation import InterpolationMap

if TYPE_CHECKING:
    from timetoalign.alignment.matchline import MatchLine
    from timetoalign.core.enums import TimeUnit
    from timetoalign.timelines.base import Timeline

module_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarpMap:
    """Bidirectional coordinate warping derived from alignment data.

    A WarpMap converts coordinates from a *source* timeline to a *target*
    timeline (and back) using linear interpolation between anchor points
    extracted from a `timetoalign.MatchLine`.

    Internally it delegates to an `timetoalign.maps.interpolation.InterpolationMap`
    for O(log n) lookup.  The ``materialise()`` method produces a complete
    copy of a source `timetoalign.Timeline` with all coordinates warped
    to the target's coordinate space.

    Attributes:
        source_timeline_id: ID of the source timeline.
        target_timeline_id: ID of the target timeline.
        interpolation_map: The underlying InterpolationMap for coordinate
            conversion.
        source_unit: Unit of the source timeline (optional, informational).
        target_unit: Unit of the target timeline (optional, informational).
        n_anchors: Number of anchor points used for interpolation.

    Examples:
        >>> warp = WarpMap.from_match_line(match_line, "audio")
        >>> warp.forward(100.0)   # score coord -> audio coord
        45.5
        >>> warp.inverse(45.5)    # audio coord -> score coord
        100.0

    See Also:
        `timetoalign.MatchLine`
        `timetoalign.InterpolationMap`
    """

    source_timeline_id: str
    target_timeline_id: str
    interpolation_map: InterpolationMap = field(repr=False)
    source_unit: "TimeUnit | None" = field(default=None)
    target_unit: "TimeUnit | None" = field(default=None)

    # region Properties

    @property
    def n_anchors(self) -> int:
        """Number of anchor points used for interpolation."""
        return self.interpolation_map.n_anchors

    @property
    def source_coords(self) -> NDArray[np.floating[Any]]:
        """The source coordinate anchor points (read-only)."""
        return self.interpolation_map.source_coords

    @property
    def target_coords(self) -> NDArray[np.floating[Any]]:
        """The target coordinate anchor points (read-only)."""
        return self.interpolation_map.target_coords

    @property
    def is_invertible(self) -> bool:
        """Whether the inverse mapping is defined.

        True if target coordinates are strictly monotonic.
        """
        return self.interpolation_map.is_invertible

    # endregion

    # region Forward / Inverse

    def forward(
        self, coord: float | NDArray[np.floating[Any]]
    ) -> float | NDArray[np.floating[Any]]:
        """Convert source coordinate(s) to target coordinate(s).

        Uses linear interpolation between anchor points, with linear
        extrapolation outside the anchor range.

        Args:
            coord: One or more source coordinates.

        Returns:
            Corresponding target coordinate(s).
        """
        return self.interpolation_map(coord)

    def inverse(
        self, coord: float | NDArray[np.floating[Any]]
    ) -> float | NDArray[np.floating[Any]]:
        """Convert target coordinate(s) to source coordinate(s).

        Uses linear interpolation between anchor points, with linear
        extrapolation outside the anchor range.

        Args:
            coord: One or more target coordinates.

        Returns:
            Corresponding source coordinate(s).

        Raises:
            ValueError: If the target coordinates are not strictly
                monotonic (map is not invertible).
        """
        return self.interpolation_map.inverse()(coord)

    # endregion

    # region Factory Methods

    @classmethod
    def from_match_line(
        cls,
        match_line: "MatchLine",
        target_timeline_id: str,
        *,
        source_unit: "TimeUnit | None" = None,
        target_unit: "TimeUnit | None" = None,
    ) -> "WarpMap":
        """Build a WarpMap from a MatchLine's coordinate pairs.

        Extracts ``(source_coord, target_coord)`` pairs from the
        MatchLine for the given target timeline, deduplicates by source
        coordinate (averaging target values for chords), and constructs
        the interpolation map.

        Args:
            match_line: The MatchLine providing ordered stamps.
            target_timeline_id: The target timeline to warp towards.
            source_unit: Unit of the source timeline (optional).
            target_unit: Unit of the target timeline (optional).

        Returns:
            A new WarpMap.

        Raises:
            ValueError: If fewer than 2 coordinate pairs are available.
            ValueError: If ``target_timeline_id`` is not in the
                MatchLine's target timelines.
        """
        pairs = match_line.get_coordinate_pairs(target_timeline_id)
        if len(pairs) < 2:
            raise ValueError(
                f"WarpMap requires at least 2 coordinate pairs, "
                f"got {len(pairs)} for target '{target_timeline_id}'. "
                f"Available targets: {match_line.target_timeline_ids()}"
            )

        # Deduplicate: chords may produce multiple pairs at the same
        # source coordinate.  Average target values.
        deduped: dict[float, list[float]] = {}
        for src, tgt in pairs:
            deduped.setdefault(src, []).append(tgt)

        src_arr = np.array(sorted(deduped.keys()), dtype=np.float64)
        tgt_arr = np.array([np.mean(deduped[s]) for s in src_arr], dtype=np.float64)

        imap = InterpolationMap(
            source_coords=src_arr,
            target_coords=tgt_arr,
            source_id=match_line.source_timeline_id,
            target_id=target_timeline_id,
            source_unit=source_unit,
            target_unit=target_unit,
        )

        return cls(
            source_timeline_id=match_line.source_timeline_id,
            target_timeline_id=target_timeline_id,
            interpolation_map=imap,
            source_unit=source_unit,
            target_unit=target_unit,
        )

    @classmethod
    def from_coordinate_pairs(
        cls,
        source_timeline_id: str,
        target_timeline_id: str,
        source_coords: list[float] | NDArray[np.floating[Any]],
        target_coords: list[float] | NDArray[np.floating[Any]],
        *,
        source_unit: "TimeUnit | None" = None,
        target_unit: "TimeUnit | None" = None,
    ) -> "WarpMap":
        """Build a WarpMap from explicit coordinate arrays.

        This lower-level constructor is useful when coordinate pairs
        are already available (e.g. from a Parquet file or external
        alignment tool) and do not need to be extracted from a
        MatchLine.

        Args:
            source_timeline_id: ID of the source timeline.
            target_timeline_id: ID of the target timeline.
            source_coords: Sorted source coordinates (strictly increasing).
            target_coords: Corresponding target coordinates.
            source_unit: Unit of the source timeline (optional).
            target_unit: Unit of the target timeline (optional).

        Returns:
            A new WarpMap.

        Raises:
            ValueError: If fewer than 2 coordinate pairs, or if
                source_coords are not strictly increasing.
        """
        src_arr = np.asarray(source_coords, dtype=np.float64)
        tgt_arr = np.asarray(target_coords, dtype=np.float64)

        imap = InterpolationMap(
            source_coords=src_arr,
            target_coords=tgt_arr,
            source_id=source_timeline_id,
            target_id=target_timeline_id,
            source_unit=source_unit,
            target_unit=target_unit,
        )

        return cls(
            source_timeline_id=source_timeline_id,
            target_timeline_id=target_timeline_id,
            interpolation_map=imap,
            source_unit=source_unit,
            target_unit=target_unit,
        )

    # endregion

    # region Materialise

    def materialise(self, source_timeline: "Timeline") -> "Timeline":
        """Produce a new Timeline with all contents warped to target coordinates.

        Creates a complete copy of the source timeline where every
        coordinate (events, children, regions) is converted via
        ``forward()``.  The resulting timeline:

        - Has length equal to ``forward(source_timeline.length)``
        - Preserves the source's unit (unless ``target_unit`` differs)
        - Contains warped copies of all events
        - Contains warped copies of all children (recursively)
        - Contains warped copies of all regions
        - Carries an inverse WarpMap as a ConversionMap for traceability

        Args:
            source_timeline: The timeline to warp.

        Returns:
            A new Timeline with warped coordinates.

        Raises:
            ValueError: If ``source_timeline.id`` does not match
                ``self.source_timeline_id``.
        """
        if source_timeline.id != self.source_timeline_id:
            raise ValueError(
                f"source_timeline.id '{source_timeline.id}' does not match "
                f"WarpMap source '{self.source_timeline_id}'"
            )

        from timetoalign.timelines.base import Timeline

        # Determine the target unit and timeline class
        target_unit = self.target_unit or source_timeline.unit
        warped_length = self.forward(float(source_timeline.length.value))

        # Choose timeline class: if target unit differs, pick the
        # appropriate typed subclass; otherwise mirror the source type.
        if target_unit != source_timeline.unit:
            from timetoalign.timelines.types import get_timeline_class

            discrete_units = {"ticks", "samples", "frames", "pixels"}
            is_discrete = target_unit.value in discrete_units
            try:
                tl_class = get_timeline_class(
                    target_unit.domain.name.lower(), discrete=is_discrete
                )
            except (ValueError, AttributeError):
                tl_class = Timeline
        else:
            tl_class = type(source_timeline)

        warped = tl_class(
            length=warped_length,
            unit=target_unit,
            name=f"{source_timeline.name or source_timeline.id}[warped->{self.target_timeline_id}]",
        )

        # Warp events
        self._warp_events(source_timeline, warped)

        # Warp children (recursively)
        self._warp_children(source_timeline, warped)

        # Warp regions
        self._warp_regions(source_timeline, warped)

        module_logger.debug(
            "Materialised '%s' -> '%s' (length %.3f -> %.3f)",
            source_timeline.id,
            warped.id,
            float(source_timeline.length.value),
            warped_length,
        )

        return warped

    def _warp_events(
        self,
        source: "Timeline",
        target: "Timeline",
    ) -> None:
        """Warp all non-segment events from source to target.

        Args:
            source: Source timeline with original events.
            target: Target timeline to receive warped events.
        """
        from timetoalign.timelines.base import SEGMENT_EVENT_TYPE

        warped_events: list[dict[str, Any]] = []
        for event in source.events:
            if event.get("event_type") == SEGMENT_EVENT_TYPE:
                continue

            warped = dict(event)

            # Warp coordinate fields
            for name in ("instant", "start", "end"):
                val = warped.get(name)
                if val is None:
                    continue
                if isinstance(val, dict) and "value" in val:
                    raw = float(val["value"])
                else:
                    raw = float(val)
                warped[name] = float(self.forward(raw))

            # Warp duration: forward(start + duration) - forward(start)
            # This correctly handles non-linear warping.
            if warped.get("duration") is not None:
                start_val = warped.get("start")
                if start_val is not None:
                    # start_raw = float(start_val)
                    dur_raw = event.get("duration")
                    if isinstance(dur_raw, dict) and "value" in dur_raw:
                        dur_raw = float(dur_raw["value"])
                    else:
                        dur_raw = float(dur_raw)
                    # Get original start for correct duration warping
                    orig_start = event.get("start")
                    if isinstance(orig_start, dict) and "value" in orig_start:
                        orig_start = float(orig_start["value"])
                    else:
                        orig_start = float(orig_start)
                    warped["duration"] = float(
                        self.forward(orig_start + dur_raw)
                    ) - float(self.forward(orig_start))
                else:
                    # Instant event with spurious duration — drop it
                    warped["duration"] = 0.0

            warped_events.append(warped)

        if warped_events:
            target.add_events(warped_events, allow_expansion=True)

    def _warp_children(
        self,
        source: "Timeline",
        target: "Timeline",
    ) -> None:
        """Warp all children from source to target (recursively).

        Each child's offset is warped and its length is scaled to
        ``forward(offset + child_length) - forward(offset)``. Events
        within each child are warped relative to the child's new
        coordinate system using a derived sub-WarpMap.

        Args:
            source: Source timeline with original children.
            target: Target timeline to receive warped children.
        """
        for child_id, child in source._children.items():
            offset = source._child_offsets[child_id]
            offset_val = float(offset.value)
            child_length = float(child.length.value)

            warped_offset = float(self.forward(offset_val))
            warped_end = float(self.forward(offset_val + child_length))
            warped_child_length = warped_end - warped_offset

            if warped_child_length <= 0:
                module_logger.warning(
                    "Skipping child '%s': warped length is non-positive "
                    "(%.3f -> %.3f)",
                    child_id,
                    child_length,
                    warped_child_length,
                )
                continue

            # Build a sub-WarpMap that converts child-local coordinates
            # to the warped child-local coordinates.
            # Child-local source coords: [0, child_length]
            # Warped child-local coords: [0, warped_child_length]
            # We need to map through the parent warp:
            #   warped_local = forward(local + offset) - forward(offset)
            n_points = max(self.n_anchors, 2)
            # Sample the child's coordinate range
            child_sample_coords = np.linspace(0.0, child_length, n_points)
            parent_coords = child_sample_coords + offset_val
            warped_parent = np.array([float(self.forward(c)) for c in parent_coords])
            warped_child_local = warped_parent - warped_offset

            # Ensure monotonicity (should hold if parent warp is monotonic)
            if not np.all(np.diff(warped_child_local) > 0):
                module_logger.warning(
                    "Child '%s' sub-warp is not monotonic; skipping.",
                    child_id,
                )
                continue

            child_warp = WarpMap(
                source_timeline_id=child.id,
                target_timeline_id=f"{child.id}[warped]",
                interpolation_map=InterpolationMap(
                    source_coords=child_sample_coords,
                    target_coords=warped_child_local,
                    source_id=child.id,
                    target_id=f"{child.id}[warped]",
                ),
            )

            # Recursively materialise the child
            warped_child = child_warp.materialise(child)

            # Add warped child to target at the warped offset
            target.add_child(warped_child, warped_offset, allow_expansion=True)

    def _warp_regions(
        self,
        source: "Timeline",
        target: "Timeline",
    ) -> None:
        """Warp all regions from source to target.

        Args:
            source: Source timeline with original regions.
            target: Target timeline to receive warped regions.
        """
        from timetoalign.core import Coordinate
        from timetoalign.timelines.regions import Region

        target_unit = target.unit

        for name, region in source._regions.items():
            warped_start = float(self.forward(float(region.start.value)))
            warped_end = float(self.forward(float(region.end.value)))

            if warped_end <= warped_start:
                module_logger.warning(
                    "Skipping region '%s': warped interval is degenerate "
                    "(%.3f -> %.3f)",
                    name,
                    warped_start,
                    warped_end,
                )
                continue

            warped_region = Region(
                name=name,
                start=Coordinate(warped_start, target_unit),
                end=Coordinate(warped_end, target_unit),
                meta=dict(region.meta),
            )
            target.add_region(warped_region)

    # endregion

    # region Serialization

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dict with timeline IDs, units, and coordinate arrays.
        """
        return {
            "source_timeline_id": self.source_timeline_id,
            "target_timeline_id": self.target_timeline_id,
            "source_coords": self.interpolation_map.source_coords.tolist(),
            "target_coords": self.interpolation_map.target_coords.tolist(),
            "source_unit": (
                self.source_unit.value if self.source_unit is not None else None
            ),
            "target_unit": (
                self.target_unit.value if self.target_unit is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WarpMap":
        """Deserialize from dictionary.

        Args:
            data: Dict as produced by ``to_dict()``.

        Returns:
            A new WarpMap.
        """
        from timetoalign.core.enums import TimeUnit

        source_unit = TimeUnit(data["source_unit"]) if data.get("source_unit") else None
        target_unit = TimeUnit(data["target_unit"]) if data.get("target_unit") else None

        return cls.from_coordinate_pairs(
            source_timeline_id=data["source_timeline_id"],
            target_timeline_id=data["target_timeline_id"],
            source_coords=data["source_coords"],
            target_coords=data["target_coords"],
            source_unit=source_unit,
            target_unit=target_unit,
        )

    # endregion

    # region Display

    def __repr__(self) -> str:
        return (
            f"WarpMap(source='{self.source_timeline_id}', "
            f"target='{self.target_timeline_id}', "
            f"n_anchors={self.n_anchors})"
        )

    def __str__(self) -> str:
        return f"WarpMap({self.source_timeline_id} -> " f"{self.target_timeline_id})"

    # endregion
