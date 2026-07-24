"""AlignmentBundle - The primary entry point for alignment workflows.

This module implements the `AlignmentBundle` class, a single entry point for
all alignment workflows as described in the API redesign specification. The
bundle manages timelines, groups, and coordinate transfer operations.

Within a group, coordinate transfer uses linear interpolation
(``TimelineGroup.convert()``).  Across groups, transfer is mediated by
the ``MatchClaim`` -> ``MatchLine`` -> ``WarpMap`` pipeline.
WarpMaps are built lazily and cached for repeated queries.

TimelineGroup uses a timestamp-based architecture. The bundle uses
the add_timeline() API internally.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from timetoalign.core import (
    Coordinate,
    CoordinateSpec,
    IdCoordinate,
    IdGenerator,
    resolve_coordinate_spec,
    resolve_id,
)
from timetoalign.timelines import TimelineGroup

from .claims import MatchClaim, MatchClaimField
from .filters import ClaimFilter
from .graph import MatchGraph, MatchStamp
from .matchline import MatchLine
from .warpmap import AmbiguousWarpMapError, WarpMap

if TYPE_CHECKING:
    import pyarrow as pa

    from timetoalign.core.enums import Domain, TimeUnit
    from timetoalign.core.timestamp import ConversionMapsSpec
    from timetoalign.display.ascii import Diagram
    from timetoalign.maps.base import ConversionMap
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)

# Module-level ID generator for bundles
_bundle_id_generator = IdGenerator(scope="bundle")


def _reset_bundle_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _bundle_id_generator
    _bundle_id_generator = IdGenerator(scope="bundle")


def _resolve_coordinate_and_timeline(
    coordinate: CoordinateSpec,
    timeline_id: str | None,
) -> tuple[int | float | Fraction, str | None, "TimeUnit | None"]:
    """Decompose a coordinate specification and resolve its timeline.

    Accepts the three canonical coordinate forms and returns the underlying
    value, unit, and timeline the coordinate lives on. When the coordinate is
    an ``IdCoordinate`` it carries its own ``timeline_id``, which fills an
    omitted ``timeline_id`` argument.

    Args:
        coordinate: The query coordinate. One of:

            - int/float/Fraction: Raw value, ``timeline_id`` required.
            - Coordinate: Value with unit, ``timeline_id`` required.
            - IdCoordinate: Value, unit AND timeline_id (``timeline_id`` param
              optional).
        timeline_id: Explicit timeline id, or None to take it from an
            ``IdCoordinate``.

    Returns:
        A ``(coord_value, timeline_id, unit)`` tuple. ``timeline_id`` may
        still be None if a non-Id coordinate was passed without one; callers
        decide whether that is an error.

    Raises:
        TypeError: If ``coordinate`` is not one of the accepted forms.
    """
    resolved = resolve_coordinate_spec(coordinate, timeline_id=timeline_id)
    return resolved.value, resolved.timeline_id, resolved.unit


# region AlignmentBundle


@dataclass
class AlignmentBundle:
    """The primary entry point for all alignment workflows.

    An AlignmentBundle manages timelines and their alignment relationships.
    Within a group, coordinate transfer uses linear interpolation
    (``TimelineGroup.convert()``).  Across groups, transfer is mediated
    by the ``MatchClaim`` → ``MatchLine`` → ``WarpMap`` pipeline.

    The bundle provides:

    - Timeline registration and lookup
    - Group management (collections of perfectly aligned timelines)
    - Coordinate transfer between any two timelines (same-group or
      cross-group via ``MatchClaim``/``WarpMap``)

    IMPORTANT: The resulting bundle structure is order-independent. Adding
    timelines in any order produces the same alignment relationships and
    coordinate transfer results.

    Attributes:
        id: Unique identifier for this bundle.
        name: Optional human-readable name.
        timelines: Dictionary mapping bundle UIDs to Timeline objects.
        groups: Dictionary mapping group IDs to TimelineGroup objects.
        timeline_to_group: Mapping from bundle UID to its containing group ID.
        cross_group_claims: MatchClaims connecting timelines across groups
            (the per-claim Python-list store).
        cross_group_claim_fields: Columnar ``MatchClaimField`` stores of dense
            synchronous-instant pairwise claims, queried vectorized without
            materialising the full claim list.

    Note:
        The two claim stores are interchangeable as far as queries are
        concerned: every reader consults both, so a bundle whose claims live
        in a ``MatchClaimField`` answers exactly as a bundle holding the same
        claims in the Python list.  What differs is cost — ``MatchClaimField``
        queries stay vectorized, and ``get_claim_fields()`` is the accessor
        that keeps them that way.

    Note:
        The bundle maintains a UID mapping layer. Users interact with bundle UIDs
        (e.g., "tl1", "tl2"), while groups internally use the actual timeline.id.
        The bundle translates between these two namespaces transparently.

    Examples:
        >>> bundle = AlignmentBundle()
        >>> bundle.add_timeline(score_timeline, uid="score")
        >>> bundle.add_timeline(audio_timeline, uid="audio", aligned_to="score")
        >>> stamp = bundle.get_matchstamp_at(100.0, "score")
        >>> stamp.get("audio")
        45.5
    """

    id: str = field(default="")
    name: str | None = None
    timelines: dict[str, "Timeline"] = field(default_factory=dict)
    groups: dict[str, TimelineGroup] = field(default_factory=dict)
    timeline_to_group: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    cross_group_claims: list[MatchClaim] = field(default_factory=list)
    # Columnar claim stores added additively (e.g. by ListenHereLoader). Each
    # holds a dense set of synchronous instant pairwise claims as a single
    # PyArrow struct column. Queries filter these vectorized and materialise
    # only the matched rows — a million-claim field is never exploded into a
    # Python list. The Python-list ``cross_group_claims`` path is unchanged.
    cross_group_claim_fields: list[MatchClaimField] = field(default_factory=list)

    # Mapping from bundle UID to actual timeline.id (used by groups)
    _uid_to_timeline_id: dict[str, str] = field(default_factory=dict, repr=False)
    # Reverse mapping from timeline.id to bundle UID
    _timeline_id_to_uid: dict[str, str] = field(default_factory=dict, repr=False)
    # Cached WarpMaps: (source_tl_id, target_tl_id) -> WarpMap | None
    # None values are cached as negative results to avoid repeated expensive
    # MatchLine construction for unreachable timeline pairs.
    _warp_map_cache: dict[tuple[str, str], WarpMap | None] = field(
        default_factory=dict, repr=False
    )
    # Cached MatchLines: source_tl_id -> MatchLine (avoids rebuilding the
    # expensive MatchGraph + group extension for every target lookup)
    _matchline_cache: dict[str, MatchLine | None] = field(
        default_factory=dict, repr=False
    )
    # Cached MatchGraphs: (timeline_id, coordinate) -> MatchGraph
    _matchgraph_cache: dict[tuple[str, float], MatchGraph] = field(
        default_factory=dict, repr=False
    )
    # Hash of cross_group_claims list at time of last cache build
    _cache_claims_hash: int = field(default=0, repr=False)

    # Internal logger
    _logger: logging.Logger = field(
        default_factory=lambda: module_logger, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize ID and logger after dataclass creation."""
        if not self.id:
            self.id = _bundle_id_generator.create(type_hint="AlignmentBundle")
        self._logger = module_logger.getChild(self.id)

    @classmethod
    def from_bundles(
        cls,
        bundles: list["AlignmentBundle"],
        *,
        id: str = "",
        name: str | None = None,
    ) -> "AlignmentBundle":
        """Merge multiple bundles' groups, standalone timelines, and claims.

        Registers every group and standalone timeline from each source
        bundle into a new bundle, preserving each source's bundle-UID
        namespace, and carries over every cross-group ``MatchClaim`` (both
        the per-claim list and any columnar ``MatchClaimField`` stores)
        unchanged. Groups from different source bundles remain distinct —
        merging does not itself align timelines across bundles. Add
        cross-group MatchClaims (e.g. via :meth:`create_match_claims`)
        afterwards to align them.

        Args:
            bundles: The bundles to merge, in order.
            id: Explicit ID for the merged bundle. Auto-generated if omitted.
            name: Optional human-readable name for the merged bundle.

        Returns:
            A new AlignmentBundle containing every group, standalone
            timeline, and cross-group claim from ``bundles``.

        Raises:
            ValueError: If two source bundles share a group ID, or a
                timeline UID collision would occur across bundles.

        Examples:
            >>> merged = AlignmentBundle.from_bundles([score_bundle, audio_bundle])
            >>> merged.groups.keys() == score_bundle.groups.keys() | audio_bundle.groups.keys()
            True
        """
        merged = cls(id=id, name=name)
        for bundle in bundles:
            uid_map = {tl.id: bundle_uid for bundle_uid, tl in bundle.timelines.items()}
            for group in bundle.groups.values():
                merged.add_group(group, uid_map=uid_map)
            for bundle_uid, timeline in bundle.timelines.items():
                if bundle_uid not in bundle.timeline_to_group:
                    merged.add_timeline(timeline, uid=bundle_uid)
            merged.add_match_claims(bundle.cross_group_claims)
            for claim_field in bundle.cross_group_claim_fields:
                merged.add_match_claim_field(claim_field)
        return merged

    # region Timeline Management

    def add_timeline(
        self,
        timeline: "Timeline",
        *,
        uid: str | None = None,
        aligned_to: str | None = None,
        as_group: str | None = None,
        start: CoordinateSpec | None = None,
        end: CoordinateSpec | None = None,
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
                - CoordinateSpec: Coordinate in the aligned_to timeline
                - IdCoordinate: Coordinate with explicit timeline_id (preferred)
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

            # Process start/end parameters for partial alignment.
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

        Supports partial string and regex matching:
        1. Exact match: If ``uid`` matches an ID exactly, returns it.
        2. Substring match: If ``uid`` is a substring of exactly one ID,
           returns that timeline. If multiple match, returns the first and warns.
        3. Regex match: If ``uid`` is a valid regex, matches via
           ``re.search()``. Same first-match logic with warning.

        Args:
            uid: The timeline's unique identifier, or a partial/regex pattern.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline matches the pattern.

        Examples:
            >>> bundle.get_timeline("clt1")          # Exact match
            >>> bundle.get_timeline("score")         # Substring match
            >>> bundle.get_timeline(r"^perf:")       # Regex match
        """
        resolved_id = resolve_id(uid, list(self.timelines.keys()))
        return self.timelines[resolved_id]

    def get_group(self, uid: str) -> TimelineGroup:
        """Get a group by ID.

        Supports partial string and regex matching:
        1. Exact match: If ``uid`` matches an ID exactly, returns it.
        2. Substring match: If ``uid`` is a substring of exactly one ID,
           returns that group. If multiple match, returns the first and warns.
        3. Regex match: If ``uid`` is a valid regex, matches via
           ``re.search()``. Same first-match logic with warning.

        Args:
            uid: The group's unique identifier, or a partial/regex pattern.

        Returns:
            The TimelineGroup object.

        Raises:
            KeyError: If no group matches the pattern.

        Examples:
            >>> bundle.get_group("score")            # Substring match
            >>> bundle.get_group(r"^perf")           # Regex match
        """
        resolved_id = resolve_id(uid, list(self.groups.keys()))
        return self.groups[resolved_id]

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

    def get_timelines(self, ids: list[str]) -> list["Timeline"]:
        """Get multiple timelines by their IDs.

        Convenience method for retrieving several timelines at once.
        Each ID supports partial string and regex matching (via
        ``get_timeline()``).

        Args:
            ids: List of timeline IDs (or partial/regex patterns).

        Returns:
            List of Timeline objects in the same order as the input IDs.

        Raises:
            KeyError: If any timeline ID is not found.

        Examples:
            >>> timelines = bundle.get_timelines(["score", "audio", "midi"])
            >>> len(timelines)
            3
        """
        return [self.get_timeline(uid) for uid in ids]

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
        """Get the single group or primary group.

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
        spec: CoordinateSpec | None,
        aligned_to: str,
    ) -> CoordinateSpec | None:
        """Convert a boundary specification from bundle UIDs to timeline IDs.

        Args:
            spec: The boundary specification (start or end).
                - CoordinateSpec: Uses the aligned_to timeline as context
                - IdCoordinate: Uses timeline_id attribute as bundle UID
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

        resolved = resolve_coordinate_spec(spec)
        actual_tl_id = self._uid_to_timeline_id[aligned_to]
        unit = resolved.unit or self.timelines[actual_tl_id].unit
        return IdCoordinate(resolved.value, unit, actual_tl_id)

    # endregion

    # region Coordinate Transfer

    def transfer(
        self,
        coord: CoordinateSpec,
        from_timeline: str,
        to_timeline: str,
    ) -> float | None:
        """Transfer a coordinate from one timeline to another.

        Automatically determines the conversion path:

        1. If both timelines are in the same group: direct conversion via
           ``TimelineGroup.convert()``.
        2. If in different groups with MatchClaims: builds a ``MatchLine``
           and a cached ``WarpMap`` and calls it to
           interpolate the coordinate.
        3. If no path exists: returns ``None``.

        Low-level coordinate transfer utility. For user-facing coordinate
        queries, use ``get_matchstamp_at()`` which returns a full cross-section
        as a MatchStamp.

        Args:
            coord: The coordinate value to transfer.
            from_timeline: Bundle UID of the source timeline.
            to_timeline: Bundle UID of the target timeline.

        Returns:
            The transferred coordinate, or None if no path exists.

        Raises:
            KeyError: If either timeline is not in the bundle.
        """
        if from_timeline not in self.timelines:
            raise KeyError(f"Source timeline '{from_timeline}' not in bundle")
        if to_timeline not in self.timelines:
            raise KeyError(f"Target timeline '{to_timeline}' not in bundle")

        coord_value, _resolved_timeline_id, unit = _resolve_coordinate_and_timeline(
            coord, from_timeline
        )
        if unit is not None:
            coord = float(
                self.get_timeline(from_timeline)
                .resolve_coordinate(Coordinate(coord_value, unit))
                .value
            )
        else:
            coord = float(coord_value)

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

        # Cross-group transfer via MatchLine/WarpMap pipeline
        actual_from_id = self._uid_to_timeline_id[from_timeline]
        actual_to_id = self._uid_to_timeline_id[to_timeline]

        warp = self._get_or_build_warp_map(actual_from_id, actual_to_id)
        if warp is not None:
            try:
                return float(warp(coord))
            except Exception as e:
                self._logger.warning(
                    "WarpMap forward failed for %s -> %s at %s: %s",
                    from_timeline,
                    to_timeline,
                    coord,
                    e,
                )
                return None

        # Try indirect via SOURCE group: convert within source, then warp
        if from_group_id is not None:
            source_group = self.groups[from_group_id]
            for src_other_tl_id in source_group.timeline_ids:
                if src_other_tl_id == actual_from_id:
                    continue
                warp = self._get_or_build_warp_map(src_other_tl_id, actual_to_id)
                if warp is None:
                    continue
                try:
                    intermediate = source_group.convert(
                        coord, source=actual_from_id, target=src_other_tl_id
                    )
                    if intermediate is None:
                        continue
                    return float(warp(float(intermediate)))
                except Exception:
                    continue

        # Try indirect via TARGET group: warp to reachable group member,
        # then convert within the target group.
        if to_group_id is not None:
            target_group = self.groups[to_group_id]
            for tgt_other_tl_id in target_group.timeline_ids:
                if tgt_other_tl_id == actual_to_id:
                    continue
                warp = self._get_or_build_warp_map(actual_from_id, tgt_other_tl_id)
                if warp is None:
                    continue
                try:
                    warped = float(warp(coord))
                    conv = self._get_claim_to_native_converter(tgt_other_tl_id)
                    if conv is not None:
                        warped = float(conv(warped))
                    result = target_group.convert(
                        warped, source=tgt_other_tl_id, target=actual_to_id
                    )
                    if result is None:
                        continue
                    return float(result)
                except Exception:
                    continue

        self._logger.debug(
            "No transfer path between '%s' and '%s'",
            from_timeline,
            to_timeline,
        )
        return None

    def transfer_interval(
        self,
        start: CoordinateSpec,
        end: CoordinateSpec,
        from_timeline: str,
        to_timeline: str,
    ) -> tuple[float, float] | None:
        """Transfer an interval from one timeline to another.

        Args:
            start: Start coordinate in source timeline. Accepts a raw
                int/float/Fraction, a Coordinate, or an IdCoordinate.
            end: End coordinate in source timeline. Accepts a raw
                int/float/Fraction, a Coordinate, or an IdCoordinate.
            from_timeline: ID of the source timeline.
            to_timeline: ID of the target timeline.

        Returns:
            Tuple of (start, end) in target timeline, or None if no path.
        """
        start_value, _start_timeline_id, start_unit = _resolve_coordinate_and_timeline(
            start, from_timeline
        )
        end_value, _end_timeline_id, end_unit = _resolve_coordinate_and_timeline(
            end, from_timeline
        )
        source_timeline = self.get_timeline(from_timeline)
        start = float(
            source_timeline.resolve_coordinate(
                Coordinate(start_value, start_unit)
            ).value
            if start_unit is not None
            else start_value
        )
        end = float(
            source_timeline.resolve_coordinate(Coordinate(end_value, end_unit)).value
            if end_unit is not None
            else end_value
        )
        transferred_start = self.transfer(start, from_timeline, to_timeline)
        transferred_end = self.transfer(end, from_timeline, to_timeline)

        if transferred_start is None or transferred_end is None:
            return None

        return (transferred_start, transferred_end)

    def are_commensurable(self, timeline_a: str, timeline_b: str) -> bool:
        """Check if two timelines can be connected via transfer.

        Two timelines are commensurable if they share the same group
        or if a cross-group path exists via MatchClaims.

        Args:
            timeline_a: First timeline ID (bundle UID).
            timeline_b: Second timeline ID (bundle UID).

        Returns:
            True if coordinates can be transferred between them.
        """
        if timeline_a == timeline_b:
            return True

        group_a = self.timeline_to_group.get(timeline_a)
        group_b = self.timeline_to_group.get(timeline_b)

        # Same group: commensurable
        if group_a is not None and group_a == group_b:
            return True

        # Check for cross-group path via claims
        if self.n_cross_group_claims == 0:
            return False

        actual_a = self._uid_to_timeline_id.get(timeline_a, timeline_a)
        actual_b = self._uid_to_timeline_id.get(timeline_b, timeline_b)

        # Check if any synchronous claim connects groups containing a and b
        group_a_tl_ids = (
            set(self.groups[group_a].timeline_ids) if group_a else {actual_a}
        )
        group_b_tl_ids = (
            set(self.groups[group_b].timeline_ids) if group_b else {actual_b}
        )

        for claim in self.cross_group_claims:
            if not claim.is_synchronous or claim.start_anchor is None:
                continue
            anchor = claim.start_anchor
            # Does this claim connect the two groups?
            a_side = (
                anchor.timeline_a_id in group_a_tl_ids
                or anchor.timeline_b_id in group_a_tl_ids
            )
            b_side = (
                anchor.timeline_a_id in group_b_tl_ids
                or anchor.timeline_b_id in group_b_tl_ids
            )
            if a_side and b_side:
                return True

        # Columnar stores answer the same question with one vectorized pass,
        # without materialising a claim.
        return any(
            claim_field.connects_groups(group_a_tl_ids, group_b_tl_ids)
            for claim_field in self.cross_group_claim_fields
        )

    # endregion

    # region Cross-Group Claims

    def create_match_claims(
        self,
        event_pairs: list[tuple[dict | str | None, str, dict | str | None, str]],
        *,
        synchronous: bool = True,
        agent: str = "user",
        agent_identifier: str = "manual",
    ) -> list[MatchClaim]:
        """Create MatchClaims from a list of event pairs.

        Convenience factory for creating multiple MatchClaims from paired
        events. Each tuple specifies two events and their timeline IDs.

        Args:
            event_pairs: List of tuples, each containing:
                ``(event_a, timeline_a_id, event_b, timeline_b_id)``.
                ``event_a``/``event_b`` are each one of:
                an event dict (must have at least a ``start`` key with a
                coordinate; an ``end`` key on both sides produces an
                interval match), the ``id`` string of an existing event on
                the paired timeline (resolved via ``Timeline.get_event()``),
                or ``None``. Exactly one of ``event_a``/``event_b`` may be
                ``None``, producing a NOMATCH claim for the other side's
                event. The forms may be mixed within a pair.
            synchronous: Whether the matches are temporally synchronous.
                Ignored for NOMATCH pairs, which are always non-synchronous.
            agent: Name of the agent creating the claims (for provenance).
            agent_identifier: The agent's stable identifier — a version string
                for a software agent or a URI for a human agent (e.g.
                ``"manual"``, ``"dynamic_time_warping"``). Stored as
                ``Agent.identifier``.

        Returns:
            List of MatchClaim objects. Also automatically adds them to
            the bundle's ``cross_group_claims``.

        Raises:
            ValueError: If event dicts are missing required keys, an event
                id string doesn't resolve to an existing event, or both
                ``event_a`` and ``event_b`` are ``None``.

        Examples:
            >>> pairs = [
            ...     ({"start": 0.0}, "score", {"start": 45.5}, "audio"),
            ...     ("note:000010", "score", "note:000042", "audio"),
            ...     ("note:000099", "score", None, "audio"),  # NOMATCH
            ... ]
            >>> claims = bundle.create_match_claims(pairs, agent="manual_alignment")
            >>> len(claims)
            3
        """
        from timetoalign.core import AgentType

        from .claims import Agent, MatchClaim, MatchMetadata

        claims = []
        for event_a, tl_a, event_b, tl_b in event_pairs:
            timeline_a = self.timelines[self._timeline_id_to_uid.get(tl_a, tl_a)]
            timeline_b = self.timelines[self._timeline_id_to_uid.get(tl_b, tl_b)]
            event_a = self._resolve_event(event_a, timeline_a, tl_a)
            event_b = self._resolve_event(event_b, timeline_b, tl_b)

            if event_a is None and event_b is None:
                raise ValueError("event_a and event_b cannot both be None")

            metadata = MatchMetadata(
                agent=Agent(
                    name=agent,
                    type=AgentType.software,
                    identifier=agent_identifier,
                ),
            )

            if event_b is None:
                claim = MatchClaim.nomatch(
                    event=event_a,
                    source_tl_id=tl_a,
                    target_tl_id=tl_b,
                    unit=timeline_a.unit,
                    metadata=metadata,
                )
            elif event_a is None:
                claim = MatchClaim.nomatch(
                    event=event_b,
                    source_tl_id=tl_b,
                    target_tl_id=tl_a,
                    unit=timeline_b.unit,
                    metadata=metadata,
                )
            else:
                # Auto-detect interval events: if both events have a non-null
                # "end" key, create an interval match with both start and end
                # anchors.  Event dicts from PyArrow may store coordinates as
                # structs ``{"value": float, ...}``; a None value means no end.
                end_key = None
                end_a = event_a.get("end")
                end_b = event_b.get("end")
                if end_a is not None and end_b is not None:
                    # Handle struct dicts: {"value": float, ...}
                    val_a = end_a["value"] if isinstance(end_a, dict) else end_a
                    val_b = end_b["value"] if isinstance(end_b, dict) else end_b
                    if val_a is not None and val_b is not None:
                        end_key = "end"
                claim = MatchClaim.from_events(
                    event_a=event_a,
                    tl_a_id=tl_a,
                    event_b=event_b,
                    tl_b_id=tl_b,
                    unit_a=timeline_a.unit,
                    unit_b=timeline_b.unit,
                    end_coord_key=end_key,
                    is_synchronous=synchronous,
                    metadata=metadata,
                )
            claims.append(claim)

        if claims:
            self.add_match_claims(claims)

        return claims

    @staticmethod
    def _resolve_event(
        event: dict | str | None, timeline: "Timeline", timeline_id: str
    ) -> dict | None:
        """Resolve an event-dict-or-id-or-None argument to an event dict.

        Args:
            event: An event dict, the ``id`` of an existing event, or
                ``None``.
            timeline: The timeline ``event`` belongs to.
            timeline_id: The timeline's id as given by the caller (for
                error messages).

        Returns:
            The event dict, or ``None`` if ``event`` was ``None``.

        Raises:
            ValueError: If ``event`` is an id string with no matching event.
        """
        if not isinstance(event, str):
            return event
        resolved = timeline.get_event(event)
        if resolved is None:
            raise ValueError(f"No event with id {event!r} on timeline {timeline_id!r}")
        return resolved

    def add_match_claims(
        self,
        claims: list[MatchClaim],
    ) -> "AlignmentBundle":
        """Add MatchClaims connecting timelines across different groups.

        MatchClaims encode coordinate correspondences between timelines in
        different groups (e.g., EEP recording notes matched to ABC score
        notes).  They enable cross-group coordinate transfer via
        ``MatchLine`` → ``WarpMap``.

        WarpMaps are built lazily on first ``transfer()`` or
        ``get_matchstamp_at()`` call, so adding claims is cheap.

        Args:
            claims: List of MatchClaim objects.  Each synchronous claim
                connects two timelines via its ``start_anchor``.

        Returns:
            self (for method chaining)
        """
        for claim in claims:
            claim.set_bundle(self)
        self.cross_group_claims.extend(claims)
        self._invalidate_warp_cache()
        return self

    def add_match_claim_field(
        self,
        claim_field: MatchClaimField,
    ) -> "AlignmentBundle":
        """Add a columnar ``MatchClaimField`` of cross-group claims.

        This is the columnar counterpart of :meth:`add_match_claims`.  The
        field is stored as-is (one PyArrow struct column) and queried
        vectorized by :meth:`get_matchstamp_at` /
        :meth:`_get_or_build_matchgraph`, which filter the struct column and
        materialise only the handful of claims at the queried coordinate.  A
        dense whole-work field (on the order of a million claims) is therefore
        never exploded into a Python list.

        It complements the per-claim list path: a bundle may hold both a
        Python-list ``cross_group_claims`` and one or more
        ``cross_group_claim_fields`` at once.

        Args:
            claim_field: A :class:`MatchClaimField` of synchronous instant
                pairwise claims.

        Returns:
            self (for method chaining)
        """
        self.cross_group_claim_fields.append(claim_field)
        self._invalidate_warp_cache()
        return self

    @property
    def n_cross_group_claims(self) -> int:
        """Total cross-group claims across BOTH claim stores.

        Sums the per-claim Python list and the row counts of every columnar
        ``MatchClaimField``.  The field contribution is a row count, so no
        claim is materialised — this is the cheap way to ask "does this
        bundle carry any alignment at all?".
        """
        return len(self.cross_group_claims) + sum(
            len(claim_field) for claim_field in self.cross_group_claim_fields
        )

    def _actual_timeline_lookup(self) -> dict[str, "Timeline"]:
        """Build an actual timeline ID to timeline metadata lookup."""
        return {
            actual_timeline_id: self.timelines[bundle_uid]
            for bundle_uid, actual_timeline_id in self._uid_to_timeline_id.items()
        }

    def _actual_id_pattern(self, id_pattern: str | None) -> str | None:
        """Translate a public UID regex into an exact actual-ID regex."""
        if id_pattern is None:
            return None

        public_pattern = re.compile(id_pattern)
        actual_ids = {
            actual_timeline_id
            for bundle_uid, actual_timeline_id in self._uid_to_timeline_id.items()
            if public_pattern.search(bundle_uid)
        }
        if not actual_ids:
            return r"(?!)"
        alternatives = "|".join(re.escape(timeline_id) for timeline_id in actual_ids)
        return rf"^(?:{alternatives})\Z"

    def get_match_claims(
        self,
        *,
        timeline_id: str | None = None,
        timeline_ids: set[str] | None = None,
        id_pattern: str | None = None,
        between: tuple[str, str] | None = None,
        synchronous_only: bool = False,
        nomatch_only: bool = False,
        include_domains: set["Domain"] | None = None,
        include_units: set["TimeUnit"] | None = None,
    ) -> list[MatchClaim]:
        """Query MatchClaims connecting timelines across groups.

        This is the primary interface for accessing alignment information.
        All parameters are optional; when none are provided, returns all
        claims.

        Filters are combined with AND logic: a claim must satisfy every
        non-None criterion. Uses the Unified Filter API.

        Both claim stores are queried: the per-claim Python list and every
        columnar ``MatchClaimField``. The columnar matches are filtered
        vectorized but then **materialised**, one ``MatchClaim`` per surviving
        row — for a dense pairwise alignment that is O(n) Python objects. Use
        :meth:`get_claim_fields` when the columnar answer suffices, or narrow
        the query first.

        Args:
            timeline_id: Return claims involving this bundle UID.
            timeline_ids: Return claims involving any of these bundle UIDs.
            id_pattern: Regex pattern matched against bundle UIDs via
                ``re.search()``. Example: ``r"^perf:"`` matches all
                performance timelines.
            between: Return claims connecting exactly these two bundle UIDs
                (order-independent).
            synchronous_only: Exclude non-synchronous (NOMATCH) claims.
            nomatch_only: Return only non-synchronous (NOMATCH) claims.
            include_domains: Only timelines in these domains.
            include_units: Only timelines with these units.

        Returns:
            Filtered list of MatchClaims.

        Examples:
            Get all synchronous claims for a performer::

                >>> claims = bundle.get_match_claims(
                ...     id_pattern=r"dlt1$", synchronous_only=True
                ... )

            Get NOMATCH claims for a specific pair::

                >>> nomatches = bundle.get_match_claims(
                ...     between=("score:clt1", "perf:dlt5"),
                ...     nomatch_only=True,
                ... )
        """
        filt = self._actual_claim_filter(
            timeline_id=timeline_id,
            timeline_ids=timeline_ids,
            id_pattern=id_pattern,
            between=between,
            synchronous_only=synchronous_only,
            nomatch_only=nomatch_only,
            include_domains=include_domains,
            include_units=include_units,
        )
        if filt is None:
            return []

        timeline_lookup = self._actual_timeline_lookup()
        claims = [
            c
            for c in self.cross_group_claims
            if filt.matches_claim(c, timelines=timeline_lookup)
        ]
        for claim_field in self._filtered_claim_fields(filt, timeline_lookup):
            claims.extend(claim_field.to_claims())
        return claims

    def get_claim_fields(
        self,
        *,
        timeline_id: str | None = None,
        timeline_ids: set[str] | None = None,
        id_pattern: str | None = None,
        between: tuple[str, str] | None = None,
        synchronous_only: bool = False,
        nomatch_only: bool = False,
        include_domains: set["Domain"] | None = None,
        include_units: set["TimeUnit"] | None = None,
    ) -> list[MatchClaimField]:
        """Query the columnar claim stores, materialising nothing.

        This is the scalable counterpart of :meth:`get_match_claims` for
        bundles whose claims live in a ``MatchClaimField`` — a dense pairwise
        alignment can hold hundreds of thousands of claims, and turning each
        one into a Python object costs orders of magnitude more than the
        columnar answer.  Every filter is applied as a vectorized PyArrow
        mask, and the result is a list of *filtered fields*, one per store
        that still has rows.

        The filter parameters are exactly those of :meth:`get_match_claims`
        and carry the same meaning.  Because a ``MatchClaimField`` holds
        synchronous claims only, ``synchronous_only`` is a no-op here and
        ``nomatch_only`` returns nothing.

        Args:
            timeline_id: Keep claims involving this bundle UID.
            timeline_ids: Keep claims involving any of these bundle UIDs.
            id_pattern: Regex matched against bundle UIDs via ``re.search()``.
            between: Keep claims connecting exactly these two bundle UIDs
                (order-independent).
            synchronous_only: No-op (every stored claim is synchronous).
            nomatch_only: Returns an empty list.
            include_domains: Only timelines in these domains.
            include_units: Only timelines with these units.

        Returns:
            Filtered ``MatchClaimField`` objects, empty stores dropped.

        Examples:
            >>> fields = bundle.get_claim_fields(timeline_id="rec-a:cpt1")
            >>> sum(len(f) for f in fields)
            66780
        """
        filt = self._actual_claim_filter(
            timeline_id=timeline_id,
            timeline_ids=timeline_ids,
            id_pattern=id_pattern,
            between=between,
            synchronous_only=synchronous_only,
            nomatch_only=nomatch_only,
            include_domains=include_domains,
            include_units=include_units,
        )
        if filt is None:
            return []
        return self._filtered_claim_fields(filt, self._actual_timeline_lookup())

    def _actual_claim_filter(
        self,
        *,
        timeline_id: str | None,
        timeline_ids: set[str] | None,
        id_pattern: str | None,
        between: tuple[str, str] | None,
        synchronous_only: bool,
        nomatch_only: bool,
        include_domains: set["Domain"] | None,
        include_units: set["TimeUnit"] | None,
    ) -> ClaimFilter | None:
        """Translate public-UID filter kwargs into an actual-ID ``ClaimFilter``.

        Claims are keyed on actual timeline IDs while the public query API
        speaks bundle UIDs, so every ID-shaped criterion is translated here
        once, for both claim stores.

        Returns:
            The translated filter, or ``None`` when a required UID is unknown
            to the bundle and no claim can possibly match.
        """
        if timeline_id is not None and timeline_id not in self._uid_to_timeline_id:
            return None
        if between is not None and any(
            bundle_uid not in self._uid_to_timeline_id for bundle_uid in between
        ):
            return None

        actual_timeline_ids = (
            {
                self._uid_to_timeline_id[bundle_uid]
                for bundle_uid in timeline_ids
                if bundle_uid in self._uid_to_timeline_id
            }
            if timeline_ids is not None
            else None
        )
        actual_between = (
            (
                self._uid_to_timeline_id[between[0]],
                self._uid_to_timeline_id[between[1]],
            )
            if between is not None
            else None
        )
        return ClaimFilter.from_kwargs(
            timeline_id=(
                self._uid_to_timeline_id[timeline_id]
                if timeline_id is not None
                else None
            ),
            timeline_ids=actual_timeline_ids,
            id_pattern=self._actual_id_pattern(id_pattern),
            between=actual_between,
            synchronous_only=synchronous_only,
            nomatch_only=nomatch_only,
            include_domains=include_domains,
            include_units=include_units,
        )

    def _filtered_claim_fields(
        self,
        filt: ClaimFilter,
        timeline_lookup: dict[str, "Timeline"],
    ) -> list[MatchClaimField]:
        """Apply an actual-ID ``ClaimFilter`` to every columnar claim store.

        The domain/unit criteria are resolved into a set of passing timeline
        IDs (the fields hold IDs, not timeline metadata); everything else maps
        straight onto ``MatchClaimField.filter``.  Stores that filter down to
        zero rows are dropped.
        """
        if not self.cross_group_claim_fields:
            return []
        within = filt.domain_unit_timeline_ids(timeline_lookup)
        filtered = (
            claim_field.filter(
                timeline_id=filt.timeline_id,
                timeline_ids=filt.timeline_ids,
                id_pattern=filt.id_pattern,
                between=filt.between,
                within=within,
                synchronous_only=filt.synchronous_only,
                nomatch_only=filt.nomatch_only,
            )
            for claim_field in self.cross_group_claim_fields
        )
        return [claim_field for claim_field in filtered if len(claim_field) > 0]

    def _get_or_build_matchgraph(
        self,
        timeline_id: str,
        coordinate: float,
    ) -> MatchGraph:
        """Get or build the MatchGraph containing (timeline_id, coordinate).

        Checks the cache first. On cache miss, finds all synchronous
        cross-group claims whose anchors touch this coordinate on this
        timeline (or any timeline connected at this coordinate via
        transitive closure), builds a MatchGraph from them, and caches
        it keyed by ALL (timeline_id, coordinate) nodes in the resulting
        graph.

        Args:
            timeline_id: A timeline in the bundle.
            coordinate: The coordinate to look up.

        Returns:
            The MatchGraph for this coordinate's connected component.

        Raises:
            ValueError: If no synchronous claims touch this node.
        """
        key = (timeline_id, coordinate)
        if key in self._matchgraph_cache:
            return self._matchgraph_cache[key]

        # Find ALL claims that touch this coordinate on this timeline.
        # Scan the per-claim Python list as before (small for the other
        # alignment loaders) ...
        relevant_claims: list[MatchClaim] = []
        for c in self.cross_group_claims:
            if not c.is_synchronous or c.start_anchor is None:
                continue
            anchor = c.start_anchor
            if (
                anchor.timeline_a_id == timeline_id
                and anchor.coordinate_a.value == coordinate
            ) or (
                anchor.timeline_b_id == timeline_id
                and anchor.coordinate_b.value == coordinate
            ):
                relevant_claims.append(c)

        # ... then query each columnar field vectorized, materialising only
        # the matched rows (never the whole field).
        for claim_field in self.cross_group_claim_fields:
            relevant_claims.extend(claim_field.at(timeline_id, coordinate).to_claims())

        if not relevant_claims:
            raise ValueError(
                f"No synchronous claims touch ({timeline_id!r}, {coordinate}) "
                f"in this bundle."
            )

        # Build graph — transitive closure connects all timelines at
        # this coordinate
        unit_map = self._get_unit_map()
        graph_units = dict(unit_map)
        graph_units.update(
            {
                self._uid_to_timeline_id.get(bundle_uid, bundle_uid): unit
                for bundle_uid, unit in unit_map.items()
            }
        )
        mg = MatchGraph(
            claims=relevant_claims,
            units=graph_units,
            axis=coordinate,
            source=self,
            source_id=timeline_id,
        )

        # Interval claims add both their start- and end-anchor edges,
        # which usually live on separate connected components. Restrict
        # to the component containing the queried node so that
        # ``get_matchstamp()`` returns a single, well-defined stamp.
        components = mg.split_components()
        target = (timeline_id, coordinate)
        for component in components:
            if target in component._graph.nodes():
                mg = component
                break

        # Cache keyed by ALL nodes in the graph
        for node in mg._graph.nodes():
            node_tl, node_coord = node
            self._matchgraph_cache[(node_tl, node_coord)] = mg

        return mg

    def get_matchstamp_at(
        self,
        coordinate: CoordinateSpec,
        timeline_id: str | None = None,
        *,
        conversion_maps: "ConversionMapsSpec" = True,
        timeline_ids: set[str] | None = None,
        id_pattern: str | None = None,
        include_domains: set["Domain"] | None = None,
        include_units: set["TimeUnit"] | None = None,
    ) -> MatchStamp:
        """Get a cross-group MatchStamp at a coordinate on a timeline.

        This is the primary interface for cross-domain coordinate transfer.
        Given a coordinate on one timeline, returns coordinates on ALL
        connected timelines across ALL groups.

        The method:
        1. Builds (or retrieves from cache) the MatchGraph for this
           coordinate's connected component.
        2. Returns the graph's MatchStamp.

        Args:
            coordinate: The query coordinate. Can be:

                - int/float/Fraction: Raw value, ``timeline_id`` required.
                - Coordinate: Value with unit, ``timeline_id`` required.
                - IdCoordinate: Value with unit AND timeline_id
                  (``timeline_id`` param optional).
            timeline_id: Bundle UID of the source timeline. Required unless
                ``coordinate`` is an ``IdCoordinate``, in which case the
                coordinate's own ``timeline_id`` is used.
            conversion_maps: C-map conversions available through unit lookup.
            timeline_ids: Only include these bundle UIDs in the result.
            id_pattern: Regex filter for bundle UIDs in the result.
            include_domains: Only these domains in the result.
            include_units: Only these units in the result.

        Returns:
            MatchStamp spanning all connected timelines.

        Raises:
            TypeError: If coordinate is not int/float/Fraction/Coordinate/
                IdCoordinate.
            ValueError: If timeline_id is None and coordinate is not an
                IdCoordinate.
            KeyError: If timeline_id is not in the bundle.

        Examples:
            >>> ms = bundle.get_matchstamp_at(10.0, "score:clt1")
            >>> ms.n_timelines
            23  # score + 22 performers
        """
        coordinate_value, timeline_id, unit = _resolve_coordinate_and_timeline(
            coordinate, timeline_id
        )
        if timeline_id is None:
            raise ValueError(
                "timeline_id is required unless coordinate is an IdCoordinate"
            )

        if (
            timeline_id not in self.timelines
            and timeline_id not in self._timeline_id_to_uid
        ):
            raise KeyError(f"Timeline '{timeline_id}' not in bundle")

        bundle_uid = self._timeline_id_to_uid.get(timeline_id, timeline_id)
        actual_timeline_id = self._uid_to_timeline_id.get(bundle_uid, timeline_id)
        coordinate = float(
            self.get_timeline(bundle_uid)
            .resolve_coordinate(Coordinate(coordinate_value, unit))
            .value
            if unit is not None
            else coordinate_value
        )

        try:
            mg = self._get_or_build_matchgraph(actual_timeline_id, coordinate)
        except ValueError as error:
            if "No synchronous claims touch" not in str(error):
                raise
            stamp = self._get_interpolated_matchstamp(
                coordinate,
                bundle_uid,
                actual_timeline_id,
                timeline_id,
                conversion_maps,
            )
        else:
            graph_stamp = mg.get_matchstamp()
            unit_map = self._get_unit_map()
            units = dict(unit_map)
            units.update(
                {
                    self._uid_to_timeline_id.get(bundle_tl_id, bundle_tl_id): unit
                    for bundle_tl_id, unit in unit_map.items()
                }
            )
            stamp = MatchStamp(
                coordinates=dict(graph_stamp.coordinates),
                anchor_edges=list(graph_stamp.anchor_edges),
                inferred_edges=list(graph_stamp.inferred_edges),
                units=units,
                axis=coordinate,
                source=self,
                source_id=timeline_id,
                is_interpolated=False,
                conversion_maps=conversion_maps,
            )

        # Apply post-hoc filtering if requested
        has_filter = (
            timeline_ids is not None
            or id_pattern is not None
            or include_domains is not None
            or include_units is not None
        )
        if has_filter:
            actual_timeline_ids = (
                {
                    self._uid_to_timeline_id[bundle_uid]
                    for bundle_uid in timeline_ids
                    if bundle_uid in self._uid_to_timeline_id
                }
                if timeline_ids is not None
                else None
            )
            filt = ClaimFilter.from_kwargs(
                timeline_ids=actual_timeline_ids,
                id_pattern=self._actual_id_pattern(id_pattern),
                include_domains=include_domains,
                include_units=include_units,
            )
            filter_timelines = self._actual_timeline_lookup()
            filtered_coords = {
                tl_id: coord
                for tl_id, coord in stamp.coordinates.items()
                if filt.matches_timeline(
                    self._uid_to_timeline_id.get(tl_id, tl_id),
                    timelines=filter_timelines,
                )
            }
            remaining = set(filtered_coords.keys())
            stamp = MatchStamp(
                coordinates=filtered_coords,
                anchor_edges=[
                    (a, b)
                    for a, b in stamp.anchor_edges
                    if a in remaining and b in remaining
                ],
                inferred_edges=[
                    (a, b)
                    for a, b in stamp.inferred_edges
                    if a in remaining and b in remaining
                ],
                units={
                    tl_id: stamp.units[tl_id]
                    for tl_id in remaining
                    if tl_id in stamp.units
                },
                axis=stamp.axis,
                source=stamp.source,
                source_id=stamp.source_id,
                is_interpolated=stamp.is_interpolated,
                conversion_maps=stamp.conversion_maps,
            )

        return stamp

    def _get_interpolated_matchstamp(
        self,
        coordinate: float,
        source_bundle_uid: str,
        source_timeline_id: str,
        query_timeline_id: str,
        conversion_maps: "ConversionMapsSpec",
    ) -> MatchStamp:
        """Resolve a cross-group stamp through group timestamps and WarpMaps."""
        source_group_id = self.timeline_to_group.get(source_bundle_uid)
        if source_group_id is None:
            coordinates = {source_bundle_uid: coordinate}
            inferred_edges: list[tuple[str, str]] = []
        else:
            source_group = self.groups[source_group_id]
            grouped_coordinates = self._get_group_timestamp(
                source_group,
                coordinate,
                source_timeline_id,
                conversion_maps=conversion_maps,
            )
            coordinates = {
                tl_id: value
                for tl_id, value in grouped_coordinates.items()
                if value is not None
            }
            inferred_edges = []

            def add_inferred_edge(timeline_a: str, timeline_b: str) -> None:
                """Record a relationship once, regardless of orientation."""
                edge = (timeline_a, timeline_b)
                reverse = (timeline_b, timeline_a)
                if (
                    timeline_a != timeline_b
                    and edge not in inferred_edges
                    and reverse not in inferred_edges
                ):
                    inferred_edges.append(edge)

            for member_uid, member_coordinate in grouped_coordinates.items():
                if member_coordinate is not None:
                    add_inferred_edge(source_bundle_uid, member_uid)

            for other_group_id, other_group in self.groups.items():
                if other_group_id == source_group_id:
                    continue
                transferred = self._transfer_to_group(
                    coordinate,
                    source_timeline_id,
                    source_group,
                    other_group,
                )
                if transferred is None:
                    continue
                target_timeline_id, target_coordinate = transferred
                target_bundle_uid = self._timeline_id_to_uid.get(
                    target_timeline_id, target_timeline_id
                )
                other_coordinates = self._get_group_timestamp(
                    other_group,
                    target_coordinate,
                    target_timeline_id,
                    conversion_maps=conversion_maps,
                )
                materialized_coordinates = {
                    tl_id: value
                    for tl_id, value in other_coordinates.items()
                    if value is not None
                }
                if target_bundle_uid in materialized_coordinates:
                    add_inferred_edge(source_bundle_uid, target_bundle_uid)
                    for member_uid in materialized_coordinates:
                        add_inferred_edge(target_bundle_uid, member_uid)
                coordinates.update(materialized_coordinates)

        unit_map = self._get_unit_map()
        return MatchStamp(
            coordinates=coordinates,
            anchor_edges=[],
            inferred_edges=inferred_edges,
            units={
                tl_id: unit_map[tl_id] for tl_id in coordinates if tl_id in unit_map
            },
            axis=coordinate,
            source=self,
            source_id=query_timeline_id,
            is_interpolated=True,
            conversion_maps=conversion_maps,
        )

    def get_matchstamps(
        self,
        claims: list[MatchClaim] | None = None,
        *,
        from_graph: bool = True,
    ) -> list[MatchStamp]:
        """Get MatchStamps for a list of MatchClaims.

        Convenience method for retrieving MatchStamps for multiple claims
        at once. Uses the bundle's caching mechanism for efficient retrieval.

        Args:
            claims: List of MatchClaims to get stamps for. If None, uses
                every cross-group claim in the bundle — the per-claim list
                and every columnar ``MatchClaimField`` (see
                :meth:`get_match_claims`, which materialises the columnar
                rows).
            from_graph: If True (default), return full MatchStamps from the
                MatchGraph (all connected timelines). If False, return
                reduced 2-timeline stamps.

        Returns:
            List of MatchStamp objects. Non-synchronous claims yield None
            entries (filtered out).

        Examples:
            >>> stamps = bundle.get_matchstamps()
            >>> len(stamps)
            100
            >>> stamps[0].n_timelines
            23
        """
        if claims is None:
            claims = self.get_match_claims()

        stamps = []
        for claim in claims:
            stamp = claim.get_matchstamp(bundle=self, from_graph=from_graph)
            if stamp is not None:
                stamps.append(stamp)

        return stamps

    def get_matchstamp_table(
        self,
        claims: list[MatchClaim] | None = None,
        *,
        timeline_filter: set[str] | None = None,
        from_graph: bool = False,
    ) -> "pa.Table":
        """Get a PyArrow table of MatchStamps for alignment queries.

        Analogous to ``get_timestamp_table()`` but for cross-group alignment.
        Fields are timeline IDs holding their coordinate values; what a *row*
        is depends on ``from_graph``:

        - ``from_graph=False`` (default) — one row per synchronous claim.  A
          pairwise claim fills exactly two cells and leaves the rest null, so
          a dense pairwise alignment produces one sparse row per claim.
        - ``from_graph=True`` — one row per connected component of the
          ``(timeline_id, coordinate)`` graph the claims induce.  The pairwise
          rows above collapse into the *cross-section* they describe: one row
          per aligned instant, every participating timeline filled.

        When ``claims`` is None both claim stores are read: the per-claim
        Python list and every columnar ``MatchClaimField``.  The columnar
        stores are read four Arrow columns at a time — no ``MatchClaim`` is
        ever materialised — which is what keeps a hundreds-of-thousands-of-rows
        alignment tabulable.

        Args:
            claims: List of MatchClaims to tabulate.  If None, uses every
                cross-group claim in the bundle (both stores).  When given,
                only those claims are tabulated.
            timeline_filter: Only include these timeline fields.
            from_graph: Collapse claims into one row per connected component
                instead of one row per claim.

        Returns:
            PyArrow Table with one field per timeline.  Non-synchronous claims
            are excluded.  Empty input yields an empty table.

        Note:
            Collapsed rows are ordered by the coordinate on the
            lexicographically smallest timeline ID present in the component,
            then by that ID — a total order, since two components can never
            share a ``(timeline_id, coordinate)`` node.  A component that
            somehow carries two coordinates for one timeline (which a
            well-formed alignment never does) keeps the smaller one.

        Examples:
            >>> table = bundle.get_matchstamp_table()
            >>> table.num_rows
            100
            >>> table.column_names
            ['score:clt1', 'perf:dlt1', 'perf:dlt2', ...]
            >>> bundle.get_matchstamp_table(from_graph=True).num_rows
            25
        """
        import pyarrow as pa

        list_claims = self.cross_group_claims if claims is None else claims
        claim_fields = [] if claims is not None else self.cross_group_claim_fields

        all_tl_ids: set[str] = set()
        rows: list[dict[str, float | None]] = []
        # Bulk (timeline_a_id, timeline_b_id, coordinate_a, coordinate_b)
        # column reads, one per columnar store, scattered without dicts.
        bulk_columns: list[tuple[list[str], list[str], list[float], list[float]]] = []

        if from_graph:
            rows = self._collapsed_claim_rows(list_claims, claim_fields)
            for row in rows:
                all_tl_ids.update(row)
        else:
            for claim in list_claims:
                if not claim.is_synchronous or claim.start_anchor is None:
                    continue

                # Get reduced stamp (2 timelines only, for efficiency)
                stamp = claim.get_matchstamp(bundle=self, from_graph=False)
                if stamp is None:
                    continue

                row = dict(stamp.coordinates)
                rows.append(row)
                all_tl_ids.update(stamp.coordinates.keys())

            bulk_columns = [
                claim_field.coordinate_pairs() for claim_field in claim_fields
            ]
            for ids_a, ids_b, _, _ in bulk_columns:
                all_tl_ids.update(ids_a)
                all_tl_ids.update(ids_b)
            all_tl_ids.discard(None)

        n_rows = len(rows) + sum(len(ids_a) for ids_a, _, _, _ in bulk_columns)
        if n_rows == 0:
            return pa.table({})

        # Apply timeline filter if provided
        if timeline_filter is not None:
            all_tl_ids = all_tl_ids & timeline_filter

        # Build table with consistent fields, scattering each claim into its
        # two cells rather than probing every field of every row.
        field_lists: dict[str, list[float | None]] = {
            tl_id: [None] * n_rows for tl_id in sorted(all_tl_ids)
        }
        for position, row in enumerate(rows):
            for tl_id, value in row.items():
                column = field_lists.get(tl_id)
                if column is not None:
                    column[position] = value

        offset = len(rows)
        for ids_a, ids_b, coordinates_a, coordinates_b in bulk_columns:
            for position in range(len(ids_a)):
                column = field_lists.get(ids_a[position])
                if column is not None:
                    column[offset + position] = coordinates_a[position]
                column = field_lists.get(ids_b[position])
                if column is not None:
                    column[offset + position] = coordinates_b[position]
            offset += len(ids_a)

        return pa.table(field_lists)

    def _collapsed_claim_rows(
        self,
        claims: list[MatchClaim],
        claim_fields: list[MatchClaimField],
    ) -> list[dict[str, float | None]]:
        """Collapse pairwise claims into one row per aligned instant.

        Each synchronous claim is an edge between the nodes
        ``(timeline_a_id, coordinate_a)`` and ``(timeline_b_id, coordinate_b)``.
        A union-find over those edges recovers the connected components, and
        each component becomes one row mapping every participating timeline to
        its coordinate.  Columnar stores contribute their edges through a bulk
        four-column read, so no ``MatchClaim`` is materialised.

        Args:
            claims: Per-claim edge source (non-synchronous claims ignored).
            claim_fields: Columnar edge sources.

        Returns:
            One row per component, ordered as documented on
            :meth:`get_matchstamp_table`.
        """
        parent: dict[tuple[str, float], tuple[str, float]] = {}

        def find(node: tuple[str, float]) -> tuple[str, float]:
            root = node
            while parent[root] != root:
                root = parent[root]
            while parent[node] != root:
                parent[node], node = root, parent[node]
            return root

        def union(node_a: tuple[str, float], node_b: tuple[str, float]) -> None:
            parent.setdefault(node_a, node_a)
            parent.setdefault(node_b, node_b)
            root_a, root_b = find(node_a), find(node_b)
            if root_a != root_b:
                parent[root_b] = root_a

        for claim in claims:
            if not claim.is_synchronous or claim.start_anchor is None:
                continue
            anchor = claim.start_anchor
            union(
                (claim.timeline_a_id, float(anchor.coordinate_a.value)),
                (claim.timeline_b_id, float(anchor.coordinate_b.value)),
            )
        for claim_field in claim_fields:
            ids_a, ids_b, coordinates_a, coordinates_b = claim_field.coordinate_pairs()
            for position in range(len(ids_a)):
                union(
                    (ids_a[position], coordinates_a[position]),
                    (ids_b[position], coordinates_b[position]),
                )

        components: dict[tuple[str, float], dict[str, float | None]] = {}
        for node in parent:
            timeline_id, coordinate = node
            row = components.setdefault(find(node), {})
            carried = row.get(timeline_id)
            if carried is None or coordinate < carried:
                row[timeline_id] = coordinate

        return sorted(components.values(), key=lambda row: (row[min(row)], min(row)))

    def _invalidate_warp_cache(self) -> None:
        """Clear the WarpMap, MatchLine, and MatchGraph caches, forcing rebuild on next access."""
        self._warp_map_cache.clear()
        self._matchline_cache.clear()
        self._matchgraph_cache.clear()
        self._cache_claims_hash = 0
        if hasattr(self, "_claim_converter_cache"):
            self._claim_converter_cache.clear()

    def _get_or_build_match_line(self, source_tl_id: str) -> MatchLine | None:
        """Get or lazily build a MatchLine for the given source timeline.

        The MatchLine is cached per ``source_tl_id`` and shared across
        all target lookups from the same source. This avoids rebuilding
        the expensive ``MatchGraph`` for every ``(source, target)`` pair.

        Group extension is deliberately NOT applied here. When groups
        contain timelines at different sampling rates (e.g. 44.1 kHz
        audio alongside 42 Hz features), within-group interpolation maps
        many distinct coordinates to the same low-resolution value,
        creating spurious edges that collapse ALL graph components into
        one.  WarpMap construction needs clean per-claim pairs, not the
        merged supergraph.  Group extension is only appropriate for
        MatchStamp display (``get_matchstamp_at``).

        Args:
            source_tl_id: Actual timeline ID (not bundle UID) of the source.

        Returns:
            MatchLine for the source, or None if construction fails.
        """
        if source_tl_id in self._matchline_cache:
            return self._matchline_cache[source_tl_id]

        # Columnar stores contribute only the rows that actually touch this
        # source. ``connecting`` is a vectorized mask, so a dense pairwise
        # field is cut to its source slice — for R recordings that is 2/R of
        # the rows — before anything is materialised, and the resulting
        # MatchLine is then cached per source.
        claims = list(self.cross_group_claims)
        for claim_field in self.cross_group_claim_fields:
            claims.extend(claim_field.connecting(source_tl_id).to_claims())

        try:
            match_line = MatchLine.from_claims(
                claims=claims,
                source_timeline_id=source_tl_id,
            )
        except Exception as e:
            self._logger.debug(
                "Failed to build MatchLine for source '%s': %s",
                source_tl_id,
                e,
            )
            self._matchline_cache[source_tl_id] = None
            return None

        self._matchline_cache[source_tl_id] = match_line
        return match_line

    def _get_or_build_warp_map(
        self, source_tl_id: str, target_tl_id: str
    ) -> WarpMap | None:
        """Get or lazily build a WarpMap for the given timeline pair.

        Builds a ``MatchLine`` from ``cross_group_claims`` with group
        extension and constructs a ``WarpMap`` via
        ``WarpMap.from_match_line()``.  Both negative results (unreachable
        pairs) and positive results are cached; the cache is invalidated
        when ``add_match_claims()`` is called.

        Args:
            source_tl_id: Actual timeline ID (not bundle UID) of the source.
            target_tl_id: Actual timeline ID (not bundle UID) of the target.

        Returns:
            WarpMap for the pair, or None if insufficient data.
        """
        if self.n_cross_group_claims == 0:
            return None

        # Check cache validity. The hash must move when EITHER store changes,
        # so it folds in the total claim count and the identity of each
        # columnar store alongside the list's own identity.
        claims_hash = id(self.cross_group_claims) + self.n_cross_group_claims
        for claim_field in self.cross_group_claim_fields:
            claims_hash += id(claim_field)
        if claims_hash != self._cache_claims_hash:
            self._warp_map_cache.clear()
            self._matchline_cache.clear()
            self._cache_claims_hash = claims_hash

        cache_key = (source_tl_id, target_tl_id)
        if cache_key in self._warp_map_cache:
            return self._warp_map_cache[cache_key]

        # Build or retrieve cached MatchLine for this source
        match_line = self._get_or_build_match_line(source_tl_id)
        if match_line is None:
            self._warp_map_cache[cache_key] = None
            return None

        # Check if target timeline is reachable
        if target_tl_id not in match_line.target_timeline_ids():
            self._warp_map_cache[cache_key] = None
            return None

        # Build WarpMap
        try:
            warp = WarpMap.from_match_line(match_line, target_tl_id)
        except AmbiguousWarpMapError:
            raise
        except ValueError as e:
            self._logger.debug(
                "Failed to build WarpMap %s -> %s: %s",
                source_tl_id,
                target_tl_id,
                e,
            )
            self._warp_map_cache[cache_key] = None
            return None

        self._warp_map_cache[cache_key] = warp
        self._logger.debug(
            "Built WarpMap %s -> %s (%d anchors)",
            source_tl_id,
            target_tl_id,
            warp.n_anchors,
        )
        return warp

    # endregion

    # region Grouped Timestamp Helpers

    def _get_group_timestamp(
        self,
        group: TimelineGroup,
        coordinate: float,
        timeline_id: str,
        *,
        conversion_maps: "ConversionMapsSpec" = True,
    ) -> dict[str, float | None]:
        """Get timestamp within a group, mapped to bundle UIDs.

        Args:
            group: The TimelineGroup.
            coordinate: Coordinate in the source timeline's native unit,
                or in a unit convertible via C-Map (see
                ``_resolve_claim_coordinate``).
            timeline_id: Actual timeline ID (not bundle UID).

        Returns:
            Dict mapping bundle UIDs to coordinates.
        """
        result: dict[str, float | None] = {}

        try:
            ts = group.get_timestamp_at(
                coordinate,
                timeline_id,
                conversion_maps=conversion_maps,
            )
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

    def _get_unit_map(self) -> dict[str, str]:
        """Build a mapping from bundle UIDs to their coordinate unit strings.

        Returns:
            Dict mapping bundle UIDs to unit strings (e.g. "samples", "quarters").
        """
        unit_map: dict[str, str] = {}
        for tl_uid, tl in self.timelines.items():
            if hasattr(tl, "unit") and tl.unit is not None:
                unit_map[tl_uid] = str(tl.unit)
        return unit_map

    def _get_claim_to_native_converter(
        self, timeline_id: str
    ) -> "ConversionMap | None":
        """Get a converter from claim-space coordinates to native units.

        MatchClaim anchors sometimes carry coordinates in a derived unit
        (e.g. EEP note onsets in seconds on an audio DPT whose native
        unit is samples).  This method detects the mismatch by comparing
        the claim coordinate range against the timeline's native range
        and each C-Map's target range.

        The result is the *inverse* of the matching C-Map, i.e. a
        function ``derived_unit → native_unit`` (e.g. seconds → samples).

        Results are cached per timeline in ``_claim_converter_cache``.

        Args:
            timeline_id: Actual timeline ID.

        Returns:
            A callable (inverse C-Map) converting claim coordinates to
            the timeline's native unit, or None if no conversion needed.
        """
        if not hasattr(self, "_claim_converter_cache"):
            self._claim_converter_cache: dict[str, Any] = {}

        _SENTINEL = object()
        cached = self._claim_converter_cache.get(timeline_id, _SENTINEL)
        if cached is not _SENTINEL:
            return cached

        bundle_uid = self._timeline_id_to_uid.get(timeline_id, timeline_id)
        tl = self.timelines.get(bundle_uid)
        if tl is None or not tl._conversion_maps:
            self._claim_converter_cache[timeline_id] = None
            return None

        # Find the max claim coordinate for this timeline
        max_claim_coord = 0.0
        for claim in self.cross_group_claims:
            anchor = claim.start_anchor
            if anchor is None:
                continue
            c = anchor.get_coordinate_for(timeline_id)
            if c is not None and c.value > max_claim_coord:
                max_claim_coord = float(c.value)
                if max_claim_coord > 1000:
                    break

        # Columnar stores answer the same question with a masked pc.max.
        for claim_field in self.cross_group_claim_fields:
            field_max = claim_field.max_coordinate(timeline_id)
            if field_max is not None and field_max > max_claim_coord:
                max_claim_coord = field_max

        if max_claim_coord == 0:
            self._claim_converter_cache[timeline_id] = None
            return None

        tl_length = float(tl.length.value)

        # If max claim coord is within 1% of the timeline's length,
        # claims are in the native unit — no conversion needed.
        if max_claim_coord > tl_length * 0.01:
            self._claim_converter_cache[timeline_id] = None
            return None

        # Claims are much smaller than the native range — find which
        # C-Map's target range covers the claim range.
        for cmap in tl._conversion_maps.values():
            try:
                converted_length = float(cmap(tl_length))
                if max_claim_coord <= converted_length * 1.1:
                    inv = cmap.inverse()
                    self._claim_converter_cache[timeline_id] = inv
                    return inv
            except Exception:
                continue

        self._claim_converter_cache[timeline_id] = None
        return None

    def _transfer_to_group(
        self,
        coordinate: float,
        source_tl_id: str,
        source_group: TimelineGroup,
        target_group: TimelineGroup,
    ) -> tuple[str, float] | None:
        """Transfer a coordinate from one group to another via WarpMap.

        Searches for a WarpMap connecting any timeline in the source
        group to any timeline in the target group.  Tries direct maps
        first, then indirect (convert within source group, then warp).

        The WarpMap may return a coordinate in the claim's unit rather
        than the target timeline's native unit (e.g. seconds instead of
        samples).  ``_get_claim_to_native_converter`` detects this and
        provides an inverse C-Map to correct the output.

        Args:
            coordinate: Source coordinate.
            source_tl_id: Source timeline ID (actual, not bundle UID).
            source_group: Source group.
            target_group: Target group.

        Returns:
            ``(target_timeline_id, transferred_coordinate)`` or ``None``.
        """
        # Try direct: source_tl_id -> any timeline in target group
        for target_tl_id in target_group.timeline_ids:
            warp = self._get_or_build_warp_map(source_tl_id, target_tl_id)
            if warp is not None:
                try:
                    transferred = float(warp(coordinate))
                    conv = self._get_claim_to_native_converter(target_tl_id)
                    if conv is not None:
                        transferred = float(conv(transferred))
                    return (target_tl_id, transferred)
                except Exception:
                    continue

        # Try indirect: convert within source group, then warp
        for src_other_tl_id in source_group.timeline_ids:
            if src_other_tl_id == source_tl_id:
                continue
            # Convert within source group
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
                warp = self._get_or_build_warp_map(src_other_tl_id, target_tl_id)
                if warp is not None:
                    try:
                        transferred = float(warp(float(intermediate)))
                        conv = self._get_claim_to_native_converter(target_tl_id)
                        if conv is not None:
                            transferred = float(conv(transferred))
                        return (target_tl_id, transferred)
                    except Exception:
                        continue

        return None

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
        return str(self.diagram())

    # endregion

    # region Display

    def diagram(
        self,
        width: int = 80,
        show_children: bool = True,
        max_children: int = 6,
        max_standalone: int = 6,
        unicode: bool = True,
    ) -> "Diagram":
        """Generate ASCII diagram for this bundle.

        Args:
            width: Total width of the diagram in characters.
            show_children: Whether to expand child timelines.
            max_children: Maximum children per timeline.
            max_standalone: Maximum standalone timelines to display
                before truncating with an ellipsis.
            unicode: Use Unicode characters (True) or ASCII fallback (False).

        Returns:
            Diagram object (displays as ASCII in terminal, rich HTML in Jupyter).

        Examples:
            >>> print(bundle.diagram())
            AlignmentBundle[thoresen_alignment]

              TimelineGroup[dgt1_group] (2 timelines, 2 timestamps)
              ┌──────────────────────────────────────────────────────┐
              │ DiscreteGraphicalTimeline[dgt1:1] (11 events)        │
              │ 0 ∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶∶ 4835 pixels    │
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
            max_standalone=max_standalone,
            unicode=unicode,
        )

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the ASCII diagram in a monospace pre block so it
        renders correctly in notebook output cells.
        """
        return self.diagram()._repr_html_()

    # endregion


# endregion
