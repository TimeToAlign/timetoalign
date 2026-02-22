"""AlignmentBundle - The primary entry point for alignment workflows.

This module implements the `AlignmentBundle` class, a single entry point for
all alignment workflows as described in the API redesign specification. The
bundle manages timelines, groups, and coordinate transfer operations.

Phase 1 supports single-group scenarios (perfect alignment).
Phase 2 adds cross-group matching via MatchClaims and WarpMaps, enabling
the ``get_timestamp_at()`` method for grouped cross-domain coordinate transfer.

NOTE: As of Phase 7.4, TimelineGroup uses a timestamp-based architecture.
The bundle now uses the new add_timeline() API internally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from timetoalign.core import IdCoordinate, IdGenerator

from .anchors import MatchClaim
from .groups import TimelineGroup

if TYPE_CHECKING:
    from timetoalign.maps import TableMap
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
    cross_group_claims: list[MatchClaim] = field(default_factory=list)

    # Mapping from bundle UID to actual timeline.id (used by groups)
    _uid_to_timeline_id: dict[str, str] = field(default_factory=dict, repr=False)
    # Reverse mapping from timeline.id to bundle UID
    _timeline_id_to_uid: dict[str, str] = field(default_factory=dict, repr=False)
    # Cached WarpMaps for cross-group transfer: (from_group, to_group) -> TableMap
    _warp_maps: dict[tuple[str, str], "TableMap"] = field(
        default_factory=dict, repr=False
    )

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
        start: IdCoordinate | tuple[float, str] | float | None = None,
        end: IdCoordinate | tuple[float, str] | float | None = None,
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
                - IdCoordinate: Coordinate with explicit timeline_id (preferred)
                - (coord, timeline_id): Legacy tuple form
                - float: Coordinate in the aligned_to timeline
                - None: Use group's current start (default for linear alignment)
            end: Where this timeline's end (length) aligns in the group.
                - Same options as start
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

            Partial alignment (SUPRA piano roll) using IdCoordinate:

                >>> from timetoalign import IdCoordinate, TimeUnit
                >>> bundle.add_timeline(image, uid="dgt1")  # Full image
                >>> bundle.add_timeline(
                ...     holes,
                ...     uid="dgt1_holes",
                ...     aligned_to="dgt1",
                ...     start=IdCoordinate(15343.0, TimeUnit.pixels, "dgt1"),
                ...     end=IdCoordinate(293119.0, TimeUnit.pixels, "dgt1"),
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

    def add_group(
        self,
        group: TimelineGroup,
        *,
        uid_map: dict[str, str] | None = None,
    ) -> "AlignmentBundle":
        """Add a pre-built TimelineGroup with all its timelines at once.

        This is the bulk-registration counterpart of ``add_timeline(..., as_group=...)``.
        It registers the group and every timeline it already contains into the
        bundle's bookkeeping (UID mapping, timeline registry, group registry).

        Args:
            group: A ``TimelineGroup`` that already contains timelines.
            uid_map: Optional mapping from timeline.id to desired bundle UID.
                If not provided, each timeline's ``id`` is used as its bundle UID.

        Returns:
            self (for method chaining)

        Raises:
            ValueError: If the group ID already exists in the bundle, or
                if any timeline UID would collide with an existing one.

        Examples:
            Add a recording group with 5 DPTs:

                >>> grp = TimelineGroup(id="normal", timelines=[dpt1, dpt2, dpt3])
                >>> bundle.add_group(grp)

            With custom UIDs:

                >>> bundle.add_group(grp, uid_map={"dpt:1": "audio", "dpt:2": "midi"})
        """
        if group.id in self.groups:
            raise ValueError(f"Group '{group.id}' already exists in bundle")

        # Validate UIDs before mutating state
        uid_map = uid_map or {}
        planned_uids: list[tuple[str, str]] = []  # (bundle_uid, actual_tl_id)
        for tl_id in group.timeline_ids:
            bundle_uid = uid_map.get(tl_id, tl_id)
            if bundle_uid in self.timelines:
                raise ValueError(
                    f"Timeline '{bundle_uid}' already exists in bundle "
                    f"(from group '{group.id}' timeline '{tl_id}')"
                )
            planned_uids.append((bundle_uid, tl_id))

        # Register the group
        self.groups[group.id] = group

        # Register each timeline
        for bundle_uid, actual_tl_id in planned_uids:
            tl = group.get_timeline(actual_tl_id)
            self.timelines[bundle_uid] = tl
            self._uid_to_timeline_id[bundle_uid] = actual_tl_id
            self._timeline_id_to_uid[actual_tl_id] = bundle_uid
            self.timeline_to_group[bundle_uid] = group.id

        self._logger.debug(
            f"Added group '{group.id}' with {len(planned_uids)} timelines"
        )

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
        spec: IdCoordinate | tuple[float, str] | float | None,
        aligned_to: str,
    ) -> IdCoordinate | tuple[float, str] | float | None:
        """Convert a boundary specification from bundle UIDs to timeline IDs.

        Args:
            spec: The boundary specification (start or end).
                - IdCoordinate: Uses timeline_id attribute as bundle UID (preferred)
                - (coord, bundle_uid): Legacy tuple form
                - float: Coordinate in the aligned_to timeline
                - None: Use defaults
            aligned_to: The bundle UID of the aligned_to timeline.

        Returns:
            The converted specification for use with TimelineGroup.add_timeline().
            IdCoordinate is converted to have the actual timeline ID.
        """
        if spec is None:
            return None

        if isinstance(spec, IdCoordinate):
            # IdCoordinate: convert bundle UID to actual timeline ID
            bundle_uid = spec.timeline_id
            if bundle_uid not in self._uid_to_timeline_id:
                raise KeyError(
                    f"Timeline '{bundle_uid}' not found in bundle. "
                    f"Available: {list(self._uid_to_timeline_id.keys())}"
                )
            actual_tl_id = self._uid_to_timeline_id[bundle_uid]
            return spec.with_timeline(actual_tl_id)

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

    # region Cross-Group Claims

    def add_match_claims(
        self,
        claims: list[MatchClaim],
        *,
        build_warp_maps: bool = True,
    ) -> "AlignmentBundle":
        """Add MatchClaims connecting timelines across different groups.

        MatchClaims encode coordinate correspondences between timelines in
        different groups (e.g., EEP recording notes matched to ABC score notes).
        They enable cross-group coordinate transfer via WarpMaps.

        Args:
            claims: List of MatchClaim objects. Each claim connects two
                timelines via its start_anchor (and optionally end_anchor).
            build_warp_maps: If True, automatically build WarpMaps (TableMaps)
                from the claims for efficient interpolation. Default True.

        Returns:
            self (for method chaining)
        """
        self.cross_group_claims.extend(claims)
        if build_warp_maps:
            self._build_warp_maps_from_claims(claims)
        return self

    def _build_warp_maps_from_claims(self, claims: list[MatchClaim]) -> None:
        """Build WarpMaps (TableMaps) from MatchClaims for interpolation.

        Groups claims by (source_group, target_group) and builds a TableMap
        for each direction.

        Args:
            claims: MatchClaims to build WarpMaps from.
        """
        from collections import defaultdict

        from timetoalign.maps import TableMap

        # Group claims by the pair of groups they connect
        # Key: (timeline_a_id, timeline_b_id) from anchors
        pair_coords: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(
            list
        )

        for claim in claims:
            anchor = claim.start_anchor
            tl_a = anchor.timeline_a_id
            tl_b = anchor.timeline_b_id
            pair_coords[(tl_a, tl_b)].append((anchor.coordinate_a, anchor.coordinate_b))

        # Build TableMaps for each pair
        for (tl_a, tl_b), coords in pair_coords.items():
            if len(coords) < 2:
                continue  # Need at least 2 points for interpolation

            # Sort by source coordinate for monotonic interpolation
            coords.sort(key=lambda c: c[0])
            x_values = [c[0] for c in coords]
            y_values = [c[1] for c in coords]

            # Forward map: tl_a -> tl_b
            try:
                forward_map = TableMap(
                    x_values=x_values,
                    y_values=y_values,
                    uid=f"warp_{tl_a}_to_{tl_b}",
                )
                self._warp_maps[(tl_a, tl_b)] = forward_map
            except Exception as e:
                self._logger.warning(f"Failed to build WarpMap {tl_a}->{tl_b}: {e}")

            # Reverse map: tl_b -> tl_a
            # Sort by target coordinate
            coords_rev = sorted(coords, key=lambda c: c[1])
            x_rev = [c[1] for c in coords_rev]
            y_rev = [c[0] for c in coords_rev]
            try:
                reverse_map = TableMap(
                    x_values=x_rev,
                    y_values=y_rev,
                    uid=f"warp_{tl_b}_to_{tl_a}",
                )
                self._warp_maps[(tl_b, tl_a)] = reverse_map
            except Exception as e:
                self._logger.warning(f"Failed to build WarpMap {tl_b}->{tl_a}: {e}")

        self._logger.debug(
            f"Built {len(self._warp_maps)} WarpMaps from {len(claims)} claims"
        )

    def get_warp_map(self, from_timeline: str, to_timeline: str) -> "TableMap | None":
        """Get the WarpMap for converting coordinates between two timelines.

        Args:
            from_timeline: Source timeline ID.
            to_timeline: Target timeline ID.

        Returns:
            TableMap for interpolation, or None if no map exists.
        """
        return self._warp_maps.get((from_timeline, to_timeline))

    # endregion

    # region Grouped Timestamp API

    def get_timestamp_at(
        self,
        coordinate: float,
        timeline_id: str,
        *,
        format: Literal["prefix", "nested", "flat"] = "prefix",
    ) -> dict[str, Any]:
        """Get a cross-group timestamp at a coordinate on a given timeline.

        This is the primary method for cross-domain coordinate transfer.
        Given a coordinate on one timeline, it returns the corresponding
        coordinates on ALL connected timelines across ALL groups.

        The method:
        1. Finds the group containing the source timeline
        2. Gets the within-group timestamp (via group.get_timestamp_at())
        3. For each connected group (via WarpMaps from MatchClaims),
           transfers the coordinate and gets the within-group timestamp
        4. Returns all coordinates in the requested format

        Args:
            coordinate: The coordinate value on the source timeline.
            timeline_id: ID of the source timeline (bundle UID).
            format: Output format:
                - ``"prefix"`` (default): ``{"group/timeline": coord, ...}``
                - ``"nested"``: ``{"group": {"timeline": coord, ...}, ...}``
                - ``"flat"``: ``{"timeline": coord, ...}``

        Returns:
            Dict of coordinates across all connected groups and timelines.
            Timelines that cannot be reached return None values.

        Raises:
            KeyError: If timeline_id is not in the bundle.

        Examples:
            >>> ts = bundle.get_timestamp_at(50.0, "clt1_score", format="prefix")
            >>> ts
            {'score/clt1_score': 50.0, 'score/dgt1': 45000.0,
             'normal/dpt1': 23456789, ...}

            >>> ts = bundle.get_timestamp_at(50.0, "clt1_score", format="nested")
            >>> ts
            {'score': {'clt1_score': 50.0, 'dgt1': 45000.0},
             'normal': {'dpt1': 23456789, ...}, ...}
        """
        if timeline_id not in self.timelines:
            raise KeyError(f"Timeline '{timeline_id}' not in bundle")

        # Get the source group
        source_group_id = self.timeline_to_group.get(timeline_id)
        if source_group_id is None:
            # Standalone timeline — return just its coordinate
            return self._format_timestamp(
                {timeline_id: {timeline_id: coordinate}}, format
            )

        source_group = self.groups[source_group_id]
        actual_tl_id = self._uid_to_timeline_id[timeline_id]

        # Step 1: Get within-group timestamp for the source group
        result: dict[str, dict[str, float | None]] = {}
        source_ts = self._get_group_timestamp(source_group, coordinate, actual_tl_id)
        result[source_group_id] = source_ts

        # Step 2: Transfer to connected groups via WarpMaps
        for other_group_id, other_group in self.groups.items():
            if other_group_id == source_group_id:
                continue

            # Find a WarpMap that connects source group to this group
            transferred_coord = self._transfer_to_group(
                coordinate, actual_tl_id, source_group, other_group
            )
            if transferred_coord is not None:
                target_tl_id, target_coord = transferred_coord
                other_ts = self._get_group_timestamp(
                    other_group, target_coord, target_tl_id
                )
                result[other_group_id] = other_ts

        return self._format_timestamp(result, format)

    def _get_group_timestamp(
        self,
        group: TimelineGroup,
        coordinate: float,
        timeline_id: str,
    ) -> dict[str, float | None]:
        """Get timestamp within a group, mapped to bundle UIDs.

        Args:
            group: The TimelineGroup.
            coordinate: Coordinate in the source timeline.
            timeline_id: Actual timeline ID (not bundle UID).

        Returns:
            Dict mapping bundle UIDs to coordinates.
        """
        result: dict[str, float | None] = {}

        try:
            ts = group.get_timestamp_at(coordinate, timeline_id)
            for tl_id in group.timeline_ids:
                bundle_uid = self._timeline_id_to_uid.get(tl_id, tl_id)
                coord = ts.get(tl_id)
                result[bundle_uid] = coord
        except Exception as e:
            self._logger.debug(
                f"Failed to get group timestamp at {coordinate} on {timeline_id}: {e}"
            )
            # Return what we can: source coordinate at least
            bundle_uid = self._timeline_id_to_uid.get(timeline_id, timeline_id)
            result[bundle_uid] = coordinate

        return result

    def _transfer_to_group(
        self,
        coordinate: float,
        source_tl_id: str,
        source_group: TimelineGroup,
        target_group: TimelineGroup,
    ) -> tuple[str, float] | None:
        """Transfer a coordinate from one group to another via WarpMaps.

        Looks for any WarpMap connecting a timeline in source_group to a
        timeline in target_group. If found, uses it to interpolate the
        coordinate.

        Args:
            coordinate: Source coordinate.
            source_tl_id: Source timeline ID (actual, not bundle UID).
            source_group: Source group.
            target_group: Target group.

        Returns:
            (target_timeline_id, transferred_coordinate) or None.
        """
        # Try direct WarpMap from source_tl_id to any timeline in target group
        for target_tl_id in target_group.timeline_ids:
            warp = self._warp_maps.get((source_tl_id, target_tl_id))
            if warp is not None:
                try:
                    transferred = warp(coordinate)
                    return (target_tl_id, float(transferred))
                except Exception:
                    continue

        # Try indirect: first convert within source group, then WarpMap
        for src_other_tl_id in source_group.timeline_ids:
            if src_other_tl_id == source_tl_id:
                continue
            # Convert coordinate within source group
            try:
                intermediate = source_group.convert(
                    coordinate, source=source_tl_id, target=src_other_tl_id
                )
                if intermediate is None:
                    continue
            except (KeyError, ValueError):
                continue

            # Try WarpMap from intermediate to target group
            for target_tl_id in target_group.timeline_ids:
                warp = self._warp_maps.get((src_other_tl_id, target_tl_id))
                if warp is not None:
                    try:
                        transferred = warp(float(intermediate))
                        return (target_tl_id, float(transferred))
                    except Exception:
                        continue

        return None

    def _format_timestamp(
        self,
        grouped: dict[str, dict[str, float | None]],
        fmt: Literal["prefix", "nested", "flat"],
    ) -> dict[str, Any]:
        """Format a grouped timestamp dict into the requested output format.

        Args:
            grouped: Dict of group_id -> {bundle_uid -> coordinate}.
            fmt: Output format.

        Returns:
            Formatted dict.
        """
        if fmt == "nested":
            return grouped

        if fmt == "prefix":
            result: dict[str, Any] = {}
            for group_id, tl_coords in grouped.items():
                for tl_id, coord in tl_coords.items():
                    result[f"{group_id}/{tl_id}"] = coord
            return result

        if fmt == "flat":
            result = {}
            for tl_coords in grouped.values():
                result.update(tl_coords)
            return result

        raise ValueError(f"Unknown format: {fmt!r}. Use 'prefix', 'nested', or 'flat'")

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

    def __str__(self) -> str:
        """Return human-readable ASCII diagram of the bundle.

        Uses the diagram() method to generate a visual representation
        showing all groups and their member timelines.
        """
        return self.diagram()

    # endregion

    # region Display

    def diagram(
        self,
        width: int = 80,
        show_children: bool = True,
        max_children: int = 6,
        unicode: bool = True,
    ) -> str:
        """Generate ASCII diagram for this bundle.

        Args:
            width: Total width of the diagram in characters.
            show_children: Whether to expand child timelines.
            max_children: Maximum children per timeline.
            unicode: Use Unicode characters (True) or ASCII fallback (False).

        Returns:
            Multi-line string with ASCII diagram.

        Examples:
            >>> print(bundle.diagram())
            AlignmentBundle[thoresen_alignment]

              TimelineGroup[dgt1_group] (2 timelines, 2 timestamps)
              ┌──────────────────────────────────────────────────────┐
              │ DiscreteGraphicalTimeline[dgt1:1] (11 events)        │
              │ 0 ::::::::::::::::::::::::::::::::::: 4835 pixels    │
              └──────────────────────────────────────────────────────┘
              Timestamps: 2

              MatchClaims: 5
        """
        from timetoalign.display.ascii import bundle_diagram

        return bundle_diagram(
            self,
            width=width,
            show_children=show_children,
            max_children=max_children,
            unicode=unicode,
        )

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the ASCII diagram in a monospace pre block so it
        renders correctly in notebook output cells.
        """
        import html

        diagram_text = html.escape(self.diagram())
        return f'<pre style="font-family: monospace; line-height: 1.2;">{diagram_text}</pre>'

    # endregion


# endregion
