"""Flow Control Events: Break and Jump for timeline traversal.

This module provides the Break and Jump classes that control the flow of
time through a timeline. From the TTA manuscript (Section 3.3-3.4):

**Break**: "A break is a control event that voids the contiguity at the
Instant where it is located."
- Prevents TimeIntervals from spanning its coordinate
- Cannot be inserted at coordinates already spanned by a TimeInterval
  (unless the spanning element "adopts" the break)

**Jump**: "A jump is a control event defined by two Instants: a JumpFrom
and a JumpTo Instant. When active, it makes any event located or starting
at JumpTo contiguous with any event ending at JumpFrom."
- Creates contiguity between non-adjacent coordinates
- Has activation conditions (e.g., "on Nth pass")

Common music notation mappings:
| Notation        | Break?  | Jump?  | Notes                           |
|-----------------|---------|--------|----------------------------------|
| Repeat End (:∥) | No      | Yes    | Jump back to repeat start       |
| Repeat Start    | Marker  | -      | Target for repeat end           |
| First Ending    | Yes     | Yes    | Break after; Jump at end        |
| Fine            | Yes     | No     | End of piece (conditional)      |
| Da Capo         | No      | Yes    | Jump to coordinate 0            |
| Dal Segno       | No      | Yes    | Jump to Segno coordinate        |
| Section End     | Yes     | No     | Always voids contiguity         |
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from fractions import Fraction
from typing import Any

from timetoalign.core import Coordinate, TimeUnit

module_logger = logging.getLogger(__name__)

# region Enums


class FlowControlType(Enum):
    """Types of flow control events.

    These map to common musical notation symbols and structures.
    """

    # Break types
    SECTION_END = auto()  # End of a section (always active)
    FINE = auto()  # End of piece (conditional, after DC/DS)
    VOLTA_START = auto()  # Start of an alternative ending bracket

    # Jump types
    REPEAT = auto()  # Simple repeat (end → start)
    DA_CAPO = auto()  # Jump to beginning
    DAL_SEGNO = auto()  # Jump to Segno marker
    TO_CODA = auto()  # Jump to Coda marker

    # Marker types (targets, not control events themselves)
    REPEAT_START = auto()  # ∥: Start repeat marker
    SEGNO = auto()  # 𝄋 Segno marker
    CODA = auto()  # 𝄌 Coda marker


class ActivationCondition(Enum):
    """When a flow control event becomes active.

    This determines on which traversal pass the event takes effect.
    """

    ALWAYS = auto()  # Always active (e.g., section end)
    FIRST_N = auto()  # Active on first N passes (e.g., repeat 2x)
    AFTER_FIRST = auto()  # Active after first pass (e.g., second ending)
    AFTER_DC_DS = auto()  # Active after Da Capo or Dal Segno


# endregion

# region Break


@dataclass(frozen=True)
class Break:
    """A control event that voids contiguity at a specific coordinate.

    From TTA manuscript (Section 3.3):
    "A break is a control event that voids the contiguity at the Instant
    where it is located."

    Constraints:
    - A Break cannot be added at coordinates already spanned by a
      TimeInterval (unless the spanning element "adopts" the break)
    - TimeIntervals cannot span a coordinate containing a Break

    Attributes:
        coordinate: The coordinate where contiguity is voided.
        control_type: The type of break (SECTION_END, FINE, VOLTA_START).
        condition: When the break becomes active.
        volta_number: For VOLTA_START, which ending number (1, 2, ...).
        repeat_count: For FINE, how many DC/DS must occur before active.
        label: Optional human-readable label (e.g., "End of Var. XI").
        meta: Additional metadata.

    Examples:
        >>> from timetoalign.core import Coordinate, TimeUnit
        >>> # Section end break
        >>> section_break = Break(
        ...     coordinate=Coordinate(100.0, TimeUnit.quarters),
        ...     control_type=FlowControlType.SECTION_END,
        ... )

        >>> # First ending bracket start
        >>> volta1 = Break(
        ...     coordinate=Coordinate(64.0, TimeUnit.quarters),
        ...     control_type=FlowControlType.VOLTA_START,
        ...     condition=ActivationCondition.FIRST_N,
        ...     volta_number=1,
        ... )
    """

    coordinate: Coordinate
    control_type: FlowControlType = FlowControlType.SECTION_END
    condition: ActivationCondition = ActivationCondition.ALWAYS
    volta_number: int | None = None
    repeat_count: int = 1
    label: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate break configuration."""
        if self.control_type == FlowControlType.VOLTA_START:
            if self.volta_number is None or self.volta_number < 1:
                raise ValueError(
                    f"VOLTA_START requires volta_number >= 1, got {self.volta_number}"
                )

    @property
    def position(self) -> float | Fraction:
        """The coordinate value where the break occurs."""
        return self.coordinate.value

    @property
    def unit(self) -> TimeUnit:
        """The time unit of the break coordinate."""
        return self.coordinate.unit

    def is_active(self, pass_number: int = 1, after_dc_ds: bool = False) -> bool:
        """Check if this break is active on a given traversal pass.

        Args:
            pass_number: The current pass number (1-indexed).
            after_dc_ds: Whether we're after a Da Capo or Dal Segno.

        Returns:
            True if the break should void contiguity on this pass.
        """
        if self.condition == ActivationCondition.ALWAYS:
            return True
        elif self.condition == ActivationCondition.FIRST_N:
            return pass_number <= self.repeat_count
        elif self.condition == ActivationCondition.AFTER_FIRST:
            return pass_number > 1
        elif self.condition == ActivationCondition.AFTER_DC_DS:
            return after_dc_ds
        return False

    def __repr__(self) -> str:
        type_str = self.control_type.name
        pos = self.position
        if self.volta_number:
            return f"Break({type_str} #{self.volta_number} @ {pos})"
        return f"Break({type_str} @ {pos})"


