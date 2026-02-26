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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
        id: Unique identifier for this claim.

    Examples:
        >>> # Synchronous instant match via factory
        >>> claim = MatchClaim.from_events(
        ...     event_a={"start": 100.0},
        ...     tl_a_id="score:1",
        ...     event_b={"start": 45.5},
        ...     tl_b_id="recording:1",
        ... )

        >>> # Non-synchronous claim (no anchors)
        >>> claim = MatchClaim.nomatch(
        ...     event={"start": 100.0},
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
    id: str = field(default="")

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
            ValueError: If ``from_graph=True`` but ``bundle`` is None.

        Examples:
            Full stamp (default -- from graph, all groups)::

                >>> stamp = claim.get_matchstamp(bundle=bundle)
                >>> stamp.n_timelines
                23  # score + 22 performers at this coordinate

            Reduced stamp (two timelines only)::

                >>> stamp = claim.get_matchstamp(bundle=bundle, from_graph=False)
                >>> stamp.n_timelines
                2   # just the two timelines in this claim
        """
        if not self.is_synchronous or self.start_anchor is None:
            return None

        if from_graph:
            if bundle is None:
                raise ValueError(
                    "bundle is required for from_graph=True. Pass the "
                    "AlignmentBundle containing this claim."
                )
            # Delegate to the bundle's cached MatchGraph mechanism
            return bundle.get_matchstamp_at(
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
            tl_a_id: Timeline A's ID.
            event_b: Event dict from timeline B (must contain ``coord_key``).
            tl_b_id: Timeline B's ID.
            coord_key: Key for start coordinate in event dicts.
            end_coord_key: Key for end coordinate (creates interval match).
            is_synchronous: Whether events are temporally synchronous.
            metadata: Provenance information.

        Returns:
            A synchronous MatchClaim with 1 or 2 anchors.
        """
        start_anchor = AlignmentAnchor(
            timeline_a_id=tl_a_id,
            coordinate_a=float(event_a[coord_key]),
            timeline_b_id=tl_b_id,
            coordinate_b=float(event_b[coord_key]),
        )

        end_anchor = None
        if end_coord_key is not None:
            end_anchor = AlignmentAnchor(
                timeline_a_id=tl_a_id,
                coordinate_a=float(event_a[end_coord_key]),
                timeline_b_id=tl_b_id,
                coordinate_b=float(event_b[end_coord_key]),
            )

        return cls(
            timeline_a_id=tl_a_id,
            timeline_b_id=tl_b_id,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            is_synchronous=is_synchronous,
            metadata=metadata,
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
            event: Event dict from the source timeline.
            source_tl_id: Source timeline's ID.
            target_tl_id: Target timeline's ID.
            target_coord: Projected coordinate on the target timeline.
            coord_key: Key for start coordinate in event dict.
            target_end_coord: Projected end coordinate (creates interval match).
            end_coord_key: Key for end coordinate in event dict.
            metadata: Provenance information.

        Returns:
            A synchronous MatchClaim with 1 or 2 anchors.
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

        return cls(
            timeline_a_id=source_tl_id,
            timeline_b_id=target_tl_id,
            start_anchor=start_anchor,
            end_anchor=end_anchor,
            is_synchronous=True,
            metadata=metadata,
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
            event: Event dict from the source timeline.
            source_tl_id: Source timeline's ID.
            target_tl_id: Target timeline's ID.
            metadata: Provenance information.

        Returns:
            A non-synchronous MatchClaim with no anchors.
        """
        return cls(
            timeline_a_id=source_tl_id,
            timeline_b_id=target_tl_id,
            start_anchor=None,
            end_anchor=None,
            is_synchronous=False,
            is_explicit=True,
            metadata=metadata,
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
            id=data.get("id", ""),
        )

    def __repr__(self) -> str:
        match_type = "interval" if self.is_interval else "instant"
        flags = []
        if not self.is_explicit:
            flags.append("inferred")
        if not self.is_synchronous:
            flags.append("non-synchronous")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        if not self.is_synchronous:
            return (
                f"MatchClaim({self.timeline_a_id} <-> "
                f"{self.timeline_b_id}{flag_str})"
            )

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

        Shows claim type, timelines with coordinates, and metadata.

        Examples:
            >>> print(claim)
            MatchClaim (synchronous, interval)
              Timeline A:  score:clt1  [0.0 -- 0.5]
              Timeline B:  perf:dlt1   [0 -- 261]
              Metadata:    agent=partitura, certainty=1.0
        """

        def _fmt(v: float) -> str:
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            return f"{v:g}"

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

        # Timeline A
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                lines.append(
                    f"  Timeline A:  {self.timeline_a_id}  "
                    f"[{_fmt(self.start_anchor.coordinate_a)} -- "
                    f"{_fmt(self.end_anchor.coordinate_a)}]"
                )
                lines.append(
                    f"  Timeline B:  {self.timeline_b_id}  "
                    f"[{_fmt(self.start_anchor.coordinate_b)} -- "
                    f"{_fmt(self.end_anchor.coordinate_b)}]"
                )
            else:
                lines.append(
                    f"  Timeline A:  {self.timeline_a_id}  "
                    f"@{_fmt(self.start_anchor.coordinate_a)}"
                )
                lines.append(
                    f"  Timeline B:  {self.timeline_b_id}  "
                    f"@{_fmt(self.start_anchor.coordinate_b)}"
                )
        else:
            lines.append(f"  Timeline A:  {self.timeline_a_id}")
            lines.append(f"  Timeline B:  {self.timeline_b_id}")

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
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            return f"{v:g}"

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

        rows = []

        # Timeline rows
        if self.is_synchronous and self.start_anchor is not None:
            if self.is_interval and self.end_anchor is not None:
                coord_a = (
                    f"[{_fmt(self.start_anchor.coordinate_a)} &ndash; "
                    f"{_fmt(self.end_anchor.coordinate_a)}]"
                )
                coord_b = (
                    f"[{_fmt(self.start_anchor.coordinate_b)} &ndash; "
                    f"{_fmt(self.end_anchor.coordinate_b)}]"
                )
            else:
                coord_a = f"@{_fmt(self.start_anchor.coordinate_a)}"
                coord_b = f"@{_fmt(self.start_anchor.coordinate_b)}"

            rows.append(
                f"<tr><td>Timeline A</td>"
                f"<td><strong>{html_mod.escape(self.timeline_a_id)}</strong></td>"
                f"<td>{coord_a}</td></tr>"
            )
            rows.append(
                f"<tr><td>Timeline B</td>"
                f"<td><strong>{html_mod.escape(self.timeline_b_id)}</strong></td>"
                f"<td>{coord_b}</td></tr>"
            )
        else:
            rows.append(
                f"<tr><td>Timeline A</td>"
                f"<td>{html_mod.escape(self.timeline_a_id)}</td>"
                f"<td></td></tr>"
            )
            rows.append(
                f"<tr><td>Timeline B</td>"
                f"<td>{html_mod.escape(self.timeline_b_id)}</td>"
                f"<td></td></tr>"
            )

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
