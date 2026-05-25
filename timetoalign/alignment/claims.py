"""AlignmentAnchor and MatchClaim classes.

This module implements the atomic and low-level alignment claims from the
TTA manuscript's multi-level alignment hierarchy:

- AlignmentAnchor: Neutral coordinate pair (pure value object)
- MatchClaim: Alignment claim between two timelines (with provenance)
- MatchMetadata: Provenance information for matches

The hierarchy is:
    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine

Design:
    AlignmentAnchor is a pure coordinate pair with no claim semantics.
    Only synchronous MatchClaims produce AlignmentAnchors.
    MatchClaim always knows its two timelines via top-level fields.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from timetoalign.core import IdGenerator

module_logger = logging.getLogger(__name__)

# Module-level ID generators
_anchor_id_generator = IdGenerator(scope="anchor")
_claim_id_generator = IdGenerator(scope="claim")


def _reset_anchor_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _anchor_id_generator
    _anchor_id_generator = IdGenerator(scope="anchor")


def _reset_claim_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _claim_id_generator
    _claim_id_generator = IdGenerator(scope="claim")


# region MatchMetadata


@dataclass(frozen=True)
class MatchMetadata:
    """Provenance information for a match claim.

    Following the TTA manuscript's requirement that matches must include
    the agent/author, decision criteria, and certainty level.

    Attributes:
        agent: Who or what created this match (user ID, algorithm name).
        decision_criteria: How the match was determined (e.g., "manual",
            "dynamic_time_warping", "segment_correspondence").
        certainty: Confidence level in [0, 1]. 1.0 = certain.
        created_at: When the match was created.
        notes: Additional human-readable notes.
        algorithm_params: Parameters used by the matching algorithm.

    Examples:
        >>> meta = MatchMetadata(
        ...     agent="analyst_jh",
        ...     decision_criteria="manual_segmentation",
        ...     certainty=1.0,
        ... )

        >>> meta = MatchMetadata(
        ...     agent="dtw_v2",
        ...     decision_criteria="dynamic_time_warping",
        ...     certainty=0.85,
        ...     algorithm_params={"window_size": 100},
        ... )
    """

    agent: str
    decision_criteria: str
    certainty: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    notes: str | None = None
    algorithm_params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate certainty is in valid range."""
        if not 0.0 <= self.certainty <= 1.0:
            raise ValueError(f"Certainty must be in [0, 1], got {self.certainty}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "agent": self.agent,
            "decision_criteria": self.decision_criteria,
            "certainty": self.certainty,
            "created_at": self.created_at.isoformat(),
            "notes": self.notes,
            "algorithm_params": self.algorithm_params,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchMetadata":
        """Deserialize from dictionary."""
        return cls(
            agent=data["agent"],
            decision_criteria=data["decision_criteria"],
            certainty=data.get("certainty", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]),
            notes=data.get("notes"),
            algorithm_params=data.get("algorithm_params"),
        )


# endregion


# region AlignmentAnchor