# endregion

# region Jump


@dataclass(frozen=True)
class Jump:
    """A control event that creates contiguity between non-adjacent coordinates.

    From TTA manuscript (Section 3.4):
    "A jump is a control event defined by two Instants: a JumpFrom and a
    JumpTo Instant. When active, it makes any event located or starting
    at JumpTo contiguous with any event ending at JumpFrom."

    Attributes:
        from_coordinate: The coordinate where the jump originates.
        to_coordinate: The coordinate where the jump lands.
        control_type: The type of jump (REPEAT, DA_CAPO, DAL_SEGNO, TO_CODA).
        condition: When the jump becomes active.
        repeat_count: For REPEAT, how many times to take the jump.
        volta_number: For volta-associated jumps, which ending.
        label: Optional human-readable label.
        meta: Additional metadata.

    Examples:
        >>> from timetoalign.core import Coordinate, TimeUnit
        >>> # Simple repeat: jump from measure 32 back to measure 8
        >>> repeat_jump = Jump(
        ...     from_coordinate=Coordinate(64.0, TimeUnit.quarters),
        ...     to_coordinate=Coordinate(16.0, TimeUnit.quarters),
        ...     control_type=FlowControlType.REPEAT,
        ...     repeat_count=1,  # Take jump once (play section twice)
        ... )

        >>> # Da Capo: jump to beginning
        >>> dc_jump = Jump(
        ...     from_coordinate=Coordinate(200.0, TimeUnit.quarters),
        ...     to_coordinate=Coordinate(0.0, TimeUnit.quarters),
        ...     control_type=FlowControlType.DA_CAPO,
        ... )
    """

    from_coordinate: Coordinate
    to_coordinate: Coordinate
    control_type: FlowControlType = FlowControlType.REPEAT
    condition: ActivationCondition = ActivationCondition.FIRST_N
    repeat_count: int = 1
    volta_number: int | None = None
    label: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate jump configuration."""
        if self.from_coordinate.unit != self.to_coordinate.unit:
            raise ValueError(
                f"Jump coordinates must have same unit: "
                f"{self.from_coordinate.unit} != {self.to_coordinate.unit}"
            )

    @property
    def from_position(self) -> float | Fraction:
        """The coordinate value where the jump originates."""
        return self.from_coordinate.value

    @property
    def to_position(self) -> float | Fraction:
        """The coordinate value where the jump lands."""
        return self.to_coordinate.value

    @property
    def unit(self) -> TimeUnit:
        """The time unit of the jump coordinates."""
        return self.from_coordinate.unit

    @property
    def is_backward(self) -> bool:
        """Whether this jump goes to an earlier coordinate (repeat)."""
        return self.to_position < self.from_position

    @property
    def is_forward(self) -> bool:
        """Whether this jump goes to a later coordinate (skip)."""
        return self.to_position > self.from_position

    @property
    def distance(self) -> float | Fraction:
        """The absolute distance covered by the jump."""
        diff = self.to_position - self.from_position
        return abs(diff)

    def is_active(self, pass_number: int = 1, after_dc_ds: bool = False) -> bool:
        """Check if this jump is active on a given traversal pass.

        Args:
            pass_number: The current pass number (1-indexed).
            after_dc_ds: Whether we're after a Da Capo or Dal Segno.

        Returns:
            True if the jump should be taken on this pass.
        """
        if self.condition == ActivationCondition.ALWAYS:
            return True
        elif self.condition == ActivationCondition.FIRST_N:
            return pass_number <= self.repeat_count
        elif self.condition == ActivationCondition.AFTER_FIRST:
            return pass_number > 1
        elif self.condition == ActivationCondition.AFTER_DC_DS:
            return after_dc_ds
        return False

    def remaining_activations(self, pass_number: int) -> int:
        """How many more times this jump can be taken.

        Args:
            pass_number: The current pass number (1-indexed).

        Returns:
            Number of remaining activations (0 if no longer active).
        """
        if self.condition == ActivationCondition.FIRST_N:
            return max(0, self.repeat_count - pass_number + 1)
        elif self.condition == ActivationCondition.ALWAYS:
            return float("inf")  # type: ignore
        return 0

    def __repr__(self) -> str:
        type_str = self.control_type.name
        from_pos = self.from_position
        to_pos = self.to_position
        direction = "←" if self.is_backward else "→"
        return f"Jump({type_str}: {from_pos} {direction} {to_pos})"


# endregion

# region FlowControlRegistry


@dataclass
class FlowControlRegistry:
    """Registry of all flow control events for a timeline.

    This class manages the collection of Breaks and Jumps for a timeline,
    providing methods to query, add, and validate flow control events.

    Attributes:
        breaks: List of Break events.
        jumps: List of Jump events.
        markers: Dict of named markers (Segno, Coda) and their coordinates.

    Examples:
        >>> registry = FlowControlRegistry()
        >>> registry.add_break(break_event)
        >>> registry.add_jump(jump_event)
        >>> registry.breaks_at(64.0)
        [Break(VOLTA_START #1 @ 64.0)]
    """

    breaks: list[Break] = field(default_factory=list)
    jumps: list[Jump] = field(default_factory=list)
    markers: dict[str, Coordinate] = field(default_factory=dict)

    def add_break(self, brk: Break) -> None:
        """Add a break to the registry.

        Args:
            brk: The Break to add.
        """
        self.breaks.append(brk)
        # Sort by coordinate for efficient lookup
        self.breaks.sort(key=lambda b: b.position)

    def add_jump(self, jump: Jump) -> None:
        """Add a jump to the registry.

        Args:
            jump: The Jump to add.
        """
        self.jumps.append(jump)
        # Sort by from_coordinate for traversal order
        self.jumps.sort(key=lambda j: j.from_position)

    def add_marker(self, name: str, coordinate: Coordinate) -> None:
        """Add a named marker (Segno, Coda, etc.).

        Args:
            name: The marker name (e.g., "segno", "coda").
            coordinate: The coordinate of the marker.
        """
        self.markers[name] = coordinate

    def breaks_at(self, coordinate: float | Fraction) -> list[Break]:
        """Get all breaks at a specific coordinate.

        Args:
            coordinate: The coordinate to query.

        Returns:
            List of breaks at that coordinate.
        """
        return [b for b in self.breaks if b.position == coordinate]

    def jumps_from(self, coordinate: float | Fraction) -> list[Jump]:
        """Get all jumps originating from a specific coordinate.

        Args:
            coordinate: The coordinate to query.

        Returns:
            List of jumps from that coordinate.
        """
        return [j for j in self.jumps if j.from_position == coordinate]

    def jumps_to(self, coordinate: float | Fraction) -> list[Jump]:
        """Get all jumps landing at a specific coordinate.

        Args:
            coordinate: The coordinate to query.

        Returns:
            List of jumps to that coordinate.
        """
        return [j for j in self.jumps if j.to_position == coordinate]

    def has_break_at(self, coordinate: float | Fraction) -> bool:
        """Check if there's a break at the coordinate.

        Args:
            coordinate: The coordinate to check.

        Returns:
            True if a break exists at that coordinate.
        """
        return any(b.position == coordinate for b in self.breaks)

    def has_flow_control(self) -> bool:
        """Check if any flow control events exist.

        Returns:
            True if there are any breaks, jumps, or markers.
        """
        return bool(self.breaks or self.jumps or self.markers)

    @property
    def has_repeats(self) -> bool:
        """Check if there are any repeat jumps."""
        return any(j.control_type == FlowControlType.REPEAT for j in self.jumps)

    @property
    def has_voltas(self) -> bool:
        """Check if there are any volta brackets."""
        return any(b.control_type == FlowControlType.VOLTA_START for b in self.breaks)

    @property
    def has_da_capo(self) -> bool:
        """Check if there's a Da Capo jump."""
        return any(j.control_type == FlowControlType.DA_CAPO for j in self.jumps)

    @property
    def has_dal_segno(self) -> bool:
        """Check if there's a Dal Segno jump."""
        return any(j.control_type == FlowControlType.DAL_SEGNO for j in self.jumps)

    def clear(self) -> None:
        """Clear all flow control events."""
        self.breaks.clear()
        self.jumps.clear()
        self.markers.clear()

    def __repr__(self) -> str:
        return (
            f"FlowControlRegistry({len(self.breaks)} breaks, "
            f"{len(self.jumps)} jumps, {len(self.markers)} markers)"
        )


# endregion
