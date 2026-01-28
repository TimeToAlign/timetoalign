"""TimelineGroup and PerfectAlignment classes.

This module implements the "perfect alignment" concept from the TTA model:
a bijective coordinate mapping between timelines via linear interpolation.

IMPORTANT CONCEPTUAL DISTINCTION:
- Perfect Alignment: Bijective coordinate mapping (linear interpolation).
  Does NOT imply the alignment is musically/temporally correct.
- Correct Alignment: A special case where mapping corresponds to reality.

Use cases for perfect (but not necessarily correct) alignment:
1. Quick rough alignment as a starting point
2. When you know two timelines are aligned (same recording, different features)
3. Placeholder alignment to be refined later
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from timetoalign.core import IdGenerator

if TYPE_CHECKING:
    from timetoalign.timelines import Timeline

module_logger = logging.getLogger(__name__)

# Module-level ID generator for groups
_group_id_generator = IdGenerator(scope="group")


def _reset_group_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _group_id_generator
    _group_id_generator = IdGenerator(scope="group")


# region PerfectAlignment


@dataclass(frozen=True)
class PerfectAlignment:
    """Defines how a timeline aligns to a group's reference timeline.

    The alignment is bijective within the specified ranges:
    source_start:source_end maps linearly to ref_start:ref_end

    This class implements linear interpolation for coordinate conversion
    between a source timeline and the group's reference timeline.

    Attributes:
        source_start: Start coordinate in the source timeline (default: 0).
        source_end: End coordinate in the source timeline.
            None means use timeline.length when added to group.
        ref_start: Start coordinate in reference timeline (default: 0).
        ref_end: End coordinate in reference timeline.
            None means use reference.length when adding.

    Examples:
        >>> # Full timeline to full reference (identity-like)
        >>> align = PerfectAlignment()
        >>> align.to_reference(50.0, source_length=100.0, ref_length=100.0)
        50.0

        >>> # Score excerpt maps to seconds 45-90 of recording
        >>> align = PerfectAlignment(
        ...     source_start=0, source_end=None,
        ...     ref_start=45.0, ref_end=90.0,
        ... )
        >>> align.to_reference(0.0, source_length=100.0, ref_length=180.0)
        45.0
    """

    source_start: float = 0.0
    source_end: float | None = None
    ref_start: float = 0.0
    ref_end: float | None = None

    def resolve(
        self,
        source_length: float,
        ref_length: float,
    ) -> tuple[float, float, float, float]:
        """Resolve None values to actual coordinates.

        Args:
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Tuple of (source_start, source_end, ref_start, ref_end).
        """
        src_end = self.source_end if self.source_end is not None else source_length
        r_end = self.ref_end if self.ref_end is not None else ref_length
        return (self.source_start, src_end, self.ref_start, r_end)

    def to_reference(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> float:
        """Convert source coordinate to reference coordinate.

        Uses linear interpolation within the alignment ranges.

        Args:
            coord: Coordinate in the source timeline.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Corresponding coordinate in the reference timeline.

        Raises:
            ValueError: If source range is zero-length (division by zero).
        """
        src_start, src_end, r_start, r_end = self.resolve(source_length, ref_length)

        if src_end == src_start:
            raise ValueError(
                f"Cannot convert: source range is zero-length "
                f"(start={src_start}, end={src_end})"
            )

        ratio = (coord - src_start) / (src_end - src_start)
        return r_start + ratio * (r_end - r_start)

    def from_reference(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> float:
        """Convert reference coordinate to source coordinate.

        Uses linear interpolation within the alignment ranges.

        Args:
            coord: Coordinate in the reference timeline.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            Corresponding coordinate in the source timeline.

        Raises:
            ValueError: If reference range is zero-length (division by zero).
        """
        src_start, src_end, r_start, r_end = self.resolve(source_length, ref_length)

        if r_end == r_start:
            raise ValueError(
                f"Cannot convert: reference range is zero-length "
                f"(start={r_start}, end={r_end})"
            )

        ratio = (coord - r_start) / (r_end - r_start)
        return src_start + ratio * (src_end - src_start)

    def is_within_source_range(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> bool:
        """Check if coordinate is within the source alignment range.

        Args:
            coord: Coordinate to check.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            True if coord is in [source_start, source_end].
        """
        src_start, src_end, _, _ = self.resolve(source_length, ref_length)
        return src_start <= coord <= src_end

    def is_within_ref_range(
        self,
        coord: float,
        source_length: float,
        ref_length: float,
    ) -> bool:
        """Check if coordinate is within the reference alignment range.

        Args:
            coord: Coordinate to check.
            source_length: Length of the source timeline.
            ref_length: Length of the reference timeline.

        Returns:
            True if coord is in [ref_start, ref_end].
        """
        _, _, r_start, r_end = self.resolve(source_length, ref_length)
        return r_start <= coord <= r_end


# endregion


# region TimelineGroup


@dataclass
class TimelineGroup:
    """Collection of timelines with perfect alignment.

    All timelines in a Group share the same temporal extent via bijective
    coordinate mapping. This does NOT imply the alignment is musically
    correct--just that coordinates can be converted without external
    match information.

    A TimelineGroup has a reference timeline that serves as the coordinate
    basis. Other timelines are added with PerfectAlignment specifications
    that define how their coordinates map to the reference.

    Attributes:
        id: Unique identifier for this group.
        reference_timeline_id: The timeline used as coordinate reference.
        name: Optional human-readable name for the group.
        meta: Additional metadata dictionary.

    Examples:
        >>> from timetoalign import DiscreteGraphicalTimeline
        >>> # Create a group with a reference timeline
        >>> dgt = DiscreteGraphicalTimeline(length=4875, unit="pixels")
        >>> group = TimelineGroup.from_reference(dgt, name="DGT1_Group")

        >>> # Add another timeline with explicit alignment
        >>> seconds_tl = ContinuousPhysicalTimeline(length=150, unit="seconds")
        >>> group.add_timeline(
        ...     seconds_tl,
        ...     alignment=PerfectAlignment(
        ...         source_start=0, source_end=150,
        ...         ref_start=0, ref_end=4875,
        ...     )
        ... )

        >>> # Convert coordinates between timelines
        >>> group.convert(2000, "dgt:1", "seconds_tl:1")
        61.54...  # Approximately
    """

    id: str
    reference_timeline_id: str
    timelines: dict[str, "Timeline"] = field(default_factory=dict)
    alignments: dict[str, PerfectAlignment] = field(default_factory=dict)
    name: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # Internal logger
    _logger: logging.Logger = field(
        default_factory=lambda: module_logger, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize logger after dataclass creation."""
        self._logger = module_logger.getChild(self.id)

    @classmethod
    def from_reference(
        cls,
        reference: "Timeline",
        uid: str | None = None,
        name: str | None = None,
    ) -> "TimelineGroup":
        """Create a new group with a reference timeline.

        The reference timeline defines the coordinate basis for the group.
        All other timelines will be aligned relative to this one.

        Args:
            reference: The timeline to use as reference.
            uid: Optional explicit ID. If None, auto-generated.
            name: Optional human-readable name.

        Returns:
            A new TimelineGroup containing only the reference timeline.
        """
        if uid is None:
            uid = _group_id_generator.create(type_hint="TimelineGroup")

        group = cls(
            id=uid,
            reference_timeline_id=reference.id,
            name=name,
        )

        # Add reference with identity alignment
        group.timelines[reference.id] = reference
        group.alignments[reference.id] = PerfectAlignment()

        group._logger.debug(f"Created group with reference '{reference.id}'")
        return group

    @property
    def reference(self) -> "Timeline":
        """The reference timeline for this group."""
        return self.timelines[self.reference_timeline_id]

    @property
    def n_timelines(self) -> int:
        """Number of timelines in this group."""
        return len(self.timelines)

    def add_timeline(
        self,
        timeline: "Timeline",
        alignment: PerfectAlignment | None = None,
    ) -> None:
        """Add a timeline to the group with specified alignment.

        Args:
            timeline: The timeline to add.
            alignment: How this timeline aligns to the reference.
                If None, uses default PerfectAlignment (full extent to full extent).

        Raises:
            ValueError: If timeline ID already exists in group.
        """
        if timeline.id in self.timelines:
            raise ValueError(
                f"Timeline '{timeline.id}' is already in group '{self.id}'"
            )

        if alignment is None:
            alignment = PerfectAlignment()

        self.timelines[timeline.id] = timeline
        self.alignments[timeline.id] = alignment

        self._logger.debug(f"Added timeline '{timeline.id}' with alignment {alignment}")

    def remove_timeline(self, timeline_id: str) -> "Timeline":
        """Remove a timeline from the group.

        Args:
            timeline_id: ID of the timeline to remove.

        Returns:
            The removed timeline.

        Raises:
            ValueError: If timeline_id is the reference or doesn't exist.
        """
        if timeline_id == self.reference_timeline_id:
            raise ValueError(
                f"Cannot remove reference timeline '{timeline_id}' from group"
            )

        if timeline_id not in self.timelines:
            raise ValueError(f"Timeline '{timeline_id}' is not in group '{self.id}'")

        timeline = self.timelines.pop(timeline_id)
        del self.alignments[timeline_id]

        self._logger.debug(f"Removed timeline '{timeline_id}'")
        return timeline

    def get_timeline(self, timeline_id: str) -> "Timeline":
        """Get a timeline by ID.

        Args:
            timeline_id: The timeline's unique identifier.

        Returns:
            The Timeline object.

        Raises:
            KeyError: If no timeline with that ID exists.
        """
        if timeline_id not in self.timelines:
            raise KeyError(f"No timeline '{timeline_id}' in group '{self.id}'")
        return self.timelines[timeline_id]

    def get_alignment(self, timeline_id: str) -> PerfectAlignment:
        """Get the alignment for a timeline.

        Args:
            timeline_id: The timeline's unique identifier.

        Returns:
            The PerfectAlignment for that timeline.

        Raises:
            KeyError: If no timeline with that ID exists.
        """
        if timeline_id not in self.alignments:
            raise KeyError(f"No timeline '{timeline_id}' in group '{self.id}'")
        return self.alignments[timeline_id]

    def convert(
        self,
        coord: float,
        from_timeline: str,
        to_timeline: str,
    ) -> float:
        """Convert a coordinate from one timeline to another.

        Uses the PerfectAlignment mappings to convert via the reference:
        source -> reference -> target

        Args:
            coord: The coordinate value to convert.
            from_timeline: ID of the source timeline.
            to_timeline: ID of the target timeline.

        Returns:
            The converted coordinate in the target timeline.

        Raises:
            KeyError: If either timeline is not in the group.
            ValueError: If conversion fails (e.g., zero-length range).
        """
        if from_timeline not in self.timelines:
            raise KeyError(f"Source timeline '{from_timeline}' not in group")
        if to_timeline not in self.timelines:
            raise KeyError(f"Target timeline '{to_timeline}' not in group")

        # Same timeline: no conversion needed
        if from_timeline == to_timeline:
            return coord

        # Get timelines and alignments
        source_tl = self.timelines[from_timeline]
        target_tl = self.timelines[to_timeline]
        ref_tl = self.timelines[self.reference_timeline_id]

        source_align = self.alignments[from_timeline]
        target_align = self.alignments[to_timeline]

        # Convert source -> reference
        ref_coord = source_align.to_reference(
            coord,
            source_length=float(source_tl.length.value),
            ref_length=float(ref_tl.length.value),
        )

        # Convert reference -> target
        return target_align.from_reference(
            ref_coord,
            source_length=float(target_tl.length.value),
            ref_length=float(ref_tl.length.value),
        )

    def to_reference_coord(self, coord: float, timeline_id: str) -> float:
        """Convert a coordinate to reference timeline coordinates.

        Args:
            coord: The coordinate value to convert.
            timeline_id: ID of the source timeline.

        Returns:
            The coordinate in reference timeline units.
        """
        return self.convert(coord, timeline_id, self.reference_timeline_id)

    def from_reference_coord(self, coord: float, timeline_id: str) -> float:
        """Convert a reference coordinate to a specific timeline.

        Args:
            coord: The coordinate in reference timeline units.
            timeline_id: ID of the target timeline.

        Returns:
            The coordinate in target timeline units.
        """
        return self.convert(coord, self.reference_timeline_id, timeline_id)

    def iter_timelines(self) -> list[tuple[str, "Timeline", PerfectAlignment]]:
        """Iterate over all timelines with their alignments.

        Yields:
            Tuples of (timeline_id, timeline, alignment).
        """
        return [
            (tl_id, tl, self.alignments[tl_id]) for tl_id, tl in self.timelines.items()
        ]

    def summary(self) -> dict[str, Any]:
        """Get a summary of the group.

        Returns:
            Dictionary with group information.
        """
        return {
            "id": self.id,
            "name": self.name,
            "reference_timeline_id": self.reference_timeline_id,
            "n_timelines": len(self.timelines),
            "timeline_ids": list(self.timelines.keys()),
            "timeline_names": {tl_id: tl.name for tl_id, tl in self.timelines.items()},
            "meta": self.meta,
        }

    def get_display_name(self, timeline_id: str) -> str:
        """Get human-readable name for a timeline.

        Uses Timeline.name if set, otherwise falls back to timeline_id.

        Args:
            timeline_id: The timeline's unique identifier.

        Returns:
            Display name for the timeline.
        """
        if timeline_id not in self.timelines:
            return timeline_id
        return self.timelines[timeline_id].name

    def __repr__(self) -> str:
        return (
            f"TimelineGroup(id={self.id!r}, "
            f"reference={self.reference_timeline_id!r}, "
            f"n_timelines={len(self.timelines)})"
        )


# endregion