@dataclass(frozen=True)
class AlignmentAnchor:
    """A coordinate pair associating one coordinate on timeline A with one
    coordinate on timeline B.

    A neutral record with no claim semantics. AlignmentAnchors are value
    objects: two anchors with the same coordinates and timeline IDs are
    equivalent regardless of how they were created.

    Only synchronous `MatchClaim` instances produce AlignmentAnchors.
    Non-synchronous claims (conceptual matches, NOMATCH) have no anchors.

    Attributes:
        timeline_a_id: First timeline's unique identifier.
        coordinate_a: Coordinate in first timeline.
        timeline_b_id: Second timeline's unique identifier.
        coordinate_b: Coordinate in second timeline.

    Examples:
        >>> anchor = AlignmentAnchor(
        ...     timeline_a_id="score:1",
        ...     coordinate_a=100.0,
        ...     timeline_b_id="recording:1",
        ...     coordinate_b=45.5,
        ... )
        >>> anchor.get_coordinate_for("score:1")
        100.0
    """

    timeline_a_id: str
    coordinate_a: float
    timeline_b_id: str
    coordinate_b: float

    @property
    def timelines(self) -> tuple[str, str]:
        """Return tuple of timeline IDs."""
        return (self.timeline_a_id, self.timeline_b_id)

    @property
    def coordinates(self) -> tuple[float, float]:
        """Return tuple of coordinates."""
        return (self.coordinate_a, self.coordinate_b)

    def get_coordinate_for(self, timeline_id: str) -> float | None:
        """Get the coordinate for a specific timeline.

        Args:
            timeline_id: The timeline to get coordinate for.

        Returns:
            The coordinate, or None if timeline not in this anchor.
        """
        if timeline_id == self.timeline_a_id:
            return self.coordinate_a
        if timeline_id == self.timeline_b_id:
            return self.coordinate_b
        return None

    def connects(self, timeline_id: str) -> bool:
        """Check if this anchor connects to a specific timeline.

        Args:
            timeline_id: The timeline to check.

        Returns:
            True if the anchor involves this timeline.
        """
        return timeline_id in (self.timeline_a_id, self.timeline_b_id)

    def connects_both(self, timeline_a_id: str, timeline_b_id: str) -> bool:
        """Check if this anchor connects two specific timelines.

        Args:
            timeline_a_id: First timeline.
            timeline_b_id: Second timeline.

        Returns:
            True if the anchor connects exactly these two timelines.
        """
        return {self.timeline_a_id, self.timeline_b_id} == {
            timeline_a_id,
            timeline_b_id,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "timeline_a_id": self.timeline_a_id,
            "coordinate_a": self.coordinate_a,
            "timeline_b_id": self.timeline_b_id,
            "coordinate_b": self.coordinate_b,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlignmentAnchor":
        """Deserialize from dictionary."""
        return cls(
            timeline_a_id=data["timeline_a_id"],
            coordinate_a=data["coordinate_a"],
            timeline_b_id=data["timeline_b_id"],
            coordinate_b=data["coordinate_b"],
        )

    def __repr__(self) -> str:
        return (
            f"AlignmentAnchor({self.timeline_a_id}@{self.coordinate_a:.2f} <-> "
            f"{self.timeline_b_id}@{self.coordinate_b:.2f})"
        )


# endregion


# region MatchClaim


@dataclass(frozen=True)
class MatchClaim:
    """A claim that two events or coordinates on different timelines correspond.

    A MatchClaim always knows which two timelines it connects via top-level
    ``timeline_a_id`` and ``timeline_b_id`` fields. Anchors are only present
    for synchronous claims.

    Four cases:
        (a) ``from_events``: Two timed things on different timelines correspond.
        (b) ``from_projection``: An event is projected onto a timeline with no
            matching event.
        (c) ``nomatch``: An event has no equivalent on the other timeline.
        (d) ``implicit``: Implicit claim generated by MatchGraph group extension.

    Attributes:
        timeline_a_id: First timeline's unique identifier.
        timeline_b_id: Second timeline's unique identifier.
        start_anchor: AlignmentAnchor for event starts (None for non-synchronous).
        end_anchor: AlignmentAnchor for event ends (None for instants or
            non-synchronous claims).
        is_synchronous: True if temporally synchronous matches.
        is_explicit: True if directly claimed, False if inferred.
        metadata: Provenance information (agent, criteria, certainty).
        source_claim_id: For implicit claims, the ID of the claim that
            generated this one.
        event_a_id: ID of the event on timeline A (if known).
        event_a_name: Name/label of the event on timeline A (if known).
        event_b_id: ID of the event on timeline B (if known).
        event_b_name: Name/label of the event on timeline B (if known).
        source_coordinate: Unmatched source-side coordinate for a NOMATCH
            claim. None for synchronous claims, whose coordinate is held by
            the anchor instead.
        id: Unique identifier for this claim.

    Examples:
        >>> # Synchronous instant match via factory
        >>> claim = MatchClaim.from_events(
        ...     event_a={"id": "e001", "name": "Note C4", "start": 100.0},
        ...     tl_a_id="score:1",
        ...     event_b={"id": "e042", "name": "Note C4", "start": 45.5},
        ...     tl_b_id="recording:1",
        ... )
        >>> claim.event_a_id
        'e001'
        >>> claim.event_a_name
        'Note C4'

        >>> # Non-synchronous claim (no anchors)
        >>> claim = MatchClaim.nomatch(
        ...     event={"id": "orphan", "start": 100.0},
        ...     source_tl_id="score:1",
        ...     target_tl_id="recording:1",
        ... )
        >>> claim.start_anchor is None
        True
    """

    timeline_a_id: str
    timeline_b_id: str
    start_anchor: AlignmentAnchor | None = None
    end_anchor: AlignmentAnchor | None = None
    is_synchronous: bool = True
    is_explicit: bool = True
    metadata: MatchMetadata | None = None
    source_claim_id: str | None = None
    event_a_id: str | None = None
    event_a_name: str | None = None
    event_b_id: str | None = None
    event_b_name: str | None = None
    source_coordinate: float | None = None
    id: str = field(default="")
    _bundle: Any = field(default=None, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        """Validate and auto-generate ID if not provided."""
        # Auto-generate ID
        if not self.id:
            object.__setattr__(
                self,
                "id",
                _claim_id_generator.create(type_hint="MatchClaim"),
            )

        # Validate anchor presence based on synchrony
        if self.is_synchronous:
            if self.start_anchor is None:
                raise ValueError(
                    "Synchronous MatchClaims require a start_anchor. "
                    "Use is_synchronous=False for conceptual/NOMATCH claims."
                )
            # If both anchors exist, they must connect the same pair
            if self.end_anchor is not None:
                start_tls = {
                    self.start_anchor.timeline_a_id,
                    self.start_anchor.timeline_b_id,
                }
                end_tls = {
                    self.end_anchor.timeline_a_id,
                    self.end_anchor.timeline_b_id,
                }
                if start_tls != end_tls:
                    raise ValueError(
                        f"Start and end anchors must connect same timelines. "
                        f"Start connects {start_tls}, end connects {end_tls}"
                    )
            # Anchors must connect the claim's timelines
            anchor_tls = {
                self.start_anchor.timeline_a_id,
                self.start_anchor.timeline_b_id,
            }
            claim_tls = {self.timeline_a_id, self.timeline_b_id}
            if anchor_tls != claim_tls:
                raise ValueError(
                    f"Anchor timelines {anchor_tls} must match claim "
                    f"timelines {claim_tls}"
                )
        else:
            if self.start_anchor is not None or self.end_anchor is not None:
                raise ValueError(
                    "Non-synchronous MatchClaims must not have anchors. "
                    "Set start_anchor=None and end_anchor=None, or use "
                    "is_synchronous=True."
                )

    @property
    def is_interval(self) -> bool:
        """Whether this is an interval match (has end anchor)."""
        return self.end_anchor is not None

    @property
    def bundle(self) -> Any:
        """The AlignmentBundle this claim belongs to, if set."""
        return self._bundle

    def set_bundle(self, bundle: Any) -> None:
        """Associate this claim with an AlignmentBundle.

        This is called automatically when claims are added to a bundle.
        Once set, ``get_matchstamp(from_graph=True)`` can be called
        without passing the bundle explicitly.

        Args:
            bundle: The AlignmentBundle containing this claim.
        """
        object.__setattr__(self, "_bundle", bundle)

    @property
    def timelines(self) -> tuple[str, str]:
        """Return tuple of timeline IDs."""
        return (self.timeline_a_id, self.timeline_b_id)

    def get_coordinates_for(self, timeline_id: str) -> tuple[float, float | None]:
        """Get start and end coordinates for a specific timeline.

        Args:
            timeline_id: The timeline to get coordinates for.

        Returns:
            Tuple of (start_coord, end_coord). end_coord is None for instants.

        Raises:
            ValueError: If timeline is not in this claim or claim has no anchors.
        """
        if self.start_anchor is None:
            raise ValueError(
                f"Claim has no anchors (non-synchronous). "
                f"Cannot get coordinates for '{timeline_id}'."
            )

        start = self.start_anchor.get_coordinate_for(timeline_id)
        if start is None:
            raise ValueError(f"Timeline '{timeline_id}' not in this claim")

        end = None
        if self.end_anchor is not None:
            end = self.end_anchor.get_coordinate_for(timeline_id)

        return (start, end)

    def connects(self, timeline_id: str) -> bool:
        """Check if this claim connects to a specific timeline.

        Args:
            timeline_id: The timeline to check.

        Returns:
            True if the claim involves this timeline.
        """
        return timeline_id in (self.timeline_a_id, self.timeline_b_id)

    def connects_both(self, timeline_a_id: str, timeline_b_id: str) -> bool:
        """Check if this claim connects two specific timelines.

        Args:
            timeline_a_id: First timeline.
            timeline_b_id: Second timeline.

        Returns:
            True if the claim connects exactly these two timelines.
        """
        return {self.timeline_a_id, self.timeline_b_id} == {
            timeline_a_id,
            timeline_b_id,
        }

    @property
    def anchors(self) -> list[AlignmentAnchor]:
        """Get all anchors in this claim (0, 1, or 2).

        Non-synchronous claims return an empty list.
        """
        if self.start_anchor is None:
            return []
        if self.end_anchor is not None:
            return [self.start_anchor, self.end_anchor]
        return [self.start_anchor]

    def get_matchstamp(
        self,
        *,
        bundle: Any | None = None,
        from_graph: bool = True,
        conversion_maps: bool = True,
    ) -> Any | None:
        """Return a MatchStamp for this claim's start anchor.

        With ``from_graph=True`` (the default), the method builds or retrieves
        the full MatchGraph for this claim's coordinate from the bundle's
        cache and returns the FULL MatchStamp combining timestamps from ALL
        groups connected at this coordinate.

        With ``from_graph=False``, constructs a **reduced** MatchStamp from
        only the two timelines in this claim (no graph construction needed).

        Args:
            bundle: The ``AlignmentBundle`` containing this claim. Required
                for ``from_graph=True``. Provides group info and the
                MatchGraph cache.
            from_graph: If True (default), build/retrieve the full
                MatchGraph and return the FULL MatchStamp across ALL
                connected groups. If False, return a reduced 2-timeline
                MatchStamp.
            conversion_maps: Include C-map conversions (reserved for
                future use).

        Returns:
            MatchStamp with coordinates, or None if this claim is
            non-synchronous (NOMATCH).

        Raises:
            ValueError: If ``from_graph=True`` but no bundle is available
                (neither passed nor set via ``set_bundle()``).

        Examples:
            Full stamp (default -- from graph, all groups)::

                >>> stamp = claim.get_matchstamp()  # uses claim's bundle
                >>> stamp.n_timelines
                23  # score + 22 performers at this coordinate

            Reduced stamp (two timelines only)::

                >>> stamp = claim.get_matchstamp(from_graph=False)
                >>> stamp.n_timelines
                2   # just the two timelines in this claim
        """
        if not self.is_synchronous or self.start_anchor is None:
            return None

        if from_graph:
            # Use provided bundle, or fall back to the claim's bundle
            effective_bundle = bundle if bundle is not None else self._bundle
            if effective_bundle is None:
                raise ValueError(
                    "bundle is required for from_graph=True. Either pass the "
                    "AlignmentBundle or ensure this claim was added to a bundle."
                )
            # Delegate to the bundle's cached MatchGraph mechanism
            return effective_bundle.get_matchstamp_at(
                self.start_anchor.coordinate_a,
                self.timeline_a_id,
            )
        else:
            # Reduced stamp: just the two coordinates from this claim
            from timetoalign.alignment.graph import MatchStamp

            coords = {
                self.timeline_a_id: self.start_anchor.coordinate_a,
                self.timeline_b_id: self.start_anchor.coordinate_b,
            }
            return MatchStamp(
                coordinates=coords,
                anchor_edges=[(self.timeline_a_id, self.timeline_b_id)],
                inferred_edges=[],
            )

    # region Factory Methods

    @classmethod
    def from_events(
        cls,
        event_a: dict[str, Any],
        tl_a_id: str,
        event_b: dict[str, Any],
        tl_b_id: str,
        *,
        coord_key: str = "start",
        end_coord_key: str | None = None,
        is_synchronous: bool = True,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaim":
        """Case (a): Two timed things on different timelines correspond.

        Args:
            event_a: Event dict from timeline A (must contain ``coord_key``).
                May also contain ``id`` and ``name`` fields.
            tl_a_id: Timeline A's ID.
            event_b: Event dict from timeline B (must contain ``coord_key``).
                May also contain ``id`` and ``name`` fields.
            tl_b_id: Timeline B's ID.
            coord_key: Key for start coordinate in event dicts.
            end_coord_key: Key for end coordinate (creates interval match).
            is_synchronous: Whether events are temporally synchronous.
            metadata: Provenance information.

        Returns:
            A synchronous MatchClaim with 1 or 2 anchors and event info.
        """

        def _extract_coord(event: dict, key: str) -> float:
            """Extract coordinate value from event dict.

            Handles both raw float values and structured coordinate dicts
            with a 'value' key.
            """
            coord = event[key]
            if isinstance(coord, dict):
                return float(coord["value"])
            return float(coord)

        def _extract_str(event: dict, key: str) -> str | None:
            """Extract string value from event dict, returning None if absent."""
            val = event.get(key)
            return str(val) if val is not None else None

        start_anchor = AlignmentAnchor(
            timeline_a_id=tl_a_id,
            coordinate_a=_extract_coord(event_a, coord_key),
            timeline_b_id=tl_b_id,
            coordinate_b=_extract_coord(event_b, coord_key),
        )

        end_anchor = None
        if end_coord_key is not None:
            end_anchor = AlignmentAnchor(
                timeline_a_id=tl_a_id,
                coordinate_a=_extract_coord(event_a, end_coord_key),
                timeline_b_id=tl_b_id,
                coordinate_b=_extract_coord(event_b, end_coord_key),
            )

        return cls(
            timeline_a_id=tl_a_id,
            timeline_b_id=tl_b_id,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            is_synchronous=is_synchronous,
            metadata=metadata,
            event_a_id=_extract_str(event_a, "id"),
            event_a_name=_extract_str(event_a, "name"),
            event_b_id=_extract_str(event_b, "id"),
            event_b_name=_extract_str(event_b, "name"),
        )

    @classmethod
    def from_projection(
        cls,
        event: dict[str, Any],
        source_tl_id: str,
        target_tl_id: str,
        target_coord: float,
        *,
        coord_key: str = "start",
        target_end_coord: float | None = None,
        end_coord_key: str | None = None,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaim":
        """Case (b): An event is projected onto a timeline with no matching event.

        The source event has a coordinate; the target coordinate is specified
        explicitly (e.g., computed by interpolation or DTW).

        Args:
            event: Event dict from the source timeline. May contain ``id``
                and ``name`` fields.
            source_tl_id: Source timeline's ID.
            target_tl_id: Target timeline's ID.
            target_coord: Projected coordinate on the target timeline.
            coord_key: Key for start coordinate in event dict.
            target_end_coord: Projected end coordinate (creates interval match).
            end_coord_key: Key for end coordinate in event dict.
            metadata: Provenance information.

        Returns:
            A synchronous MatchClaim with 1 or 2 anchors and source event info.
        """
        start_anchor = AlignmentAnchor(
            timeline_a_id=source_tl_id,
            coordinate_a=float(event[coord_key]),
            timeline_b_id=target_tl_id,
            coordinate_b=target_coord,
        )

        end_anchor = None
        if target_end_coord is not None and end_coord_key is not None:
            end_anchor = AlignmentAnchor(
                timeline_a_id=source_tl_id,
                coordinate_a=float(event[end_coord_key]),
                timeline_b_id=target_tl_id,
                coordinate_b=target_end_coord,
            )

        # Extract event info from source event (target has no event)
        event_a_id = str(event["id"]) if event.get("id") is not None else None
        event_a_name = str(event["name"]) if event.get("name") is not None else None

        return cls(
            timeline_a_id=source_tl_id,
            timeline_b_id=target_tl_id,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            is_synchronous=True,
            metadata=metadata,
            event_a_id=event_a_id,
            event_a_name=event_a_name,
            event_b_id=None,
            event_b_name=None,
        )

    @classmethod
    def nomatch(
        cls,
        event: dict[str, Any],
        source_tl_id: str,
        target_tl_id: str,
        *,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaim":
        """Case (c): An event has no equivalent on the other timeline.

        Creates a non-synchronous claim with no anchors (NOMATCH sentinel).

        Args:
            event: Event dict from the source timeline. May contain ``id``
                and ``name`` fields.
            source_tl_id: Source timeline's ID.
            target_tl_id: Target timeline's ID.
            metadata: Provenance information.

        Returns:
            A non-synchronous MatchClaim with no anchors but source event
            info. The source-side coordinate (``event["start"]``) is
            preserved as ``source_coordinate`` for display.
        """
        # Extract event info from source event
        event_a_id = str(event["id"]) if event.get("id") is not None else None
        event_a_name = str(event["name"]) if event.get("name") is not None else None
        source_coordinate = (
            float(event["start"]) if event.get("start") is not None else None
        )

        return cls(
            timeline_a_id=source_tl_id,
            timeline_b_id=target_tl_id,
            start_anchor=None,
            end_anchor=None,
            is_synchronous=False,
            is_explicit=True,
            metadata=metadata,
            event_a_id=event_a_id,
            event_a_name=event_a_name,
            event_b_id=None,
            event_b_name=None,
            source_coordinate=source_coordinate,
        )

    @classmethod
    def implicit(
        cls,
        tl_a_id: str,
        coord_a: float,
        tl_b_id: str,
        coord_b: float,
        *,
        source_claim: "MatchClaim | None" = None,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaim":
        """Case (d): Implicit claim generated by MatchGraph group extension.

        Args:
            tl_a_id: First timeline's ID.
            coord_a: Coordinate on timeline A.
            tl_b_id: Second timeline's ID.
            coord_b: Coordinate on timeline B.
            source_claim: The claim that generated this one.
            metadata: Provenance information.

        Returns:
            A synchronous, non-explicit MatchClaim with one anchor.
        """
        return cls(
            timeline_a_id=tl_a_id,
            timeline_b_id=tl_b_id,
            start_anchor=AlignmentAnchor(
                timeline_a_id=tl_a_id,
                coordinate_a=coord_a,
                timeline_b_id=tl_b_id,
                coordinate_b=coord_b,
            ),
            is_synchronous=True,
            is_explicit=False,
            source_claim_id=source_claim.id if source_claim else None,
            metadata=metadata,
        )

    # endregion

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        data: dict[str, Any] = {
            "id": self.id,
            "timeline_a_id": self.timeline_a_id,
            "timeline_b_id": self.timeline_b_id,
            "start_anchor": self.start_anchor.to_dict() if self.start_anchor else None,
            "end_anchor": self.end_anchor.to_dict() if self.end_anchor else None,
            "is_explicit": self.is_explicit,
            "is_synchronous": self.is_synchronous,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "event_a_id": self.event_a_id,
            "event_a_name": self.event_a_name,
            "event_b_id": self.event_b_id,
            "event_b_name": self.event_b_name,
            "source_coordinate": self.source_coordinate,
        }
        if self.source_claim_id is not None:
            data["source_claim_id"] = self.source_claim_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchClaim":
        """Deserialize from dictionary."""
        start_anchor = (
            AlignmentAnchor.from_dict(data["start_anchor"])
            if data.get("start_anchor")
            else None
        )
        end_anchor = (
            AlignmentAnchor.from_dict(data["end_anchor"])
            if data.get("end_anchor")
            else None
        )

        # Derive timeline IDs: prefer top-level fields, fall back to anchor
        tl_a = data.get("timeline_a_id")
        tl_b = data.get("timeline_b_id")
        if tl_a is None and start_anchor is not None:
            tl_a = start_anchor.timeline_a_id
        if tl_b is None and start_anchor is not None:
            tl_b = start_anchor.timeline_b_id
        if tl_a is None or tl_b is None:
            raise ValueError(
                "Cannot deserialize MatchClaim: missing timeline IDs and no anchor."
            )

        return cls(
            timeline_a_id=tl_a,
            timeline_b_id=tl_b,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            is_explicit=data.get("is_explicit", True),
            is_synchronous=data.get("is_synchronous", True),
            metadata=(
                MatchMetadata.from_dict(data["metadata"])
                if data.get("metadata")
                else None
            ),
            source_claim_id=data.get("source_claim_id"),
            event_a_id=data.get("event_a_id"),
            event_a_name=data.get("event_a_name"),
            event_b_id=data.get("event_b_id"),
            event_b_name=data.get("event_b_name"),
            source_coordinate=data.get("source_coordinate"),
            id=data.get("id", ""),
        )

    def __repr__(self) -> str:
        match_type = "interval" if self.is_interval else "instant"
        flags = []
        if not self.is_explicit:
            flags.append("inferred")
        if not self.is_synchronous:
            flags.append("NOMATCH")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        if not self.is_synchronous:
            if self.source_coordinate is not None:
                timeline_a = f"{self.timeline_a_id}@{self.source_coordinate:.1f}"
            else:
                timeline_a = self.timeline_a_id
            return f"MatchClaim({timeline_a} <-> {self.timeline_b_id}{flag_str})"

        if self.is_interval:
            start_a, end_a = self.get_coordinates_for(self.timeline_a_id)
            start_b, end_b = self.get_coordinates_for(self.timeline_b_id)
            return (
                f"MatchClaim({match_type}: "
                f"{self.timeline_a_id}[{start_a:.1f}-{end_a:.1f}] <-> "
                f"{self.timeline_b_id}[{start_b:.1f}-{end_b:.1f}]{flag_str})"
            )
        else:
            return (
                f"MatchClaim({match_type}: "
                f"{self.timeline_a_id}@{self.start_anchor.coordinate_a:.1f} <-> "
                f"{self.timeline_b_id}@{self.start_anchor.coordinate_b:.1f}{flag_str})"
            )

    def __str__(self) -> str:
        """Readable multi-line display showing claim details.

        Shows claim type, timelines with coordinates, events, and metadata.

        Examples:
            >>> print(claim)
            MatchClaim (synchronous, interval)
              Timeline A:  score:clt1  [0.0 -- 0.5]
              Event A:     e001 "Intro"
              Timeline B:  perf:dlt1   [0 -- 261]
              Event B:     e042 "Intro"
              Metadata:    agent=partitura, certainty=1.0
        """

        def _fmt(v: float) -> str:
            """Format coordinate without scientific notation."""
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            elif abs(v) >= 1e6:
                return str(int(round(v)))
            elif abs(v) >= 1:
                return f"{v:.6f}".rstrip("0").rstrip(".")
            else:
                return f"{v:.6f}".rstrip("0").rstrip(".")

        def _event_str(ev_id: str | None, ev_name: str | None) -> str | None:
            """Format event info as 'id "name"' or just id/name if one is missing."""
            if ev_id and ev_name:
                return f'{ev_id} "{ev_name}"'
            elif ev_id:
                return ev_id
            elif ev_name:
                return f'"{ev_name}"'
            return None

        # Header
        if not self.is_synchronous:
            header = "MatchClaim (NOMATCH)"
        elif self.is_interval:
            header = "MatchClaim (synchronous, interval)"
        else:
            header = "MatchClaim (synchronous, instant)"

        if not self.is_explicit:
            header += " [inferred]"

        lines = [header]

        # Timeline A and Event A
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                lines.append(
                    f"  Timeline A:  {self.timeline_a_id}  "
                    f"[{_fmt(self.start_anchor.coordinate_a)} -- "
                    f"{_fmt(self.end_anchor.coordinate_a)}]"
                )
            else:
                lines.append(
                    f"  Timeline A:  {self.timeline_a_id}  "
                    f"@{_fmt(self.start_anchor.coordinate_a)}"
                )
        else:
            lines.append(f"  Timeline A:  {self.timeline_a_id}")

        # Event A (always show if present)
        event_a_str = _event_str(self.event_a_id, self.event_a_name)
        if event_a_str:
            lines.append(f"  Event A:     {event_a_str}")

        # Timeline B and Event B
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                lines.append(
                    f"  Timeline B:  {self.timeline_b_id}  "
                    f"[{_fmt(self.start_anchor.coordinate_b)} -- "
                    f"{_fmt(self.end_anchor.coordinate_b)}]"
                )
            else:
                lines.append(
                    f"  Timeline B:  {self.timeline_b_id}  "
                    f"@{_fmt(self.start_anchor.coordinate_b)}"
                )
        else:
            lines.append(f"  Timeline B:  {self.timeline_b_id}")

        # Event B (always show if present)
        event_b_str = _event_str(self.event_b_id, self.event_b_name)
        if event_b_str:
            lines.append(f"  Event B:     {event_b_str}")

        # Metadata
        if self.metadata is not None:
            meta_parts = [f"agent={self.metadata.agent}"]
            if self.metadata.certainty < 1.0:
                meta_parts.append(f"certainty={self.metadata.certainty}")
            if self.metadata.decision_criteria:
                meta_parts.append(f"criteria={self.metadata.decision_criteria}")
            lines.append(f"  Metadata:    {', '.join(meta_parts)}")

        if self.source_claim_id is not None:
            lines.append(f"  Source:      {self.source_claim_id}")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """Return HTML representation for Jupyter notebooks.

        Displays the MatchClaim as a compact HTML block with claim details.
        """
        import html as html_mod

        def _fmt(v: float) -> str:
            """Format coordinate without scientific notation."""
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            elif abs(v) >= 1e6:
                return str(int(round(v)))
            elif abs(v) >= 1:
                return f"{v:.6f}".rstrip("0").rstrip(".")
            else:
                return f"{v:.6f}".rstrip("0").rstrip(".")

        # Header badge
        if not self.is_synchronous:
            badge_bg = "#ffcdd2"
            badge_text = "NOMATCH"
        elif self.is_interval:
            badge_bg = "#e3f2fd"
            badge_text = "synchronous, interval"
        else:
            badge_bg = "#e8f5e9"
            badge_text = "synchronous, instant"

        if not self.is_explicit:
            badge_text += " [inferred]"

        badge = (
            f"<span style='background: {badge_bg}; padding: 0 4px; "
            f"border-radius: 3px; font-size: 0.8em;'>{badge_text}</span>"
        )

        def _event_html(
            ev_id: str | None, ev_name: str | None, label: str
        ) -> str | None:
            """Format event info as an HTML row, or None if no event info."""
            if ev_id and ev_name:
                return (
                    f"<tr style='color: #555; font-size: 0.9em;'><td>{label}</td>"
                    f"<td>{html_mod.escape(ev_id)}</td>"
                    f'<td>"{html_mod.escape(ev_name)}"</td></tr>'
                )
            elif ev_id:
                return (
                    f"<tr style='color: #555; font-size: 0.9em;'><td>{label}</td>"
                    f"<td colspan='2'>{html_mod.escape(ev_id)}</td></tr>"
                )
            elif ev_name:
                return (
                    f"<tr style='color: #555; font-size: 0.9em;'><td>{label}</td>"
                    f"<td colspan='2'>\"{html_mod.escape(ev_name)}\"</td></tr>"
                )
            return None

        rows = []

        # Timeline A row
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                coord_a = (
                    f"[{_fmt(self.start_anchor.coordinate_a)} &ndash; "
                    f"{_fmt(self.end_anchor.coordinate_a)}]"
                )
            else:
                coord_a = f"@{_fmt(self.start_anchor.coordinate_a)}"

            rows.append(
                f"<tr><td>Timeline A</td>"
                f"<td><strong>{html_mod.escape(self.timeline_a_id)}</strong></td>"
                f"<td>{coord_a}</td></tr>"
            )
        else:
            rows.append(
                f"<tr><td>Timeline A</td>"
                f"<td>{html_mod.escape(self.timeline_a_id)}</td>"
                f"<td></td></tr>"
            )

        # Event A row (if present)
        event_a_row = _event_html(self.event_a_id, self.event_a_name, "Event A")
        if event_a_row:
            rows.append(event_a_row)

        # Timeline B row
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                coord_b = (
                    f"[{_fmt(self.start_anchor.coordinate_b)} &ndash; "
                    f"{_fmt(self.end_anchor.coordinate_b)}]"
                )
            else:
                coord_b = f"@{_fmt(self.start_anchor.coordinate_b)}"

            rows.append(
                f"<tr><td>Timeline B</td>"
                f"<td><strong>{html_mod.escape(self.timeline_b_id)}</strong></td>"
                f"<td>{coord_b}</td></tr>"
            )
        else:
            rows.append(
                f"<tr><td>Timeline B</td>"
                f"<td>{html_mod.escape(self.timeline_b_id)}</td>"
                f"<td></td></tr>"
            )

        # Event B row (if present)
        event_b_row = _event_html(self.event_b_id, self.event_b_name, "Event B")
        if event_b_row:
            rows.append(event_b_row)

        # Metadata row
        if self.metadata is not None:
            meta_parts = [
                html_mod.escape(f"agent={self.metadata.agent}"),
            ]
            if self.metadata.certainty < 1.0:
                meta_parts.append(f"certainty={self.metadata.certainty}")
            rows.append(
                f"<tr style='color: #666;'><td>Metadata</td>"
                f"<td colspan='2'>{', '.join(meta_parts)}</td></tr>"
            )

        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>MatchClaim</strong> {badge}"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table></div>"
        )


# endregion


# region MatchClaimField


class MatchClaimField:
    """Columnar store for a set of synchronous-instant pairwise match claims.

    A ``MatchClaimField`` wraps a single :class:`pyarrow.Table` so that a very
    large set of pairwise alignment claims (millions of rows) can be held as
    four columns instead of one frozen :class:`MatchClaim` object per claim.
    Individual :class:`MatchClaim` instances are materialised lazily, only when
    a row is indexed or iterated.

    This is **not** a ``SemanticField`` / ``DataField`` subclass: a
    :class:`MatchClaim` is a frozen dataclass (not a pydantic scalar) and the
    store spans several columns, so the pydantic-to-Arrow translation machinery
    does not apply. It is a purpose-built columnar store that follows the
    paired-Scalar/Field file-layout convention only in spirit -- it lives in
    the same module as :class:`MatchClaim`, immediately after it.

    **Scope (v1): synchronous instant pairwise claims only.** Every row
    represents a claim where ``is_synchronous is True``, ``start_anchor`` is
    present, and ``end_anchor`` is ``None`` (an instant). NOMATCH claims
    (non-synchronous) and interval claims (with an end anchor) remain
    dataclass-only and are **out of scope** for this store;
    :meth:`from_claims` raises :class:`ValueError` when handed one.

    The backing table has exactly four columns:

    * ``timeline_a_id`` -- dictionary-encoded string. Only a handful of
      distinct timeline ids appear across up to ~1.15M rows, so the dictionary
      encoding keeps the store compact.
    * ``timeline_b_id`` -- dictionary-encoded string (same type).
    * ``coordinate_a`` -- ``float64``.
    * ``coordinate_b`` -- ``float64``.

    Shared provenance is held once at field level as a single
    :class:`MatchMetadata` (or ``None``); it is **not** a per-row column. Every
    claim a ``MatchClaimField`` materialises carries this same metadata.

    Attributes:
        table: The backing :class:`pyarrow.Table` (read-only property).
        metadata: Shared :class:`MatchMetadata` (or ``None``) applied to every
            materialised claim.

    Examples:
        >>> meta = MatchMetadata(agent="dtw", decision_criteria="warp")
        >>> field = MatchClaimField.from_columns(
        ...     timeline_a_ids=["A", "A", "B"],
        ...     timeline_b_ids=["B", "C", "C"],
        ...     coordinate_a=[0.0, 0.0, 1.0],
        ...     coordinate_b=[10.0, 20.0, 21.0],
        ...     metadata=meta,
        ... )
        >>> len(field)
        3
        >>> field[0].timeline_a_id, field[0].timeline_b_id
        ('A', 'B')
    """

    # The exact column layout every backing table must carry.
    _ID_TYPE: pa.DataType = pa.dictionary(pa.int32(), pa.string())
    _COLUMN_NAMES: tuple[str, ...] = (
        "timeline_a_id",
        "timeline_b_id",
        "coordinate_a",
        "coordinate_b",
    )

    @classmethod
    def from_columns(
        cls,
        timeline_a_ids: Sequence[str] | pa.Array | pa.ChunkedArray,
        timeline_b_ids: Sequence[str] | pa.Array | pa.ChunkedArray,
        coordinate_a: Sequence[float] | pa.Array | pa.ChunkedArray,
        coordinate_b: Sequence[float] | pa.Array | pa.ChunkedArray,
        *,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaimField":
        """Build a field directly from parallel columns (the vectorized path).

        This is the constructor a bulk producer (e.g. an alignment loader)
        uses. It builds the four columns straight into a
        :class:`pyarrow.Table` and **never** materialises a single
        :class:`MatchClaim` Python object, so it scales to millions of rows.

        Args:
            timeline_a_ids: Timeline-A ids, one per claim. Any sequence or
                PyArrow array; dictionary-encoded into the store.
            timeline_b_ids: Timeline-B ids, one per claim.
            coordinate_a: Coordinate on timeline A, one per claim. Cast to
                ``float64``.
            coordinate_b: Coordinate on timeline B, one per claim.
            metadata: Shared provenance for every claim in the field.

        Returns:
            A new :class:`MatchClaimField`.

        Raises:
            ValueError: If the four inputs do not all have the same length.
        """
        tl_a = cls._encode_id_array(timeline_a_ids)
        tl_b = cls._encode_id_array(timeline_b_ids)
        coord_a = cls._encode_coordinate_array(coordinate_a)
        coord_b = cls._encode_coordinate_array(coordinate_b)

        lengths = {len(tl_a), len(tl_b), len(coord_a), len(coord_b)}
        if len(lengths) != 1:
            raise ValueError(
                "from_columns requires four equal-length columns; got lengths "
                f"timeline_a_id={len(tl_a)}, timeline_b_id={len(tl_b)}, "
                f"coordinate_a={len(coord_a)}, coordinate_b={len(coord_b)}."
            )

        table = pa.table(
            [tl_a, tl_b, coord_a, coord_b],
            names=list(cls._COLUMN_NAMES),
        )
        return cls(table, metadata=metadata)

    @classmethod
    def from_claims(
        cls,
        claims: list[MatchClaim],
        *,
        metadata: MatchMetadata | None = None,
    ) -> "MatchClaimField":
        """Build a field from existing :class:`MatchClaim` objects.

        Every claim must be a synchronous instant (``is_synchronous is True``,
        ``start_anchor`` present, ``end_anchor is None``) per the v1 scope.

        If ``metadata`` is ``None`` and all claims share one identical
        :class:`MatchMetadata` (by equality), that metadata is adopted as the
        field-level provenance; otherwise the field's metadata stays ``None``
        (no per-row metadata is ever stored).

        Args:
            claims: The claims to store. Coordinates are pulled from each
                claim's ``start_anchor``.
            metadata: Explicit field-level provenance. When provided it
                overrides any per-claim metadata inference.

        Returns:
            A new :class:`MatchClaimField`.

        Raises:
            ValueError: If any claim is non-synchronous (NOMATCH), lacks a
                start anchor, or is an interval (carries an end anchor).
        """
        for index, claim in enumerate(claims):
            if not claim.is_synchronous or claim.start_anchor is None:
                raise ValueError(
                    f"MatchClaimField holds synchronous instant claims only; "
                    f"claim at index {index} is non-synchronous (NOMATCH) and "
                    f"is out of scope."
                )
            if claim.end_anchor is not None:
                raise ValueError(
                    f"MatchClaimField holds synchronous instant claims only; "
                    f"claim at index {index} is an interval claim (has an "
                    f"end anchor) and is out of scope."
                )

        if metadata is None:
            metadata = cls._common_metadata(claims)

        timeline_a_ids = [claim.timeline_a_id for claim in claims]
        timeline_b_ids = [claim.timeline_b_id for claim in claims]
        coordinate_a = [claim.start_anchor.coordinate_a for claim in claims]
        coordinate_b = [claim.start_anchor.coordinate_b for claim in claims]

        return cls.from_columns(
            timeline_a_ids,
            timeline_b_ids,
            coordinate_a,
            coordinate_b,
            metadata=metadata,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchClaimField":
        """Deserialize a field from a plain dictionary.

        Inverse of :meth:`to_dict`.

        Args:
            data: A mapping with the four column lists and an optional
                ``metadata`` dict.

        Returns:
            A new :class:`MatchClaimField`.
        """
        metadata_dict = data.get("metadata")
        metadata = (
            MatchMetadata.from_dict(metadata_dict)
            if metadata_dict is not None
            else None
        )
        return cls.from_columns(
            data["timeline_a_id"],
            data["timeline_b_id"],
            data["coordinate_a"],
            data["coordinate_b"],
            metadata=metadata,
        )

    @staticmethod
    def _encode_id_array(
        values: Sequence[str] | pa.Array | pa.ChunkedArray,
    ) -> pa.Array | pa.ChunkedArray:
        """Coerce a sequence/array of ids into the dictionary-encoded id type."""
        if isinstance(values, (pa.Array, pa.ChunkedArray)):
            arr: pa.Array | pa.ChunkedArray = values
        else:
            arr = pa.array(values, type=pa.string())
        if pa.types.is_dictionary(arr.type):
            return pc.cast(arr, MatchClaimField._ID_TYPE)
        return pc.cast(arr, MatchClaimField._ID_TYPE)

    @staticmethod
    def _encode_coordinate_array(
        values: Sequence[float] | pa.Array | pa.ChunkedArray,
    ) -> pa.Array | pa.ChunkedArray:
        """Coerce a sequence/array of coordinates into ``float64``."""
        if isinstance(values, (pa.Array, pa.ChunkedArray)):
            return pc.cast(values, pa.float64())
        return pa.array(values, type=pa.float64())

    @staticmethod
    def _common_metadata(claims: list[MatchClaim]) -> MatchMetadata | None:
        """Return the shared metadata if all claims agree, else ``None``."""
        if not claims:
            return None
        first = claims[0].metadata
        if first is None:
            return None
        for claim in claims[1:]:
            if claim.metadata != first:
                return None
        return first

    def __init__(
        self,
        table: pa.Table,
        *,
        metadata: MatchMetadata | None = None,
    ) -> None:
        """Wrap a backing table of synchronous-instant pairwise claims.

        Args:
            table: A :class:`pyarrow.Table` carrying exactly the four expected
                columns in order: ``timeline_a_id`` and ``timeline_b_id``
                (dictionary-encoded strings), ``coordinate_a`` and
                ``coordinate_b`` (``float64``).
            metadata: Shared provenance applied to every materialised claim.

        Raises:
            ValueError: If the table's columns do not match the expected
                names or types.
        """
        if tuple(table.column_names) != self._COLUMN_NAMES:
            raise ValueError(
                f"MatchClaimField table must have columns {list(self._COLUMN_NAMES)}; "
                f"got {table.column_names}."
            )
        schema = table.schema
        for id_column in ("timeline_a_id", "timeline_b_id"):
            if not pa.types.is_dictionary(schema.field(id_column).type):
                raise ValueError(
                    f"MatchClaimField column {id_column!r} must be dictionary-encoded; "
                    f"got {schema.field(id_column).type}."
                )
        for coord_column in ("coordinate_a", "coordinate_b"):
            if schema.field(coord_column).type != pa.float64():
                raise ValueError(
                    f"MatchClaimField column {coord_column!r} must be float64; "
                    f"got {schema.field(coord_column).type}."
                )
        self._table = table
        self._metadata = metadata

    def __len__(self) -> int:
        """Number of claims (rows) in the field."""
        return self._table.num_rows

    def __getitem__(self, i: int) -> MatchClaim:
        """Materialise the claim at row ``i`` as a :class:`MatchClaim`.

        Supports negative indexing.

        Args:
            i: Zero-based row index (negative counts from the end).

        Returns:
            A synchronous instant :class:`MatchClaim` carrying the field's
            shared metadata.

        Raises:
            IndexError: If ``i`` is out of range.
        """
        n = self._table.num_rows
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(f"MatchClaimField index {i} out of range (len={n})")

        timeline_a_id = self._table.column("timeline_a_id")[i].as_py()
        timeline_b_id = self._table.column("timeline_b_id")[i].as_py()
        coordinate_a = self._table.column("coordinate_a")[i].as_py()
        coordinate_b = self._table.column("coordinate_b")[i].as_py()

        anchor = AlignmentAnchor(
            timeline_a_id=timeline_a_id,
            coordinate_a=coordinate_a,
            timeline_b_id=timeline_b_id,
            coordinate_b=coordinate_b,
        )
        return MatchClaim(
            timeline_a_id=timeline_a_id,
            timeline_b_id=timeline_b_id,
            start_anchor=anchor,
            is_synchronous=True,
            metadata=self._metadata,
        )

    def __iter__(self) -> Iterator[MatchClaim]:
        """Yield each claim, materialised lazily one row at a time."""
        for i in range(self._table.num_rows):
            yield self[i]

    def __repr__(self) -> str:
        return (
            f"MatchClaimField(claims={self._table.num_rows}, "
            f"timelines={len(self.timeline_ids)})"
        )

    @property
    def table(self) -> pa.Table:
        """The backing :class:`pyarrow.Table`."""
        return self._table

    @property
    def metadata(self) -> MatchMetadata | None:
        """Shared provenance applied to every materialised claim."""
        return self._metadata

    @property
    def timeline_ids(self) -> set[str]:
        """The distinct timeline ids appearing in either id column.

        Reads the dictionary-encoded columns' dictionaries directly rather
        than scanning every row.
        """
        ids: set[str] = set()
        for column_name in ("timeline_a_id", "timeline_b_id"):
            column = self._table.column(column_name)
            for chunk in column.chunks:
                ids.update(chunk.dictionary.to_pylist())
        return ids

    def connecting(self, timeline_id: str) -> "MatchClaimField":
        """Return the claims that involve ``timeline_id`` on either side.

        The filter is a vectorized boolean mask over the id columns; no claim
        is materialised. The shared metadata carries over.

        Args:
            timeline_id: The exact timeline id to match against either column.

        Returns:
            A new :class:`MatchClaimField` holding only the matching rows.
        """
        mask = self._involves_mask(timeline_id)
        return MatchClaimField(self._table.filter(mask), metadata=self._metadata)

    def filter(
        self,
        *,
        timeline_id: str | None = None,
        timeline_ids: set[str] | None = None,
    ) -> "MatchClaimField":
        """Return a filtered view following the unified-filter spirit.

        Both arguments are vectorized; no claim is materialised. The shared
        metadata carries over.

        Args:
            timeline_id: Keep rows involving this exact id on either side
                (equivalent to :meth:`connecting`).
            timeline_ids: Keep rows involving **any** id in this set on either
                side.

        Returns:
            A new :class:`MatchClaimField`. When both arguments are ``None``,
            a copy over the full table is returned. When both are given the
            two conditions are combined with logical AND.
        """
        mask: pa.Array | None = None
        if timeline_id is not None:
            mask = self._involves_mask(timeline_id)
        if timeline_ids is not None:
            any_mask = self._involves_any_mask(timeline_ids)
            mask = any_mask if mask is None else pc.and_(mask, any_mask)
        if mask is None:
            return MatchClaimField(self._table, metadata=self._metadata)
        return MatchClaimField(self._table.filter(mask), metadata=self._metadata)

    def to_claims(self) -> list[MatchClaim]:
        """Materialise every row into a list of :class:`MatchClaim` objects.

        This is ``O(n)`` and defeats the columnar purpose for large sets; it
        is provided for convenience and round-tripping, not for hot paths.

        Returns:
            A list of synchronous instant claims, one per row.
        """
        return [self[i] for i in range(self._table.num_rows)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (inverse of :meth:`from_dict`).

        The four columns are emitted as plain Python lists; the metadata is
        emitted via :meth:`MatchMetadata.to_dict` (or ``None``).

        Returns:
            A round-trippable mapping.
        """
        return {
            "timeline_a_id": self._table.column("timeline_a_id").to_pylist(),
            "timeline_b_id": self._table.column("timeline_b_id").to_pylist(),
            "coordinate_a": self._table.column("coordinate_a").to_pylist(),
            "coordinate_b": self._table.column("coordinate_b").to_pylist(),
            "metadata": (
                self._metadata.to_dict() if self._metadata is not None else None
            ),
        }

    def _involves_mask(self, timeline_id: str) -> pa.Array:
        """Boolean mask: rows where either id column equals ``timeline_id``."""
        return pc.or_(
            pc.equal(self._table.column("timeline_a_id"), timeline_id),
            pc.equal(self._table.column("timeline_b_id"), timeline_id),
        )

    def _involves_any_mask(self, timeline_ids: set[str]) -> pa.Array:
        """Boolean mask: rows involving any id in ``timeline_ids``."""
        wanted = pa.array(sorted(timeline_ids), type=pa.string())
        return pc.or_(
            pc.is_in(self._table.column("timeline_a_id"), value_set=wanted),
            pc.is_in(self._table.column("timeline_b_id"), value_set=wanted),
        )

    def _repr_html_(self) -> str:
        """Compact Jupyter summary: claim count, timeline count, head sample."""
        import html as html_mod

        n = self._table.num_rows
        n_timelines = len(self.timeline_ids)
        head = min(n, 5)
        rows = []
        for i in range(head):
            claim = self[i]
            anchor = claim.start_anchor
            rows.append(
                f"<tr><td>{i}</td>"
                f"<td>{html_mod.escape(claim.timeline_a_id)}</td>"
                f"<td>{anchor.coordinate_a:g}</td>"
                f"<td>{html_mod.escape(claim.timeline_b_id)}</td>"
                f"<td>{anchor.coordinate_b:g}</td></tr>"
            )
        if n > head:
            rows.append("<tr><td colspan='5'>&hellip;</td></tr>")
        header = (
            "<tr><th>#</th><th>timeline A</th><th>coord A</th>"
            "<th>timeline B</th><th>coord B</th></tr>"
        )
        return (
            f"<div style='font-family: monospace;'>"
            f"<strong>MatchClaimField</strong> "
            f"<span style='color: #555;'>claims={n}, timelines={n_timelines}</span>"
            f"<table style='border-collapse: collapse; margin-top: 4px;'>"
            f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody>"
            f"</table></div>"
        )


# endregion
