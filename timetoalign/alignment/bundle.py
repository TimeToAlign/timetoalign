"""AlignmentBundle - The primary entry point for alignment workflows.

This module implements the `AlignmentBundle` class, a single entry point for
all alignment workflows as described in the API redesign specification. The
bundle manages timelines, groups, and coordinate transfer operations.

Phase 1 supports single-group scenarios (perfect alignment).
Future phases will add cross-group matching and WarpMap transfer.

NOTE: As of Phase 7.4, TimelineGroup uses a timestamp-based architecture.
The bundle now uses the new add_timeline() API internally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from timetoalign.core import IdGenerator

from .groups import TimelineGroup

if TYPE_CHECKING:
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)

# Module-level ID generator for bundles
_bundle_id_generator = IdGenerator(scope="bundle")


def _reset_bundle_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _bundle_id_generator
    _bundle_id_generator = IdGenerator(scope="bundle")


# region AlignmentBundle


@dataclass
class AlignmentBundle:
    """The primary entry point for all alignment workflows.

    An AlignmentBundle manages timelines and their alignment relationships.
    It supports "perfect alignment" (linear interpolation within groups)
    for Phase 1, with cross-group matching planned for future phases.

    The bundle provides:
    - Timeline registration and lookup
    - Group management (collections of perfectly aligned timelines)
    - Coordinate transfer between any two timelines in the same group

    IMPORTANT: The resulting bundle structure is order-independent. Adding
    timelines in any order produces the same alignment relationships and
    coordinate transfer results.

    Attributes:
        id: Unique identifier for this bundle.
        name: Optional human-readable name.
        timelines: Dictionary mapping bundle UIDs to Timeline objects.
        groups: Dictionary mapping group IDs to TimelineGroup objects.
        timeline_to_group: Mapping from bundle UID to its containing group ID.

    Note:
        The bundle maintains a UID mapping layer. Users interact with bundle UIDs
        (e.g., "tl1", "tl2"), while groups internally use the actual timeline.id.
        The bundle translates between these two namespaces transparently.

    Examples:
        Basic usage with explicit timelines:

            >>> bundle = AlignmentBundle()
            >>> bundle.add_timeline(score_timeline, uid="score")
            >>> bundle.add_timeline(audio_timeline, uid="audio", aligned_to="score")
            >>> bundle.transfer(100.0, "score", "audio")
            45.5

        SUPRA Piano Roll example:

            >>> bundle = AlignmentBundle(name="SUPRA WM990")
            >>> bundle.add_timeline(image_timeline, uid="dgt1")
            >>> bundle.add_timeline(midi_raw, uid="dlt1", aligned_to="dgt1")
            >>> bundle.add_timeline(midi_exp, uid="dlt2", aligned_to="dgt1")
            >>> bundle.transfer(50000, "dgt1", "dlt1")  # pixels -> ticks
    """

    id: str = field(default="")
    name: str | None = None
    timelines: dict[str, "Timeline"] = field(default_factory=dict)
    groups: dict[str, TimelineGroup] = field(default_factory=dict)
    timeline_to_group: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    # Mapping from bundle UID to actual timeline.id (used by groups)
    _uid_to_timeline_id: dict[str, str] = field(default_factory=dict, repr=False)
    # Reverse mapping from timeline.id to bundle UID
    _timeline_id_to_uid: dict[str, str] = field(default_factory=dict, repr=False)

    # Internal logger
    _logger: logging.Logger = field(
        default_factory=lambda: module_logger, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize ID and logger after dataclass creation."""
        if not self.id:
            self.id = _bundle_id_generator.create(type_hint="AlignmentBundle")
        self._logger = module_logger.getChild(self.id)

    # region Timeline Management

    def add_timeline(
        self,
        timeline: "Timeline",
        *,
        uid: str | None = None,
        aligned_to: str | None = None,
        as_group: str | None = None,
        start: tuple[float, str] | float | None = None,
        end: tuple[float, str] | float | None = None,
    ) -> "AlignmentBundle":
        """Add a timeline, optionally aligned to an existing timeline.

        This is the primary method for adding timelines to the bundle.
        Timelines can be standalone or aligned to existing timelines.

        Args:
            timeline: The Timeline to add.
            uid: Optional explicit ID. If None, uses timeline.id.
            aligned_to: ID of existing timeline to align with.
                If provided, both timelines become part of the same group.
                If the target timeline is not yet in a group, a new group
                is created with the target as reference.
            as_group: Name for the group if creating a new one.
            start: Where this timeline's 0-origin starts in the group.
                - (coord, timeline_id): Position in an existing group timeline
                - float: Coordinate in the aligned_to timeline
                - None: Use group's current start (default for linear alignment)
            end: Where this timeline's end (length) aligns in the group.
                - (coord, timeline_id): Position in an existing group timeline
                - float: Coordinate in the aligned_to timeline
                - None: Use group's current end (default for linear alignment)

        Returns:
            self (for method chaining)

        Raises:
            ValueError: If uid already exists in bundle.
            KeyError: If aligned_to references a non-existent timeline.

        Examples:
            Linear (full-extent) alignment:

                >>> bundle.add_timeline(audio, uid="dgt1")
                >>> bundle.add_timeline(midi, uid="dlt1", aligned_to="dgt1")

            Partial alignment (SUPRA piano roll):

                >>> bundle.add_timeline(image, uid="dgt1")  # Full image
                >>> bundle.add_timeline(
                ...     holes,
                ...     uid="dgt1_holes",
                ...     aligned_to="dgt1",
                ...     start=(15343.0, "dgt1"),  # Musical region starts here
                ...     end=(293119.0, "dgt1"),   # Musical region ends here
                ... )
        """
        # Determine the bundle UID to use
        bundle_uid = uid if uid is not None else timeline.id

        if bundle_uid in self.timelines:
            raise ValueError(f"Timeline '{bundle_uid}' already exists in bundle")

        # Store the UID mapping (bundle_uid -> actual timeline.id)
        actual_tl_id = timeline.id
        self._uid_to_timeline_id[bundle_uid] = actual_tl_id
        self._timeline_id_to_uid[actual_tl_id] = bundle_uid

        # Store timeline with bundle UID as key
        self.timelines[bundle_uid] = timeline

        if aligned_to is not None:
            # Align to existing timeline
            if aligned_to not in self.timelines:
                raise KeyError(f"Cannot align to '{aligned_to}': not in bundle")

            # Get or create group for the target timeline
            if aligned_to in self.timeline_to_group:
                group_id = self.timeline_to_group[aligned_to]
                group = self.groups[group_id]
            else:
                # Create new group with target as first timeline
                target_timeline = self.timelines[aligned_to]
                group_id = as_group or f"group_{aligned_to}"
                group = TimelineGroup(id=group_id, name=as_group)
                group.add_timeline(target_timeline)
                self.groups[group_id] = group
                self.timeline_to_group[aligned_to] = group_id

            # Process start/end parameters for partial alignment
            # Convert bundle UIDs in (coord, uid) tuples to actual timeline IDs
            start_spec = self._convert_boundary_spec(start, aligned_to)
            end_spec = self._convert_boundary_spec(end, aligned_to)

            # Add current timeline to the group with optional partial alignment
            group.add_timeline(timeline, start=start_spec, end=end_spec)
            self.timeline_to_group[bundle_uid] = group_id

            self._logger.debug(
                f"Added timeline '{bundle_uid}' (internal: {actual_tl_id}) "
                f"aligned to '{aligned_to}' in group '{group_id}'"
                f"{' with partial alignment' if start is not None or end is not None else ''}"
            )

        elif as_group is not None:
            # Create standalone group with this timeline
            group = TimelineGroup(id=as_group, name=as_group, timelines=[timeline])
            self.groups[as_group] = group
            self.timeline_to_group[bundle_uid] = as_group

            self._logger.debug(
                f"Added timeline '{bundle_uid}' as first timeline in new group '{as_group}'"
            )

        else:
            # Standalone timeline (not in any group yet)
            self._logger.debug(f"Added standalone timeline '{bundle_uid}'")

        return self

    def get_timeline(self, uid: str) -> "Timeline":
        """Get a timeline by ID.

        Args:
            uid: The timeline's unique identifier.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline with that ID exists.
        """
        if uid not in self.timelines:
            raise KeyError(f"No timeline '{uid}' in bundle '{self.id}'")
        return self.timelines[uid]

    def get_group(self, uid: str) -> TimelineGroup:
        """Get a group by ID.

        Args:
            uid: The group's unique identifier.

        Returns:
            The TimelineGroup object.

        Raises:
            KeyError: If no group with that ID exists.
        """
        if uid not in self.groups:
            raise KeyError(f"No group '{uid}' in bundle '{self.id}'")
        return self.groups[uid]

    def get_group_for_timeline(self, timeline_id: str) -> TimelineGroup | None:
        """Get the group containing a timeline.

        Args:
            timeline_id: The timeline's unique identifier.

        Returns:
            The TimelineGroup containing the timeline, or None if standalone.
        """
        group_id = self.timeline_to_group.get(timeline_id)
        if group_id is None:
            return None
        return self.groups.get(group_id)

    @property
    def n_timelines(self) -> int:
        """Number of timelines in this bundle."""
        return len(self.timelines)

    @property
    def n_groups(self) -> int:
        """Number of groups in this bundle."""
        return len(self.groups)

    @property
    def default_group(self) -> TimelineGroup | None:
        """Get the single group (Phase 1) or primary group.

        Returns:
            The first/only group if one exists, None otherwise.
        """
        if not self.groups:
            return None
        return next(iter(self.groups.values()))

    @property
    def timeline_ids(self) -> list[str]:
        """List of all timeline IDs in the bundle."""
        return list(self.timelines.keys())

    @property
    def group_ids(self) -> list[str]:
        """List of all group IDs in the bundle."""
        return list(self.groups.keys())

    def _convert_boundary_spec(
        self,
        spec: tuple[float, str] | float | None,
        aligned_to: str,
    ) -> tuple[float, str] | float | None:
        """Convert a boundary specification from bundle UIDs to timeline IDs.

        Args:
            spec: The boundary specification (start or end).
            aligned_to: The bundle UID of the aligned_to timeline.

        Returns:
            The converted specification for use with TimelineGroup.add_timeline().
        """
        if spec is None:
            return None

        if isinstance(spec, (int, float)):
            # Float: assume it refers to the aligned_to timeline
            # Convert bundle UID to actual timeline ID
            actual_tl_id = self._uid_to_timeline_id[aligned_to]
            return (float(spec), actual_tl_id)

        if isinstance(spec, tuple):
            coord, bundle_uid = spec
            # Convert bundle UID to actual timeline ID
            if bundle_uid not in self._uid_to_timeline_id:
                raise KeyError(
                    f"Timeline '{bundle_uid}' not found in bundle. "
                    f"Available: {list(self._uid_to_timeline_id.keys())}"
                )
            actual_tl_id = self._uid_to_timeline_id[bundle_uid]
            return (float(coord), actual_tl_id)

        raise ValueError(f"Invalid boundary specification: {spec}")

    # endregion

    # region Coordinate Transfer

    def transfer(
        self,
        coord: float,
        from_timeline: str,
        to_timeline: str,
    ) -> float | None:
        """Transfer a coordinate from one timeline to another.

        Automatically determines the conversion path:
        1. If both timelines are in the same group: direct conversion
        2. If in different groups with matches: uses WarpMap (Phase 2+)
        3. If no path exists: returns None

        This is the primary user-facing method for coordinate conversion.

        Args:
            coord: The coordinate value to transfer.
            from_timeline: ID of the source timeline.
            to_timeline: ID of the target timeline.

        Returns:
            The transferred coordinate, or None if no path exists.

        Raises:
            KeyError: If either timeline is not in the bundle.
        """
        if from_timeline not in self.timelines:
            raise KeyError(f"Source timeline '{from_timeline}' not in bundle")
        if to_timeline not in self.timelines:
            raise KeyError(f"Target timeline '{to_timeline}' not in bundle")

        # Same timeline: no conversion needed
        if from_timeline == to_timeline:
            return coord

        # Check if both are in the same group
        from_group_id = self.timeline_to_group.get(from_timeline)
        to_group_id = self.timeline_to_group.get(to_timeline)

        if from_group_id is not None and from_group_id == to_group_id:
            # Same group: direct conversion via group
            # Translate bundle UIDs to actual timeline IDs used by the group
            group = self.groups[from_group_id]
            actual_from_id = self._uid_to_timeline_id[from_timeline]
            actual_to_id = self._uid_to_timeline_id[to_timeline]
            return group.convert(coord, actual_from_id, actual_to_id)

        # Phase 1: No cross-group transfer yet
        # TODO: Phase 2 will add WarpMap-based cross-group transfer
        self._logger.warning(
            f"Cannot transfer between '{from_timeline}' and '{to_timeline}': "
            f"not in the same group (cross-group transfer not yet implemented)"
        )
        return None

    def transfer_interval(
        self,
        start: float,
        end: float,
        from_timeline: str,
        to_timeline: str,
    ) -> tuple[float, float] | None:
        """Transfer an interval from one timeline to another.

        Args:
            start: Start coordinate in source timeline.
            end: End coordinate in source timeline.
            from_timeline: ID of the source timeline.
            to_timeline: ID of the target timeline.

        Returns:
            Tuple of (start, end) in target timeline, or None if no path.
        """
        transferred_start = self.transfer(start, from_timeline, to_timeline)
        transferred_end = self.transfer(end, from_timeline, to_timeline)

        if transferred_start is None or transferred_end is None:
            return None

        return (transferred_start, transferred_end)

    def are_commensurable(self, timeline_a: str, timeline_b: str) -> bool:
        """Check if two timelines can be connected via transfer.

        In Phase 1, this means they are in the same group.
        Future phases will also check for match paths.

        Args:
            timeline_a: First timeline ID.
            timeline_b: Second timeline ID.

        Returns:
            True if coordinates can be transferred between them.
        """
        if timeline_a == timeline_b:
            return True

        group_a = self.timeline_to_group.get(timeline_a)
        group_b = self.timeline_to_group.get(timeline_b)

        return group_a is not None and group_a == group_b

    # endregion

    # region Summary and Serialization

    def summary(self) -> dict[str, Any]:
        """Get a summary of the bundle contents.

        Returns a deterministic representation suitable for comparison.
        Keys and timeline lists are sorted for order-independence.

        Returns:
            Dictionary with bundle information.
        """
        timeline_info = {}
        for tl_id in sorted(self.timelines.keys()):
            tl = self.timelines[tl_id]
            group_id = self.timeline_to_group.get(tl_id)
            timeline_info[tl_id] = {
                "name": tl.name,
                "length": (
                    float(tl.length.value) if hasattr(tl.length, "value") else tl.length
                ),
                "unit": str(tl.unit) if hasattr(tl, "unit") else None,
                "group": group_id,
            }

        group_info = {}
        for grp_id in sorted(self.groups.keys()):
            grp = self.groups[grp_id]
            group_info[grp_id] = {
                "name": grp.name,
                "reference": grp.reference_timeline_id,
                "n_timelines": grp.n_timelines,
                "timeline_ids": sorted(grp.timeline_ids),
            }

        return {
            "id": self.id,
            "name": self.name,
            "n_timelines": len(self.timelines),
            "n_groups": len(self.groups),
            "timelines": timeline_info,
            "groups": group_info,
            "meta": self.meta,
        }

    def __repr__(self) -> str:
        name_str = f", name={self.name!r}" if self.name else ""
        return (
            f"AlignmentBundle(id={self.id!r}{name_str}, "
            f"timelines={len(self.timelines)}, groups={len(self.groups)})"
        )

    # endregion


# endregion
