"""AlignmentAnchor and MatchClaim classes.

This module implements the atomic and low-level alignment claims from the
TTA manuscript's multi-level alignment hierarchy:

- AlignmentAnchor: Atomic coordinate pair (the fundamental unit)
- MatchClaim: 1-2 anchors between two events (instant or interval match)
- MatchMetadata: Provenance information for matches

The hierarchy is:
    AlignmentAnchor -> MatchClaim -> MatchGraph -> MatchStamp -> MatchLine
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
    """A claim that two coordinates from different timelines are equivalent.

    This is the atomic unit of alignment. An anchor always connects exactly
    two timelines (and therefore potentially two groups).

    Anchors can be:
    - Explicit: Directly claimed by user/algorithm
    - Inferred: Extended via C-Map or Group membership
    - Synchronous: Temporally equivalent (same musical moment)
    - Conceptual: Related but not temporally equivalent (e.g., same structural role)

    Attributes:
        timeline_a_id: First timeline's unique identifier.
        coordinate_a: Coordinate in first timeline.
        timeline_b_id: Second timeline's unique identifier.
        coordinate_b: Coordinate in second timeline.
        is_explicit: True if user/algorithm explicitly created this anchor.
            False if inferred via C-Map or Group extension.
        is_synchronous: True if coordinates are temporally synchronous.
            False if only conceptually related (structural correspondence).
        id: Unique identifier for this anchor.

    Examples:
        >>> # Explicit synchronous anchor (same moment in time)
        >>> anchor = AlignmentAnchor(
        ...     timeline_a_id="score:1",
        ...     coordinate_a=100.0,
        ...     timeline_b_id="recording:1",
        ...     coordinate_b=45.5,
        ...     is_explicit=True,
        ...     is_synchronous=True,
        ... )

        >>> # Conceptual anchor (same structural position, different time)
        >>> anchor = AlignmentAnchor(
        ...     timeline_a_id="analysis_2009",
        ...     coordinate_a=866.0,
        ...     timeline_b_id="analysis_2010",
        ...     coordinate_b=975.0,
        ...     is_synchronous=False,  # Different performances
        ... )
    """

    timeline_a_id: str
    coordinate_a: float
    timeline_b_id: str
    coordinate_b: float
    is_explicit: bool = True
    is_synchronous: bool = True
    id: str = field(default="")

    def __post_init__(self) -> None:
        """Auto-generate ID if not provided."""
        if not self.id:
            # Use object.__setattr__ since dataclass is frozen
            object.__setattr__(
                self,
                "id",
                _anchor_id_generator.create(type_hint="AlignmentAnchor"),
            )

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

    def with_explicit(self, is_explicit: bool) -> "AlignmentAnchor":
        """Return a copy with different explicit flag.

        Args:
            is_explicit: New explicit flag value.

        Returns:
            New AlignmentAnchor with updated flag.
        """
        return AlignmentAnchor(
            timeline_a_id=self.timeline_a_id,
            coordinate_a=self.coordinate_a,
            timeline_b_id=self.timeline_b_id,
            coordinate_b=self.coordinate_b,
            is_explicit=is_explicit,
            is_synchronous=self.is_synchronous,
            id=self.id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "id": self.id,
            "timeline_a_id": self.timeline_a_id,
            "coordinate_a": self.coordinate_a,
            "timeline_b_id": self.timeline_b_id,
            "coordinate_b": self.coordinate_b,
            "is_explicit": self.is_explicit,
            "is_synchronous": self.is_synchronous,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlignmentAnchor":
        """Deserialize from dictionary."""
        return cls(
            timeline_a_id=data["timeline_a_id"],
            coordinate_a=data["coordinate_a"],
            timeline_b_id=data["timeline_b_id"],
            coordinate_b=data["coordinate_b"],
            is_explicit=data.get("is_explicit", True),
            is_synchronous=data.get("is_synchronous", True),
            id=data.get("id", ""),
        )

    def __repr__(self) -> str:
        flags = []
        if not self.is_explicit:
            flags.append("inferred")
        if not self.is_synchronous:
            flags.append("conceptual")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        return (
            f"AlignmentAnchor({self.timeline_a_id}@{self.coordinate_a:.2f} <-> "
            f"{self.timeline_b_id}@{self.coordinate_b:.2f}{flag_str})"
        )


# endregion


# region MatchClaim


@dataclass(frozen=True)
class MatchClaim:
    """A claim that two events are matched.

    A MatchClaim represents a match between two events, consisting of:
    - 1 AlignmentAnchor for instant events (single time point)
    - 2 AlignmentAnchors for interval events (start and end)

    The MatchClaim is the fundamental unit for building MatchGraphs and
    ultimately creating alignment relationships between timelines.

    Attributes:
        start_anchor: AlignmentAnchor for event starts.
        end_anchor: AlignmentAnchor for event ends (None for instant matches).
        is_explicit: True if directly claimed, False if inferred.
        is_synchronous: True if temporally synchronous matches.
        metadata: Provenance information (agent, criteria, certainty).
        id: Unique identifier for this claim.

    Examples:
        >>> # Instant match (single anchor)
        >>> claim = MatchClaim(
        ...     start_anchor=AlignmentAnchor(
        ...         timeline_a_id="score:1",
        ...         coordinate_a=0.0,
        ...         timeline_b_id="recording:1",
        ...         coordinate_b=0.0,
        ...     ),
        ...     metadata=MatchMetadata(
        ...         agent="manual",
        ...         decision_criteria="beat_alignment",
        ...     ),
        ... )
        >>> claim.is_interval
        False

        >>> # Interval match (two anchors: start and end)
        >>> claim = MatchClaim(
        ...     start_anchor=AlignmentAnchor(
        ...         timeline_a_id="dgt1",
        ...         coordinate_a=0.0,
        ...         timeline_b_id="dgt2",
        ...         coordinate_b=0.0,
        ...     ),
        ...     end_anchor=AlignmentAnchor(
        ...         timeline_a_id="dgt1",
        ...         coordinate_a=975.0,
        ...         timeline_b_id="dgt2",
        ...         coordinate_b=866.0,
        ...     ),
        ...     metadata=MatchMetadata(
        ...         agent="analyst",
        ...         decision_criteria="segment_correspondence",
        ...     ),
        ... )
        >>> claim.is_interval
        True
    """

    start_anchor: AlignmentAnchor
    end_anchor: AlignmentAnchor | None = None
    is_explicit: bool = True
    is_synchronous: bool = True
    metadata: MatchMetadata | None = None
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

        # Validate that start and end anchors connect same timelines
        if self.end_anchor is not None:
            start_tls = {
                self.start_anchor.timeline_a_id,
                self.start_anchor.timeline_b_id,
            }
            end_tls = {self.end_anchor.timeline_a_id, self.end_anchor.timeline_b_id}
            if start_tls != end_tls:
                raise ValueError(
                    f"Start and end anchors must connect same timelines. "
                    f"Start connects {start_tls}, end connects {end_tls}"
                )

    @property
    def is_interval(self) -> bool:
        """Whether this is an interval match (has end anchor)."""
        return self.end_anchor is not None

    @property
    def timeline_a_id(self) -> str:
        """ID of the first timeline in this match."""
        return self.start_anchor.timeline_a_id

    @property
    def timeline_b_id(self) -> str:
        """ID of the second timeline in this match."""
        return self.start_anchor.timeline_b_id

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
            ValueError: If timeline is not in this claim.
        """
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
        return self.start_anchor.connects(timeline_id)

    def connects_both(self, timeline_a_id: str, timeline_b_id: str) -> bool:
        """Check if this claim connects two specific timelines.

        Args:
            timeline_a_id: First timeline.
            timeline_b_id: Second timeline.

        Returns:
            True if the claim connects exactly these two timelines.
        """
        return self.start_anchor.connects_both(timeline_a_id, timeline_b_id)

    @property
    def anchors(self) -> list[AlignmentAnchor]:
        """Get all anchors in this claim (1 or 2)."""
        if self.end_anchor is not None:
            return [self.start_anchor, self.end_anchor]
        return [self.start_anchor]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        data = {
            "id": self.id,
            "start_anchor": self.start_anchor.to_dict(),
            "end_anchor": self.end_anchor.to_dict() if self.end_anchor else None,
            "is_explicit": self.is_explicit,
            "is_synchronous": self.is_synchronous,
            "metadata": self.metadata.to_dict() if self.metadata else None,
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchClaim":
        """Deserialize from dictionary."""
        return cls(
            start_anchor=AlignmentAnchor.from_dict(data["start_anchor"]),
            end_anchor=(
                AlignmentAnchor.from_dict(data["end_anchor"])
                if data.get("end_anchor")
                else None
            ),
            is_explicit=data.get("is_explicit", True),
            is_synchronous=data.get("is_synchronous", True),
            metadata=(
                MatchMetadata.from_dict(data["metadata"])
                if data.get("metadata")
                else None
            ),
            id=data.get("id", ""),
        )

    @classmethod
    def instant(
        cls,
        timeline_a_id: str,
        coordinate_a: float,
        timeline_b_id: str,
        coordinate_b: float,
        metadata: MatchMetadata | None = None,
        is_synchronous: bool = True,
    ) -> "MatchClaim":
        """Create an instant match (single anchor).

        Convenience constructor for instant (non-interval) matches.

        Args:
            timeline_a_id: First timeline's ID.
            coordinate_a: Coordinate in first timeline.
            timeline_b_id: Second timeline's ID.
            coordinate_b: Coordinate in second timeline.
            metadata: Optional provenance information.
            is_synchronous: Whether match is temporally synchronous.

        Returns:
            A new MatchClaim with a single anchor.
        """
        return cls(
            start_anchor=AlignmentAnchor(
                timeline_a_id=timeline_a_id,
                coordinate_a=coordinate_a,
                timeline_b_id=timeline_b_id,
                coordinate_b=coordinate_b,
                is_synchronous=is_synchronous,
            ),
            metadata=metadata,
            is_synchronous=is_synchronous,
        )

    @classmethod
    def interval(
        cls,
        timeline_a_id: str,
        start_a: float,
        end_a: float,
        timeline_b_id: str,
        start_b: float,
        end_b: float,
        metadata: MatchMetadata | None = None,
        is_synchronous: bool = True,
    ) -> "MatchClaim":
        """Create an interval match (two anchors).

        Convenience constructor for interval matches.

        Args:
            timeline_a_id: First timeline's ID.
            start_a: Start coordinate in first timeline.
            end_a: End coordinate in first timeline.
            timeline_b_id: Second timeline's ID.
            start_b: Start coordinate in second timeline.
            end_b: End coordinate in second timeline.
            metadata: Optional provenance information.
            is_synchronous: Whether match is temporally synchronous.

        Returns:
            A new MatchClaim with start and end anchors.
        """
        return cls(
            start_anchor=AlignmentAnchor(
                timeline_a_id=timeline_a_id,
                coordinate_a=start_a,
                timeline_b_id=timeline_b_id,
                coordinate_b=start_b,
                is_synchronous=is_synchronous,
            ),
            end_anchor=AlignmentAnchor(
                timeline_a_id=timeline_a_id,
                coordinate_a=end_a,
                timeline_b_id=timeline_b_id,
                coordinate_b=end_b,
                is_synchronous=is_synchronous,
            ),
            metadata=metadata,
            is_synchronous=is_synchronous,
        )

    def __repr__(self) -> str:
        match_type = "interval" if self.is_interval else "instant"
        flags = []
        if not self.is_explicit:
            flags.append("inferred")
        if not self.is_synchronous:
            flags.append("conceptual")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

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


# endregion
