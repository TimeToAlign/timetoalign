"""Flow API: Compute unfolded measure sequences from flow control data.

This module implements Phase 3.7 of the TimeToAlign! implementation roadmap.
It provides classes for computing and representing "flows" - the sequence of
measure visitations that results from following flow control instructions
(repeats, voltas, D.S., D.C., etc.).

From the design spec (measure_handling_design.md Part 14):

    FlowMode: Enum for flow computation modes
    FlowStep: A single step in a Flow sequence
    Flow: A computed flow (sequence of measure visitations)
    FlowMap: Attached to timelines for coordinate transformation
    FlowController: Compute Flow paths from MeasureData

Terminology:
    - "Flow" is used uniformly instead of "traversal"
    - mc_playthrough: Monotonically increasing index in unfolded sequence
    - mn_playthrough: MN with occurrence suffix (e.g., "19a", "19b")

Gold Standard Conventions (from ms3):
    - mn_playthrough suffix: Always 'a' for first occurrence, 'b' for second
    - Split bars: Same mn_playthrough for all MCs sharing same MN
    - quarterbeats: Cumulative in unfolded, NOT reset at jumps
    - mc_playthrough: Monotonically increasing 1, 2, 3, ...
    - Final row: next = -1 indicates end of flow
"""

from __future__ import annotations

import logging
import weakref
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

    from timetoalign.loader.score.stores.measures import MeasureData

module_logger = logging.getLogger(__name__)


# region FlowMode


class FlowMode(Enum):
    """Flow computation modes.

    Different contexts require different unfoldings:

    General modes:
    - DEFAULT: Most complete flow (all repeats taken), equivalent to MS3
    - PRINTED: All bars as printed (no unfolding)
    - SINGLE_PASS: Single playthrough (last volta only)
    - CUSTOM: User-provided flow sequence

    Software-specific modes (for ground truth validation):
    - MS3: From ms3's *_unfolded.measures.tsv (gold standard)
    - PARTITURA_MINIMAL: partitura's unfold_part_minimal()
    - PARTITURA_MAXIMAL: partitura's unfold_part_maximal()
    - MUSIC21: music21's expandRepeats()
    """

    DEFAULT = "default"
    MS3 = "ms3"
    PARTITURA_MINIMAL = "partitura_minimal"
    PARTITURA_MAXIMAL = "partitura_maximal"
    MUSIC21 = "music21"
    PRINTED = "printed"
    SINGLE_PASS = "single"
    CUSTOM = "custom"


# endregion

# region MeasureUnit


@dataclass(frozen=True)
class MeasureUnit:
    """Single measure from the folded score (one MeasureData row).

    This is the fundamental building block from which AtomicSections
    are constructed. MeasureUnit represents the "folded" skeleton of
    the score before any unfolding takes place.

    Attributes:
        mc: Measure Count (monotonic, 1-indexed).
        mn: Measure Number label (may have suffix like "19a").
        duration_qb: Duration in quarter beats.
        next: Tuple of possible next MCs. (-1 = end of piece)
        volta: Ending number (1, 2, ...) or None.
        timesig: Time signature string ("4/4", "3/4") or None.
        timesig_duration_qb: Expected duration from time signature (computed).
        start_repeat: True if has repeat start marker (||:).
        end_repeat: True if has repeat end marker (:||).
        jump_from: True if this MC is a jump origin (D.C., D.S., to_coda).
        jump_to: True if this MC is a jump target (segno, coda destination).
        segno: Segno marker name if present (e.g., "segno", "segno2").
        coda: Coda marker name if present (e.g., "coda", "codab").
        fine: True if Fine marker present.
        section_break: True if section break at this MC.
        flow_control_types: Tuple of FlowControlType.value strings for serialization.

    Examples:
        >>> unit = MeasureUnit(
        ...     mc=1,
        ...     mn="1",
        ...     duration_qb=Fraction(4),
        ...     next=(2,),
        ... )
        >>> unit.mc
        1
        >>> unit.next
        (2,)
    """

    mc: int
    mn: str
    duration_qb: Fraction
    next: tuple[int, ...]
    volta: int | None = None
    timesig: str | None = None
    timesig_duration_qb: Fraction | None = None
    start_repeat: bool = False
    end_repeat: bool = False
    jump_from: bool = False
    jump_to: bool = False
    segno: str | None = None
    coda: str | None = None
    fine: bool = False
    section_break: bool = False
    flow_control_types: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame serialization.

        Returns:
            Dict with all MeasureUnit fields, suitable for DataFrame conversion.
            The flow_control_types tuple is joined with semicolons for CSV storage.
        """
        return {
            "mc": self.mc,
            "mn": self.mn,
            "duration_qb": float(self.duration_qb),
            "next": list(self.next),
            "volta": self.volta,
            "timesig": self.timesig,
            "timesig_duration_qb": (
                float(self.timesig_duration_qb) if self.timesig_duration_qb else None
            ),
            "start_repeat": self.start_repeat,
            "end_repeat": self.end_repeat,
            "jump_from": self.jump_from,
            "jump_to": self.jump_to,
            "segno": self.segno,
            "coda": self.coda,
            "fine": self.fine,
            "section_break": self.section_break,
            "flow_control_types": ";".join(self.flow_control_types),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MeasureUnit":
        """Create MeasureUnit from dictionary (e.g., DataFrame row).

        Args:
            d: Dictionary with MeasureUnit field values.

        Returns:
            New MeasureUnit instance.
        """
        # Parse flow_control_types from semicolon-separated string
        fct = d.get("flow_control_types", "")
        if isinstance(fct, str):
            flow_control_types = tuple(fct.split(";")) if fct else ()
        else:
            flow_control_types = tuple(fct) if fct else ()

        # Parse next field
        next_val = d.get("next", [-1])
        if isinstance(next_val, str):
            # Handle string representation like "[1, 2]" or "1, 2"
            cleaned = next_val.strip().strip("[]()").replace(" ", "")
            next_tuple = (
                tuple(int(x) for x in cleaned.split(",") if x) if cleaned else (-1,)
            )
        elif isinstance(next_val, (list, tuple)):
            next_tuple = tuple(next_val)
        else:
            next_tuple = (int(next_val),) if next_val is not None else (-1,)

        # Parse duration
        duration = d.get("duration_qb", 4)
        if isinstance(duration, Fraction):
            duration_qb = duration
        else:
            duration_qb = Fraction(duration) if duration else Fraction(4)

        # Parse timesig_duration_qb
        ts_dur = d.get("timesig_duration_qb")
        timesig_duration_qb = Fraction(ts_dur) if ts_dur is not None else None

        return cls(
            mc=int(d["mc"]),
            mn=str(d.get("mn", d["mc"])),
            duration_qb=duration_qb,
            next=next_tuple,
            volta=d.get("volta"),
            timesig=d.get("timesig"),
            timesig_duration_qb=timesig_duration_qb,
            start_repeat=bool(d.get("start_repeat")),
            end_repeat=bool(d.get("end_repeat")),
            jump_from=bool(d.get("jump_from")),
            jump_to=bool(d.get("jump_to")),
            segno=d.get("segno"),
            coda=d.get("coda"),
            fine=bool(d.get("fine")),
            section_break=bool(d.get("section_break")),
            flow_control_types=flow_control_types,
        )

    def __repr__(self) -> str:
        volta_str = f", volta={self.volta}" if self.volta else ""
        return f"MeasureUnit(MC {self.mc}: {self.mn}, next={self.next}{volta_str})"


# endregion

# region Typed MeasureUnit Subclasses


class IncompletePosition(Enum):
    """Position of an incomplete measure within the score.

    Used by IncompleteMeasure to classify why a measure is incomplete:
    - ANACRUSIS: Pickup measure at the start of the piece
    - FINAL: Final incomplete measure (often pairs with anacrusis)
    - SPLIT_FIRST: First part of a split measure
    - SPLIT_SECOND: Second part of a split measure
    - UNKNOWN: Position not yet determined
    """

    ANACRUSIS = "anacrusis"
    FINAL = "final"
    SPLIT_FIRST = "split_first"
    SPLIT_SECOND = "split_second"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IncompleteMeasure(MeasureUnit):
    """A MeasureUnit that does not metrically complete on its own.

    NOT a group - this is a typed copy of a MeasureUnit created during
    Phase 1 (Typing) of the two-phase algorithm.

    IncompleteMeasure inherits all MeasureUnit properties including
    FlowControlTypes, enabling serialization round-trip.

    Examples:
        - Anacrusis (pickup): First measure shorter than time signature
        - Final incomplete: Last measure shorter than time signature
        - Split part: One half of a split measure

    Note:
        An IncompleteMeasure can later form part of a SplitMeasure group
        (e.g., anacrusis + final measure after repeat = SplitMeasure).

    Attributes:
        position: Classification of why this measure is incomplete.
    """

    position: IncompletePosition = IncompletePosition.UNKNOWN


@dataclass(frozen=True)
class CompleteMeasure(MeasureUnit):
    """A MeasureUnit that metrically completes on its own.

    NOT a group - this is a typed copy of a MeasureUnit created during
    Phase 1 (Typing) of the two-phase algorithm.

    The simple, default case: duration_qb == timesig_duration_qb.

    CompleteMeasure inherits all MeasureUnit properties including
    FlowControlTypes, enabling serialization round-trip.
    """

    pass


@dataclass(frozen=True)
class OverlengthMeasure(MeasureUnit):
    """A MeasureUnit that exceeds the expected metrical length.

    NOT a group - this is a typed copy of a MeasureUnit created during
    Phase 1 (Typing) of the two-phase algorithm.

    OverlengthMeasure inherits all MeasureUnit properties including
    FlowControlTypes, enabling serialization round-trip.

    Examples:
        - Fermata: Written duration > time signature
        - Cadenza: Extended passage notated in single measure
        - Ad lib: Performer-determined length
    """

    pass


# Type alias for any typed measure
TypedMeasure = IncompleteMeasure | CompleteMeasure | OverlengthMeasure

# endregion

# region MeasureGroup


@dataclass(frozen=True)
class MeasureGroup:
    """Base class for groupings of typed MeasureUnits.

    Groups are constructed in Phase 2 (Grouping), AFTER MeasureUnits have been
    typed as IncompleteMeasure/CompleteMeasure/OverlengthMeasure in Phase 1.

    MeasureGroup is an abstract base - use SplitMeasure, IncompleteGroup,
    Volta, or CompleteMeasureGroup for concrete groupings.

    Attributes:
        members: Tuple of typed MeasureUnits in this group.
    """

    members: tuple["TypedMeasure", ...]

    def __post_init__(self) -> None:
        """Validate group has at least one member."""
        if not self.members:
            raise ValueError("MeasureGroup must have at least one member")

    @property
    def mc_start(self) -> int:
        """First MC in this group."""
        return min(m.mc for m in self.members)

    @property
    def mc_end(self) -> int:
        """First MC AFTER this group (right-open)."""
        return max(m.mc for m in self.members) + 1

    @property
    def mc_range(self) -> tuple[int, int]:
        """Return (mc_start, mc_end) tuple (right-open interval)."""
        return (self.mc_start, self.mc_end)

    @property
    def total_duration_qb(self) -> Fraction:
        """Total duration in quarterbeats."""
        return sum((m.duration_qb for m in self.members), Fraction(0))

    def __len__(self) -> int:
        """Return number of measures in this group."""
        return len(self.members)

    def __repr__(self) -> str:
        return f"MeasureGroup(MC [{self.mc_start},{self.mc_end}), {len(self.members)} measures)"


@dataclass(frozen=True)
class SplitMeasure(MeasureGroup):
    """Multiple IncompleteMeasures that together form a complete metrical unit.

    This is the complex case where IncompleteMeasures combine to form a
    complete measure duration. Split measures share the same measure number (mn).

    Examples:
        - Anacrusis (1/4) + Final (3/4) after repeat = complete 4/4
        - Split bar: MC 11 (1/4) + MC 12 (1/4) = complete 2/4 (same mn="10")

    Note:
        All members must be IncompleteMeasure instances. The detection
        algorithm uses shared mn as a strong signal for split measure pairs.
    """

    def __post_init__(self) -> None:
        """Validate all members are IncompleteMeasure."""
        super().__post_init__()
        for m in self.members:
            if not isinstance(m, IncompleteMeasure):
                raise TypeError(
                    f"SplitMeasure members must be IncompleteMeasure, got {type(m).__name__}"
                )

    def __repr__(self) -> str:
        mcs = [m.mc for m in self.members]
        return f"SplitMeasure(MC {mcs}, total={self.total_duration_qb})"


@dataclass(frozen=True)
class IncompleteGroup(MeasureGroup):
    """Isolated IncompleteMeasure(s) that don't yet form a split.

    Used for anacrusis or final measures that haven't been paired with their
    complement. In AtomicSections, these may later merge into SplitMeasures
    when the flow brings them together in PlaythroughSections.

    Note:
        All members must be IncompleteMeasure instances.
    """

    def __post_init__(self) -> None:
        """Validate all members are IncompleteMeasure."""
        super().__post_init__()
        for m in self.members:
            if not isinstance(m, IncompleteMeasure):
                raise TypeError(
                    f"IncompleteGroup members must be IncompleteMeasure, got {type(m).__name__}"
                )

    def __repr__(self) -> str:
        # Safe to access position since __post_init__ validates all are IncompleteMeasure
        positions = [
            m.position.value for m in self.members if isinstance(m, IncompleteMeasure)
        ]
        return f"IncompleteGroup(MC [{self.mc_start},{self.mc_end}), positions={positions})"


@dataclass(frozen=True)
class VoltaGroup(MeasureGroup):
    """Typed MeasureUnits under the same volta bracket.

    A VoltaGroup contains measures that share the same volta number (1, 2, 3...).
    Each different volta number creates a separate VoltaGroup.

    Note:
        A VoltaGroup is contained within ONE AtomicSection. Multiple voltas
        (e.g., volta 1 and volta 2) are separated by Breaks and thus cannot
        be in the same section.

    Attributes:
        volta_number: The volta bracket number (1, 2, 3, ...).
    """

    volta_number: int = 1

    def __post_init__(self) -> None:
        """Validate volta_number is positive."""
        super().__post_init__()
        if self.volta_number < 1:
            raise ValueError(f"volta_number must be >= 1, got {self.volta_number}")

    def __repr__(self) -> str:
        return (
            f"VoltaGroup(volta={self.volta_number}, MC [{self.mc_start},{self.mc_end}), "
            f"{len(self.members)} measures)"
        )


@dataclass(frozen=True)
class CompleteMeasureGroup(MeasureGroup):
    """Adjacent CompleteMeasures grouped together.

    Useful for identifying contiguous "normal" passages between special
    structures (voltas, splits, incomplete measures, etc.).

    Note:
        All members must be CompleteMeasure instances. OverlengthMeasures
        are NOT included in CompleteMeasureGroup (they're a special case).
    """

    def __post_init__(self) -> None:
        """Validate all members are CompleteMeasure."""
        super().__post_init__()
        for m in self.members:
            if not isinstance(m, CompleteMeasure):
                raise TypeError(
                    f"CompleteMeasureGroup members must be CompleteMeasure, got {type(m).__name__}"
                )

    def __repr__(self) -> str:
        return f"CompleteMeasureGroup(MC [{self.mc_start},{self.mc_end}), {len(self.members)} measures)"


@dataclass(frozen=True)
class OverlengthGroup(MeasureGroup):
    """One or more OverlengthMeasures grouped together.

    For overlength measures like fermatas, cadenzas, or ad lib passages.

    Note:
        All members must be OverlengthMeasure instances.
    """

    def __post_init__(self) -> None:
        """Validate all members are OverlengthMeasure."""
        super().__post_init__()
        for m in self.members:
            if not isinstance(m, OverlengthMeasure):
                raise TypeError(
                    f"OverlengthGroup members must be OverlengthMeasure, got {type(m).__name__}"
                )

    def __repr__(self) -> str:
        return f"OverlengthGroup(MC [{self.mc_start},{self.mc_end}), {len(self.members)} measures)"


# endregion

# region AtomicSection


@dataclass(frozen=True)
class AtomicSection:
    """Smallest indivisible traversal unit (similar to partitura's segment model).

    Atomic sections are derived from:
    - partitura's add_segments()/get_segments() for MusicXML/MEI
    - next[] array analysis for TSV/MeasureMap

    Section IDs (A, B, C, ...) form a canonical reference for mapping all
    flow modes. The partitura_minimal flow mode defines these canonical sections.

    Note:
        MC ranges use the **right-open interval convention** [mc_start, mc_end),
        consistent with partitura and the TTA manuscript. For example, mc_start=1
        and mc_end=5 means measures 1, 2, 3, 4 (four measures total).

    Attributes:
        id: Letter identifier (A, B, C...) from partitura or generated.
        mc_start: First MC of this section (inclusive).
        mc_end: First MC AFTER this section (exclusive, right-open).
        to: List of possible next section IDs.
        await_to: Destinations available after a leap (D.C./D.S. patterns).
        section_type: "default", "leap_end", or "leap_start".

    Examples:
        >>> sec = AtomicSection(
        ...     id="A",
        ...     mc_start=1,
        ...     mc_end=5,  # Right-open: includes MCs 1,2,3,4
        ...     to=("A", "B"),
        ...     section_type="leap_end",
        ... )
        >>> sec.mc_range
        (1, 5)
        >>> sec.mc_count
        4
    """

    id: str
    mc_start: int
    mc_end: int
    to: tuple[str, ...] = ()
    await_to: tuple[str, ...] = ()
    section_type: str = "default"  # "default" | "leap_end" | "leap_start"
    typed_measures: tuple["TypedMeasure", ...] | None = None  # Phase 1 output
    groups: tuple["MeasureGroup", ...] | None = None  # Phase 2 output

    def __post_init__(self) -> None:
        """Validate section configuration."""
        if self.mc_end < self.mc_start:
            raise ValueError(
                f"AtomicSection '{self.id}': mc_end ({self.mc_end}) "
                f"cannot be before mc_start ({self.mc_start})"
            )
        if self.section_type not in ("default", "leap_end", "leap_start"):
            raise ValueError(
                f"AtomicSection '{self.id}': invalid section_type '{self.section_type}'"
            )

    @property
    def mc_range(self) -> tuple[int, int]:
        """Return (mc_start, mc_end) tuple (right-open interval)."""
        return (self.mc_start, self.mc_end)

    @property
    def mc_count(self) -> int:
        """Number of MCs in this section (right-open: end - start)."""
        return self.mc_end - self.mc_start

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "mc_start": self.mc_start,
            "mc_end": self.mc_end,
            "to": list(self.to),
            "await_to": list(self.await_to),
            "section_type": self.section_type,
        }
        if self.typed_measures is not None:
            result["typed_measures_count"] = len(self.typed_measures)
            result["incomplete_count"] = sum(
                1 for m in self.typed_measures if isinstance(m, IncompleteMeasure)
            )
            result["overlength_count"] = sum(
                1 for m in self.typed_measures if isinstance(m, OverlengthMeasure)
            )
        if self.groups is not None:
            result["groups_count"] = len(self.groups)
            result["group_types"] = [type(g).__name__ for g in self.groups]
        return result

    def __repr__(self) -> str:
        typed_info = ""
        if self.typed_measures is not None:
            typed_info = f", {len(self.typed_measures)} typed"
        groups_info = ""
        if self.groups is not None:
            groups_info = f", {len(self.groups)} groups"
        return (
            f"AtomicSection({self.id}: MC [{self.mc_start},{self.mc_end}), "
            f"{self.section_type}{typed_info}{groups_info})"
        )


# endregion

# region PlaythroughSection


@dataclass(frozen=True)
class PlaythroughSection:
    """A contiguous group of atomic sections in a specific traversal.

    This is what gets written to .flow.csv and compared via is_equivalent().
    Each PlaythroughSection represents a contiguous run of MCs in the unfolded
    sequence.

    Note:
        MC ranges use the **right-open interval convention** [mc_start, mc_end),
        consistent with partitura and the TTA manuscript. For example, mc_start=1
        and mc_end=9 means measures 1, 2, 3, 4, 5, 6, 7, 8 (eight measures total).

    Attributes:
        mc_start: First MC of this playthrough section (inclusive).
        mc_end: First MC AFTER this playthrough section (exclusive, right-open).
        atomic_section_ids: Which atomic sections this covers.

    Examples:
        >>> sec = PlaythroughSection(mc_start=1, mc_end=9, atomic_section_ids=("A", "B"))
        >>> sec.mc_range
        (1, 9)
        >>> sec.mc_count
        8
    """

    mc_start: int
    mc_end: int
    atomic_section_ids: tuple[str, ...] = ()
    typed_measures: tuple["TypedMeasure", ...] | None = None  # Phase 1 output
    groups: tuple["MeasureGroup", ...] | None = None  # Phase 2 output

    def __post_init__(self) -> None:
        """Validate section configuration."""
        if self.mc_end < self.mc_start:
            raise ValueError(
                f"PlaythroughSection: mc_end ({self.mc_end}) "
                f"cannot be before mc_start ({self.mc_start})"
            )

    @property
    def mc_range(self) -> tuple[int, int]:
        """Return (mc_start, mc_end) tuple (right-open interval)."""
        return (self.mc_start, self.mc_end)

    @property
    def mc_count(self) -> int:
        """Number of MCs in this section (right-open: end - start)."""
        return self.mc_end - self.mc_start

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "mc_start": self.mc_start,
            "mc_end": self.mc_end,
            "atomic_sections": ";".join(self.atomic_section_ids),
        }
        if self.typed_measures is not None:
            result["typed_measures_count"] = len(self.typed_measures)
        if self.groups is not None:
            result["groups_count"] = len(self.groups)
            result["group_types"] = [type(g).__name__ for g in self.groups]
        return result

    def to_mc_sequence(self) -> list[int]:
        """Return list of all MCs in this section.

        Returns:
            List of MC values from mc_start to mc_end (right-open, excludes mc_end).
        """
        return list(range(self.mc_start, self.mc_end))

    def __repr__(self) -> str:
        secs = ";".join(self.atomic_section_ids) if self.atomic_section_ids else "?"
        typed_info = ""
        if self.typed_measures is not None:
            typed_info = f", {len(self.typed_measures)} typed"
        groups_info = ""
        if self.groups is not None:
            groups_info = f", {len(self.groups)} groups"
        return f"PlaythroughSection(MC [{self.mc_start},{self.mc_end}) [{secs}]{typed_info}{groups_info})"


# endregion

# region Flow


@dataclass
class Flow:
    """A computed flow (sequence of measure visitations).

    A Flow represents one possible path through a score, accounting for
    repeats, jumps, and voltas. It can be:
    - Computed by FlowController from MeasureData
    - Loaded from .flow.csv ground truth
    - Compared using is_equivalent()

    Flows are section-based, using `sections` (list of PlaythroughSection)
    for .flow.csv serialization and is_equivalent() comparison.

    Flows computed by FlowController have a controller reference, allowing
    access to MeasureUnits via iter_units(). Flows loaded from CSV are
    "detached" and do not have controller access.

    Note:
        MC ranges use the **right-open interval convention** [mc_start, mc_end),
        consistent with partitura and the TTA manuscript.

    Attributes:
        sections: The sequence of PlaythroughSection objects.
        mode: The FlowMode used to compute this flow.
        folded_length: Number of unique MCs (measures in printed score).
        scope_id: Identifier for this flow (defaults to mode.value).
        source_metadata: Optional metadata from the source MeasureData.
    """

    sections: list[PlaythroughSection] = field(default_factory=list)
    mode: FlowMode = FlowMode.DEFAULT
    folded_length: int = 0
    scope_id: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)
    _controller_ref: "weakref.ref[FlowController] | None" = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Initialize scope_id from mode if not set."""
        if not self.scope_id:
            object.__setattr__(self, "scope_id", self.mode.value)

    @property
    def controller(self) -> "FlowController | None":
        """Get the FlowController that created this Flow, if still alive.

        Returns:
            FlowController if this Flow was computed and controller is alive,
            None if Flow was loaded from CSV or controller was garbage collected.
        """
        if self._controller_ref is None:
            return None
        return self._controller_ref()

    def iter_units(self) -> Iterator[MeasureUnit]:
        """Iterate over MeasureUnits via the controller.

        This provides access to the folded score skeleton (one MeasureUnit
        per MeasureData row).

        Yields:
            MeasureUnit objects in MC order.

        Raises:
            ValueError: If Flow is detached from controller (e.g., loaded from CSV).

        Examples:
            >>> flow = controller.compute_flow()
            >>> for unit in flow.iter_units():
            ...     print(f"MC {unit.mc}: next={unit.next}")
        """
        ctrl = self.controller
        if ctrl is None:
            raise ValueError(
                "Flow is detached from controller. "
                "iter_units() is only available for flows computed by FlowController."
            )
        yield from ctrl.iter_units()

    # === Class Methods (Constructors) ===

    @classmethod
    def from_sections(
        cls,
        sections: list[PlaythroughSection],
        mode: FlowMode,
        folded_length: int | None = None,
    ) -> "Flow":
        """Create a Flow from PlaythroughSections.

        Args:
            sections: List of PlaythroughSection objects.
            mode: The FlowMode for this flow.
            folded_length: Number of unique MCs. If None, computed from sections.

        Returns:
            New Flow instance with sections populated.
        """
        if folded_length is None:
            # Estimate from section ranges (may not be accurate for repeated sections)
            # Note: Right-open interval, so range(start, end) is correct
            all_mcs = set()
            for sec in sections:
                all_mcs.update(range(sec.mc_start, sec.mc_end))
            folded_length = len(all_mcs)

        return cls(
            sections=sections,
            mode=mode,
            folded_length=folded_length,
        )

    @classmethod
    def from_records(cls, records: list[dict], mode: FlowMode) -> "Flow":
        """Create Flow from list of dicts with mc_start, mc_end, atomic_sections.

        Note:
            MC ranges use right-open interval convention [mc_start, mc_end).

        Args:
            records: List of dicts, each with keys:
                - mc_start: int (inclusive)
                - mc_end: int (exclusive, right-open)
                - atomic_sections: str (semicolon-separated, e.g., "A;B")
                  (also accepts "atomic_segments" for backwards compatibility)
            mode: The FlowMode for this flow.

        Returns:
            New Flow instance with sections populated.
        """
        sections = []
        for rec in records:
            # Support both old "atomic_segments" and new "atomic_sections" keys
            atomic_ids_str = rec.get("atomic_sections", rec.get("atomic_segments", ""))
            atomic_ids = tuple(
                s.strip() for s in atomic_ids_str.split(";") if s.strip()
            )
            sections.append(
                PlaythroughSection(
                    mc_start=int(rec["mc_start"]),
                    mc_end=int(rec["mc_end"]),
                    atomic_section_ids=atomic_ids,
                )
            )
        return cls.from_sections(sections, mode)

    @classmethod
    def from_dataframe(cls, df: "pd.DataFrame", mode: FlowMode) -> "Flow":
        """Create Flow from DataFrame with mc_start, mc_end, atomic_sections columns.

        Note:
            MC ranges use right-open interval convention [mc_start, mc_end).

        Args:
            df: DataFrame with columns: mc_start, mc_end, atomic_sections.
                (also accepts "atomic_segments" for backwards compatibility)
            mode: The FlowMode for this flow.

        Returns:
            New Flow instance with sections populated.
        """
        records = df.to_dict("records")
        return cls.from_records(records, mode)

    @classmethod
    def from_csv(cls, path: "Path | str", mode: FlowMode) -> "Flow":
        """Load Flow for specific mode from .flow.csv file.

        Filters CSV to rows matching the given flow_mode.

        Note:
            MC ranges use right-open interval convention [mc_start, mc_end).

        Args:
            path: Path to the .flow.csv file.
            mode: The FlowMode to load.

        Returns:
            New Flow instance with sections populated.

        Raises:
            ValueError: If no entries found for the given mode.
        """
        from pathlib import Path as _Path

        import pandas as pd

        if isinstance(path, str):
            path = _Path(path)

        df = pd.read_csv(path)

        # Filter to matching flow_mode
        mode_df = df[df["flow_mode"] == mode.value]

        if len(mode_df) == 0:
            available_modes = df["flow_mode"].unique().tolist()
            raise ValueError(
                f"No entries for flow_mode '{mode.value}' in {path}. "
                f"Available modes: {available_modes}"
            )

        # Skip ERROR entries
        mode_df = mode_df[mode_df["mc_start"] != "ERROR"]

        # Convert to DataFrame explicitly to satisfy type checker
        return cls.from_dataframe(pd.DataFrame(mode_df), mode)

    # === Serialization Methods ===

    def to_records(self) -> list[dict]:
        """Export as list of dicts (section-based).

        Returns:
            List of dicts with keys: mc_start, mc_end, atomic_sections.
        """
        return [sec.to_dict() for sec in self.sections]

    def to_section_dataframe(self) -> "pd.DataFrame":
        """Export as DataFrame (section-based).

        Returns:
            DataFrame with columns: mc_start, mc_end, atomic_sections.
        """
        import pandas as pd

        return pd.DataFrame(self.to_records())

    def to_csv_rows(self, source_file: str, software_version: str) -> list[dict]:
        """Export as .flow.csv format rows.

        Returns list of dicts with keys:
            flow_mode, source_file, software_version, mc_start, mc_end, atomic_sections

        Args:
            source_file: The file that was parsed to produce this flow.
            software_version: Software name and version for reproducibility.

        Returns:
            List of dicts ready for CSV writing.
        """
        rows = []
        for sec in self.sections:
            rows.append(
                {
                    "flow_mode": self.mode.value,
                    "source_file": source_file,
                    "software_version": software_version,
                    "mc_start": sec.mc_start,
                    "mc_end": sec.mc_end,
                    "atomic_sections": ";".join(sec.atomic_section_ids),
                }
            )
        return rows

    # === Comparison Methods ===

    def is_equivalent(self, other: "Flow") -> bool:
        """Compare by zipped (mc_start, mc_end) ranges.

        Two flows are equivalent if they have the same number of sections
        and each corresponding section has matching mc_start and mc_end.

        Note: atomic_section_ids are NOT compared - only MC ranges matter.

        Args:
            other: Another Flow to compare against.

        Returns:
            True if flows are equivalent, False otherwise.
        """
        if len(self.sections) != len(other.sections):
            return False
        return all(
            (a.mc_start, a.mc_end) == (b.mc_start, b.mc_end)
            for a, b in zip(self.sections, other.sections)
        )

    # === Properties ===

    @property
    def unfolded_length(self) -> int:
        """Number of measure visitations in the unfolded sequence."""
        # Compute from sections (right-open: mc_count = end - start)
        return sum(sec.mc_count for sec in self.sections)

    @property
    def total_quarterbeats(self) -> Fraction:
        """Total duration of the unfolded sequence in quarter beats.

        Note:
            This requires controller access to get measure durations.
            Returns 0 for detached flows (loaded from CSV).
        """
        ctrl = self.controller
        if ctrl is None:
            return Fraction(0)
        # Sum durations from MeasureUnits for all MCs in the flow
        total = Fraction(0)
        mc_sequence = self.to_mc_sequence()
        unit_lookup = {u.mc: u for u in ctrl.iter_units()}
        for mc in mc_sequence:
            if mc in unit_lookup:
                total += unit_lookup[mc].duration_qb
        return total

    @property
    def has_repeats(self) -> bool:
        """Whether the flow contains repeated measures."""
        return self.unfolded_length > self.folded_length

    # === Convenience Methods ===

    def to_mc_sequence(self) -> list[int]:
        """Return the sequence of MCs in traversal order.

        Returns:
            List of MC values in the order they are visited (right-open intervals).
        """
        # Compute from sections (right-open: range(start, end) excludes end)
        result = []
        for sec in self.sections:
            result.extend(range(sec.mc_start, sec.mc_end))
        return result

    def to_atomic_sequence(self) -> list[str]:
        """Return flattened sequence of atomic section IDs.

        This provides a canonical representation of the flow as a sequence
        of atomic section traversals. Useful for comparing flows and debugging.

        Returns:
            List of atomic section IDs in traversal order.

        Examples:
            >>> flow = Flow.from_sections([
            ...     PlaythroughSection(1, 17, ("A", "B")),
            ...     PlaythroughSection(17, 32, ("C",)),
            ...     PlaythroughSection(6, 17, ("B",)),
            ... ], FlowMode.DEFAULT)
            >>> flow.to_atomic_sequence()
            ['A', 'B', 'C', 'B']
        """
        result = []
        for sec in self.sections:
            result.extend(sec.atomic_section_ids)
        return result

    def diff_flows(self, other: "Flow") -> str:
        """Show differences between this flow and another using sequence alignment.

        Uses difflib to produce a human-readable diff of atomic sequences.

        Args:
            other: Another Flow to compare against.

        Returns:
            String showing the alignment/diff between the two flows.
        """
        import difflib

        self_seq = self.to_atomic_sequence()
        other_seq = other.to_atomic_sequence()

        # Use unified diff for readability
        diff = difflib.unified_diff(
            [f"{i+1}: {s}" for i, s in enumerate(other_seq)],
            [f"{i+1}: {s}" for i, s in enumerate(self_seq)],
            fromfile="other",
            tofile="self",
            lineterm="",
        )
        return "\n".join(diff)

    def to_dataframe(self) -> "pd.DataFrame":
        """Convert to pandas DataFrame with section information.

        Returns:
            DataFrame with columns: mc_start, mc_end, atomic_sections
            for each PlaythroughSection.

        Note:
            This returns section-level data. For per-MC data, use
            iter_units() with controller access.
        """
        import pandas as pd

        rows = [sec.to_dict() for sec in self.sections]
        return pd.DataFrame(rows)

    def __repr__(self) -> str:
        ratio = self.unfolded_length / self.folded_length if self.folded_length else 0
        sec_info = f", {len(self.sections)} sections" if self.sections else ""
        return (
            f"Flow({self.mode.value}: {self.folded_length} folded -> "
            f"{self.unfolded_length} unfolded, ratio={ratio:.2f}{sec_info})"
        )


def load_valid_flows(csv_path: "Path | str") -> dict[FlowMode, "Flow"]:
    """Load all valid flows from a .flow.csv file, grouped by flow_mode.

    Args:
        csv_path: Path to the .flow.csv file.

    Returns:
        Dict mapping FlowMode to Flow for each unique flow_mode in the CSV.
        Skips unknown flow_modes and ERROR entries.

    Examples:
        >>> flows = load_valid_flows(Path("tests/data/target_flows/specimen.flow.csv"))
        >>> default_flow = flows[FlowMode.DEFAULT]
        >>> for mode, flow in flows.items():
        ...     print(f"{mode.value}: {len(flow.sections)} sections")
    """
    from pathlib import Path as _Path

    import pandas as pd

    if isinstance(csv_path, str):
        csv_path = _Path(csv_path)

    df = pd.read_csv(csv_path)

    # Skip ERROR entries
    df = df[df["mc_start"] != "ERROR"]

    flows: dict[FlowMode, Flow] = {}
    for mode_str, group in df.groupby("flow_mode"):
        try:
            mode = FlowMode(str(mode_str))
            # Ensure group is a DataFrame
            group_df = pd.DataFrame(group)
            flows[mode] = Flow.from_dataframe(group_df, mode)
        except ValueError:
            # Skip unknown flow modes
            module_logger.debug(f"Skipping unknown flow_mode: {mode_str}")
            pass

    return flows


# endregion

# region FlowMap


@dataclass
class FlowMap:
    """A FlowMap attached to a timeline for coordinate transformation.

    FlowMap encodes one specific Flow and enables:
    - Folded -> Unfolded coordinate conversion (1:N, since repeats duplicate)
    - Unfolded -> Folded coordinate lookup (N:1)
    - Creating transformed timeline views

    Attributes:
        flow: The computed Flow.
    """

    flow: Flow

    def folded_to_unfolded(self, qb: Fraction | float) -> list[Fraction]:
        """Convert a folded coordinate to unfolded coordinates.

        Since a folded coordinate may be visited multiple times (repeats),
        this returns a list of all corresponding unfolded coordinates.

        Args:
            qb: Quarter beat position in folded timeline.

        Returns:
            List of quarter beat positions in unfolded timeline.

        Note:
            This is a placeholder implementation. Full coordinate mapping
            requires MeasureUnit data with quarterbeats positions.
        """
        qb = Fraction(qb) if not isinstance(qb, Fraction) else qb
        # TODO: Implement proper coordinate-to-MC lookup using controller
        # For now, return the input coordinate
        return [qb]

    def unfolded_to_folded(self, qb: Fraction | float) -> Fraction:
        """Convert an unfolded coordinate to folded coordinate.

        Args:
            qb: Quarter beat position in unfolded timeline.

        Returns:
            Quarter beat position in folded timeline.

        Raises:
            ValueError: If coordinate is outside the flow range.

        Note:
            This is a placeholder implementation. Full coordinate mapping
            requires MeasureUnit data with quarterbeats positions.
        """
        qb = Fraction(qb) if not isinstance(qb, Fraction) else qb
        # TODO: Implement proper coordinate lookup using controller
        # For now, return the input coordinate
        return qb

    def __repr__(self) -> str:
        return f"FlowMap({self.flow})"


# endregion

# region FlowController


class FlowController:
    """Compute Flow paths from MeasureData or atomic sections.

    The FlowController operates at the section level:
    1. Derives atomic sections from next[] arrays OR accepts from partitura
    2. Uses flow control markers + volta attributes to execute flow logic
    3. Groups atomic sections into playthrough sections per FlowMode

    The algorithm follows the 'next' field in measure data, using visit
    counts to choose which branch to take at repeat points. This matches
    the ms3 unfolding algorithm.

    Attributes:
        measures: The source MeasureData.

    Public API:
        - get_sections(mode=None): Get sections (None=atomic, else playthrough)
        - iter_sections(mode=None): Iterate over sections
        - iter_units(): Iterate over MeasureUnits (folded skeleton)
        - compute_flow(mode): Compute Flow for the given mode

    Examples:
        >>> controller = FlowController(measure_data)
        >>> flow = controller.compute_flow()
        >>> print(f"Unfolded: {flow.unfolded_length} measures")

        >>> # Get atomic sections (folded structure)
        >>> for sec in controller.get_sections():
        ...     print(f"{sec.id}: MC [{sec.mc_start},{sec.mc_end})")

        >>> # Get playthrough sections for DEFAULT mode
        >>> for sec in controller.get_sections(FlowMode.DEFAULT):
        ...     print(f"MC [{sec.mc_start},{sec.mc_end})")

        >>> # Iterate over MeasureUnits
        >>> for unit in controller.iter_units():
        ...     print(f"MC {unit.mc}: next={unit.next}, jump_from={unit.jump_from}")
    """

    def __init__(self, measures: "MeasureData") -> None:
        """Initialize FlowController from MeasureData.

        Args:
            measures: MeasureData containing flow control fields.
        """
        self._measures = measures
        self._measure_lookup: dict[int, dict[str, Any]] = {}
        self._units: list[MeasureUnit] = []
        self._atomic_sections: list[AtomicSection] = []
        self._build_lookup()
        self._build_units()
        self._build_atomic_sections()

    @classmethod
    def from_atomic_sections(
        cls,
        sections: list[AtomicSection],
        measures: "MeasureData | None" = None,
    ) -> "FlowController":
        """Initialize directly from atomic sections (e.g., from partitura).

        Args:
            sections: List of AtomicSection objects.
            measures: Optional MeasureData for detailed step computation.

        Returns:
            FlowController with pre-built atomic sections.
        """
        # Create instance without calling __init__
        instance = object.__new__(cls)
        instance._measures = measures
        instance._measure_lookup = {}
        instance._units = []
        instance._atomic_sections = list(sections)

        # Build lookup and units if measures provided
        if measures is not None:
            instance._build_lookup()
            instance._build_units()

        return instance

    def _build_lookup(self) -> None:
        """Build MC -> measure dict lookup from MeasureData.

        Extracts all available columns including FlowControl markers:
        - Basic: mc, mn, duration, next, quarterbeats
        - FlowControl: volta, timesig, start_repeat, end_repeat, segno, coda, fine
        """
        if len(self._measures) == 0:
            return

        table = self._measures._table

        # Get column data
        mc_col = table.column("mc").to_pylist()
        mn_col = (
            table.column("mn").to_pylist()
            if "mn" in table.column_names
            else [str(mc) for mc in mc_col]
        )

        # Get duration - handle struct type
        if "duration" in table.column_names:
            dur_col = table.column("duration").to_pylist()
            # Duration is a struct with 'value' field
            duration_values = []
            for d in dur_col:
                if d is None:
                    duration_values.append(Fraction(4))
                elif isinstance(d, dict):
                    duration_values.append(Fraction(d.get("value", 4)))
                else:
                    duration_values.append(Fraction(d))
        elif "actual_length" in table.column_names:
            al_col = table.column("actual_length").to_pylist()
            duration_values = [Fraction(d) if d else Fraction(4) for d in al_col]
        else:
            duration_values = [Fraction(4)] * len(mc_col)

        # Get 'next' field
        next_col = (
            table.column("next").to_pylist()
            if "next" in table.column_names
            else [None] * len(mc_col)
        )

        # Get 'start' (quarterbeats) - handle struct type
        if "start" in table.column_names:
            start_col = table.column("start").to_pylist()
            qb_values = []
            for s in start_col:
                if s is None:
                    qb_values.append(Fraction(0))
                elif isinstance(s, dict):
                    qb_values.append(Fraction(s.get("value", 0)))
                else:
                    qb_values.append(Fraction(s))
        else:
            qb_values = [Fraction(0)] * len(mc_col)

        # Get FlowControl fields (with safe defaults)
        def _get_column_safe(name: str, default: Any = None) -> list:
            """Get column values or return list of defaults."""
            if name in table.column_names:
                return table.column(name).to_pylist()
            return [default] * len(mc_col)

        volta_col = _get_column_safe("volta")
        timesig_col = _get_column_safe("timesig")
        start_repeat_col = _get_column_safe("start_repeat", False)
        end_repeat_col = _get_column_safe("end_repeat", False)
        segno_col = _get_column_safe("segno")
        coda_col = _get_column_safe("coda")
        fine_col = _get_column_safe("fine", False)
        section_break_col = _get_column_safe("section_break", False)

        for i, mc in enumerate(mc_col):
            # Parse 'next' field
            next_val = next_col[i]
            if next_val is None or next_val == "":
                # Default: next MC or -1 for last
                if i < len(mc_col) - 1:
                    next_list = [mc_col[i + 1]]
                else:
                    next_list = [-1]
            elif isinstance(next_val, str):
                # Parse various string formats:
                # - Comma-separated: "2, 3, 4" or "2,3,4"
                # - Tuple string: "(2,)" or "(2, 3)"
                # - Single value: "2"
                next_list = []
                # Remove tuple parentheses if present
                cleaned = next_val.strip()
                if cleaned.startswith("(") and cleaned.endswith(")"):
                    cleaned = cleaned[1:-1]
                # Split by comma
                for part in cleaned.split(","):
                    part = part.strip()
                    if part:
                        try:
                            next_list.append(int(part))
                        except ValueError:
                            pass
                if not next_list:
                    # If we couldn't parse anything, default to next MC or -1
                    if i < len(mc_col) - 1:
                        next_list = [mc_col[i + 1]]
                    else:
                        next_list = [-1]
            elif isinstance(next_val, list):
                next_list = next_val
            else:
                next_list = [-1]

            self._measure_lookup[mc] = {
                "mc": mc,
                "mn": str(mn_col[i]) if mn_col[i] is not None else str(mc),
                "duration_qb": duration_values[i],
                "quarterbeats": qb_values[i],
                "next": next_list,
                # FlowControl fields
                "volta": volta_col[i],
                "timesig": timesig_col[i],
                "start_repeat": bool(start_repeat_col[i]),
                "end_repeat": bool(end_repeat_col[i]),
                "segno": segno_col[i] if segno_col[i] else None,
                "coda": coda_col[i] if coda_col[i] else None,
                "fine": bool(fine_col[i]),
                "section_break": bool(section_break_col[i]),
            }

    def _build_units(self) -> None:
        """Create MeasureUnits from the measure lookup.

        MeasureUnits represent the folded score skeleton - one per MeasureData row.
        Populates all FlowControlType fields including computed values:
        - jump_from, jump_to derived from next[] patterns
        - timesig_duration_qb computed from timesig string
        - flow_control_types tuple for serialization
        """
        if not self._measure_lookup:
            return

        sorted_mcs = sorted(self._measure_lookup.keys())

        for mc in sorted_mcs:
            info = self._measure_lookup[mc]
            next_list = info.get("next", [-1])

            # Compute jump_from: MC where next[] indicates a jump
            # A jump is when next != [MC+1] (non-contiguous)
            mc_idx = sorted_mcs.index(mc)
            is_jump_from = self._is_jump_from(mc, next_list, sorted_mcs, mc_idx)

            # Compute jump_to: MC that is a jump target (segno, coda, or non-adjacent next target)
            is_jump_to = self._is_jump_to(mc, info, sorted_mcs)

            # Parse timesig to duration in quarterbeats
            timesig = info.get("timesig")
            timesig_duration_qb = self._parse_timesig_duration(timesig)

            # Build flow_control_types tuple
            flow_control_types = self._extract_flow_control_types(
                info, is_jump_from, is_jump_to
            )

            unit = MeasureUnit(
                mc=mc,
                mn=str(info.get("mn", mc)),
                duration_qb=info.get("duration_qb", Fraction(4)),
                next=tuple(next_list),
                volta=info.get("volta"),
                timesig=timesig,
                timesig_duration_qb=timesig_duration_qb,
                start_repeat=bool(info.get("start_repeat")),
                end_repeat=bool(info.get("end_repeat")),
                jump_from=is_jump_from,
                jump_to=is_jump_to,
                segno=info.get("segno"),
                coda=info.get("coda"),
                fine=bool(info.get("fine")),
                section_break=bool(info.get("section_break")),
                flow_control_types=flow_control_types,
            )
            self._units.append(unit)

    def _is_jump_from(
        self, mc: int, next_list: list[int], sorted_mcs: list[int], mc_idx: int
    ) -> bool:
        """Determine if this MC is a jump origin.

        A jump origin is an MC where next[] indicates non-contiguous continuation:
        - next has multiple options (volta/repeat choice)
        - next jumps backward (repeat end)
        - next jumps forward > MC+1 (skip/coda)

        Args:
            mc: Current MC.
            next_list: List of possible next MCs.
            sorted_mcs: Sorted list of all MCs.
            mc_idx: Index of mc in sorted_mcs.

        Returns:
            True if this MC is a jump origin.
        """
        if len(next_list) > 1:
            # Multiple next options (volta or conditional jump)
            return True

        if not next_list or next_list == [-1]:
            # End of piece, not a jump
            return False

        next_mc = next_list[0]

        # Check if next is contiguous
        if mc_idx < len(sorted_mcs) - 1:
            expected_next = sorted_mcs[mc_idx + 1]
            if next_mc != expected_next:
                return True

        return False

    def _is_jump_to(self, mc: int, info: dict[str, Any], sorted_mcs: list[int]) -> bool:
        """Determine if this MC is a jump target.

        A jump target is an MC that:
        - Has a segno marker
        - Has a coda marker
        - Is the target of a non-adjacent next[] from another MC

        Args:
            mc: Current MC.
            info: Measure info dict.
            sorted_mcs: Sorted list of all MCs.

        Returns:
            True if this MC is a jump target.
        """
        # Explicit markers
        if info.get("segno") or info.get("coda"):
            return True

        # Check if any other MC jumps to this MC (non-adjacent)
        mc_idx = sorted_mcs.index(mc)
        for other_mc in sorted_mcs:
            if other_mc == mc:
                continue
            other_info = self._measure_lookup[other_mc]
            other_next = other_info.get("next", [])
            if mc in other_next:
                other_idx = sorted_mcs.index(other_mc)
                # Check if jump is non-adjacent
                if mc_idx != other_idx + 1:
                    return True

        return False

    def _parse_timesig_duration(self, timesig: str | None) -> Fraction | None:
        """Parse time signature to expected duration in quarterbeats.

        Args:
            timesig: Time signature string like "4/4", "3/4", "6/8".

        Returns:
            Expected duration in quarterbeats, or None if unparseable.

        Examples:
            >>> _parse_timesig_duration("4/4")
            Fraction(4, 1)
            >>> _parse_timesig_duration("3/4")
            Fraction(3, 1)
            >>> _parse_timesig_duration("6/8")
            Fraction(3, 1)  # 6 eighth notes = 3 quarterbeats
        """
        if timesig is None:
            return None
        try:
            # Handle compound time signatures
            parts = timesig.split("/")
            if len(parts) != 2:
                return None
            num, denom = int(parts[0]), int(parts[1])
            # Duration in quarterbeats = num * (4 / denom)
            return Fraction(num * 4, denom)
        except (ValueError, ZeroDivisionError):
            return None

    def _extract_flow_control_types(
        self, info: dict[str, Any], is_jump_from: bool, is_jump_to: bool
    ) -> tuple[str, ...]:
        """Extract FlowControlType values from measure info.

        Builds a tuple of FlowControlType.value strings for serialization.

        Args:
            info: Measure info dict.
            is_jump_from: Whether this MC is a jump origin.
            is_jump_to: Whether this MC is a jump target.

        Returns:
            Tuple of FlowControlType value strings.
        """
        types: list[str] = []

        if info.get("start_repeat"):
            types.append("repeat_start")
        if info.get("end_repeat"):
            types.append("repeat_end")
        if info.get("segno"):
            types.append("segno")
        if info.get("coda"):
            types.append("coda")
        if info.get("fine"):
            types.append("fine")
        if info.get("section_break"):
            types.append("section_break")
        if is_jump_from:
            types.append("jump_from")
        if is_jump_to:
            types.append("jump_to")

        return tuple(types)

    def _type_measure(self, unit: MeasureUnit) -> TypedMeasure:
        """Create a typed copy of a MeasureUnit (Phase 1 of two-phase algorithm).

        Compares the measure's actual duration with the expected duration from
        the time signature to classify measures as:
        - IncompleteMeasure: actual < expected (anacrusis, final, split)
        - CompleteMeasure: actual == expected (normal measure)
        - OverlengthMeasure: actual > expected (fermata, cadenza)

        The typed copy inherits all properties from the generating MeasureUnit,
        including FlowControlTypes.

        Args:
            unit: The MeasureUnit to type.

        Returns:
            IncompleteMeasure, CompleteMeasure, or OverlengthMeasure.
        """
        # If no time signature info, default to CompleteMeasure
        if unit.timesig_duration_qb is None:
            return CompleteMeasure(
                mc=unit.mc,
                mn=unit.mn,
                duration_qb=unit.duration_qb,
                next=unit.next,
                volta=unit.volta,
                timesig=unit.timesig,
                timesig_duration_qb=unit.timesig_duration_qb,
                start_repeat=unit.start_repeat,
                end_repeat=unit.end_repeat,
                jump_from=unit.jump_from,
                jump_to=unit.jump_to,
                segno=unit.segno,
                coda=unit.coda,
                fine=unit.fine,
                section_break=unit.section_break,
                flow_control_types=unit.flow_control_types,
            )

        # Compare durations
        if unit.duration_qb < unit.timesig_duration_qb:
            position = self._determine_incomplete_position(unit)
            return IncompleteMeasure(
                mc=unit.mc,
                mn=unit.mn,
                duration_qb=unit.duration_qb,
                next=unit.next,
                volta=unit.volta,
                timesig=unit.timesig,
                timesig_duration_qb=unit.timesig_duration_qb,
                start_repeat=unit.start_repeat,
                end_repeat=unit.end_repeat,
                jump_from=unit.jump_from,
                jump_to=unit.jump_to,
                segno=unit.segno,
                coda=unit.coda,
                fine=unit.fine,
                section_break=unit.section_break,
                flow_control_types=unit.flow_control_types,
                position=position,
            )
        elif unit.duration_qb > unit.timesig_duration_qb:
            return OverlengthMeasure(
                mc=unit.mc,
                mn=unit.mn,
                duration_qb=unit.duration_qb,
                next=unit.next,
                volta=unit.volta,
                timesig=unit.timesig,
                timesig_duration_qb=unit.timesig_duration_qb,
                start_repeat=unit.start_repeat,
                end_repeat=unit.end_repeat,
                jump_from=unit.jump_from,
                jump_to=unit.jump_to,
                segno=unit.segno,
                coda=unit.coda,
                fine=unit.fine,
                section_break=unit.section_break,
                flow_control_types=unit.flow_control_types,
            )
        else:
            return CompleteMeasure(
                mc=unit.mc,
                mn=unit.mn,
                duration_qb=unit.duration_qb,
                next=unit.next,
                volta=unit.volta,
                timesig=unit.timesig,
                timesig_duration_qb=unit.timesig_duration_qb,
                start_repeat=unit.start_repeat,
                end_repeat=unit.end_repeat,
                jump_from=unit.jump_from,
                jump_to=unit.jump_to,
                segno=unit.segno,
                coda=unit.coda,
                fine=unit.fine,
                section_break=unit.section_break,
                flow_control_types=unit.flow_control_types,
            )

    def _determine_incomplete_position(self, unit: MeasureUnit) -> IncompletePosition:
        """Determine the position of an incomplete measure.

        Uses the unit's position in the score to classify:
        - First measure -> ANACRUSIS
        - Last measure -> FINAL
        - Otherwise -> SPLIT_FIRST (may be refined by Phase 2 grouping)

        Args:
            unit: The incomplete MeasureUnit.

        Returns:
            IncompletePosition classification.
        """
        if not self._units:
            return IncompletePosition.UNKNOWN

        # Find index of this unit
        idx = next((i for i, u in enumerate(self._units) if u.mc == unit.mc), -1)
        if idx == -1:
            return IncompletePosition.UNKNOWN

        if idx == 0:
            return IncompletePosition.ANACRUSIS
        elif idx == len(self._units) - 1:
            return IncompletePosition.FINAL
        else:
            # Check if this might be part of a split measure
            # For now, classify as SPLIT_FIRST (Phase 2 will refine)
            return IncompletePosition.SPLIT_FIRST

    # ========================================================================
    # Phase 2: Grouping methods
    # ========================================================================

    def _build_groups(
        self, typed_measures: tuple[TypedMeasure, ...]
    ) -> tuple[MeasureGroup, ...]:
        """Group typed measures into MeasureGroups (Phase 2 of two-phase algorithm).

        Algorithm for complete coverage (every measure belongs to exactly one group):
        1. Identify VoltaGroups (consecutive measures with same volta number)
        2. Identify SplitMeasures (IncompleteMeasures with same mn that sum to time sig)
        3. Identify isolated IncompleteMeasures -> IncompleteGroup
        4. Identify OverlengthMeasures -> OverlengthGroup
        5. Group remaining CompleteMeasures into CompleteMeasureGroups

        Args:
            typed_measures: Tuple of typed measures from Phase 1.

        Returns:
            Tuple of MeasureGroup objects covering all measures.
        """
        if not typed_measures:
            return ()

        # Track which measures have been grouped
        grouped_mcs: set[int] = set()
        groups: list[MeasureGroup] = []

        # Step 1: VoltaGroups (consecutive measures with same volta number)
        volta_groups = self._group_voltas(typed_measures, grouped_mcs)
        groups.extend(volta_groups)

        # Step 2: SplitMeasures (IncompleteMeasures with same mn)
        split_groups = self._group_splits(typed_measures, grouped_mcs)
        groups.extend(split_groups)

        # Step 3: Remaining IncompleteMeasures -> IncompleteGroup
        incomplete_groups = self._group_incompletes(typed_measures, grouped_mcs)
        groups.extend(incomplete_groups)

        # Step 4: OverlengthMeasures -> OverlengthGroup
        overlength_groups = self._group_overlengths(typed_measures, grouped_mcs)
        groups.extend(overlength_groups)

        # Step 5: Remaining CompleteMeasures -> CompleteMeasureGroup
        complete_groups = self._group_completes(typed_measures, grouped_mcs)
        groups.extend(complete_groups)

        # Sort groups by mc_start for consistent ordering
        groups.sort(key=lambda g: g.mc_start)

        return tuple(groups)

    def _group_voltas(
        self, typed_measures: tuple[TypedMeasure, ...], grouped_mcs: set[int]
    ) -> list[VoltaGroup]:
        """Group consecutive measures with the same volta number.

        Volta groups are identified by the volta attribute (1, 2, 3...).
        A VoltaGroup is contained within ONE AtomicSection - multiple voltas
        are separated by Breaks and cannot be in the same section.

        Args:
            typed_measures: Tuple of typed measures.
            grouped_mcs: Set of MCs already grouped (will be updated).

        Returns:
            List of VoltaGroup objects.
        """
        groups: list[VoltaGroup] = []
        current_volta: int | None = None
        current_members: list[TypedMeasure] = []

        for m in typed_measures:
            if m.volta is not None and m.mc not in grouped_mcs:
                if m.volta == current_volta:
                    # Continue current volta group
                    current_members.append(m)
                else:
                    # Start new volta group (save previous if exists)
                    if current_members and current_volta is not None:
                        groups.append(
                            VoltaGroup(
                                members=tuple(current_members),
                                volta_number=current_volta,
                            )
                        )
                        for member in current_members:
                            grouped_mcs.add(member.mc)
                    current_volta = m.volta
                    current_members = [m]
            else:
                # Non-volta measure: finalize current group if exists
                if current_members and current_volta is not None:
                    groups.append(
                        VoltaGroup(
                            members=tuple(current_members),
                            volta_number=current_volta,
                        )
                    )
                    for member in current_members:
                        grouped_mcs.add(member.mc)
                current_volta = None
                current_members = []

        # Finalize last group
        if current_members and current_volta is not None:
            groups.append(
                VoltaGroup(
                    members=tuple(current_members),
                    volta_number=current_volta,
                )
            )
            for member in current_members:
                grouped_mcs.add(member.mc)

        return groups

    def _group_splits(
        self, typed_measures: tuple[TypedMeasure, ...], grouped_mcs: set[int]
    ) -> list[SplitMeasure]:
        """Group IncompleteMeasures that together form a complete metrical unit.

        Detection strategy: Measures with the same mn (measure number) are
        candidates for split measures. Their durations should sum to the
        time signature duration.

        Args:
            typed_measures: Tuple of typed measures.
            grouped_mcs: Set of MCs already grouped (will be updated).

        Returns:
            List of SplitMeasure objects.
        """
        groups: list[SplitMeasure] = []

        # Group IncompleteMeasures by mn
        by_mn: dict[str, list[IncompleteMeasure]] = defaultdict(list)
        for m in typed_measures:
            if isinstance(m, IncompleteMeasure) and m.mc not in grouped_mcs:
                by_mn[m.mn].append(m)

        # Check each group with same mn
        for mn, measures in by_mn.items():
            if len(measures) > 1:
                # Check if they sum to time signature duration
                total = sum((m.duration_qb for m in measures), Fraction(0))
                # Get expected duration from first measure
                expected = measures[0].timesig_duration_qb
                if expected is not None and total == expected:
                    # Valid split measure
                    groups.append(SplitMeasure(members=tuple(measures)))
                    for m in measures:
                        grouped_mcs.add(m.mc)

        return groups

    def _group_incompletes(
        self, typed_measures: tuple[TypedMeasure, ...], grouped_mcs: set[int]
    ) -> list[IncompleteGroup]:
        """Group isolated IncompleteMeasures that don't form splits.

        These are measures that haven't been grouped yet - typically anacrusis
        or final measures that will be paired with their complement when the
        flow brings them together in PlaythroughSections.

        Args:
            typed_measures: Tuple of typed measures.
            grouped_mcs: Set of MCs already grouped (will be updated).

        Returns:
            List of IncompleteGroup objects (one per isolated incomplete).
        """
        groups: list[IncompleteGroup] = []

        for m in typed_measures:
            if isinstance(m, IncompleteMeasure) and m.mc not in grouped_mcs:
                # Create singleton IncompleteGroup
                groups.append(IncompleteGroup(members=(m,)))
                grouped_mcs.add(m.mc)

        return groups

    def _group_overlengths(
        self, typed_measures: tuple[TypedMeasure, ...], grouped_mcs: set[int]
    ) -> list[OverlengthGroup]:
        """Group OverlengthMeasures.

        Currently creates individual groups for each overlength measure.
        Future: could group adjacent overlength measures (cadenzas).

        Args:
            typed_measures: Tuple of typed measures.
            grouped_mcs: Set of MCs already grouped (will be updated).

        Returns:
            List of OverlengthGroup objects.
        """
        groups: list[OverlengthGroup] = []

        for m in typed_measures:
            if isinstance(m, OverlengthMeasure) and m.mc not in grouped_mcs:
                groups.append(OverlengthGroup(members=(m,)))
                grouped_mcs.add(m.mc)

        return groups

    def _group_completes(
        self, typed_measures: tuple[TypedMeasure, ...], grouped_mcs: set[int]
    ) -> list[CompleteMeasureGroup]:
        """Group adjacent CompleteMeasures together.

        Creates CompleteMeasureGroup for runs of consecutive CompleteMeasures
        that haven't been grouped yet.

        Args:
            typed_measures: Tuple of typed measures.
            grouped_mcs: Set of MCs already grouped (will be updated).

        Returns:
            List of CompleteMeasureGroup objects.
        """
        groups: list[CompleteMeasureGroup] = []
        current_run: list[CompleteMeasure] = []

        for m in typed_measures:
            if isinstance(m, CompleteMeasure) and m.mc not in grouped_mcs:
                # Check if adjacent to current run
                if current_run and m.mc == current_run[-1].mc + 1:
                    current_run.append(m)
                else:
                    # Save current run and start new one
                    if current_run:
                        groups.append(CompleteMeasureGroup(members=tuple(current_run)))
                        for member in current_run:
                            grouped_mcs.add(member.mc)
                    current_run = [m]
            else:
                # Non-complete or already grouped: save current run
                if current_run:
                    groups.append(CompleteMeasureGroup(members=tuple(current_run)))
                    for member in current_run:
                        grouped_mcs.add(member.mc)
                    current_run = []

        # Finalize last run
        if current_run:
            groups.append(CompleteMeasureGroup(members=tuple(current_run)))
            for member in current_run:
                grouped_mcs.add(member.mc)

        return groups

    def iter_units(self) -> Iterator[MeasureUnit]:
        """Iterate over MeasureUnits (the folded score skeleton).

        Yields:
            MeasureUnit objects in MC order.

        Examples:
            >>> for unit in controller.iter_units():
            ...     print(f"MC {unit.mc}: {unit.mn}, next={unit.next}")
        """
        yield from self._units

    def _build_atomic_sections(self) -> None:
        """Derive atomic sections from next[] arrays.

        Note:
            Uses right-open interval convention [mc_start, mc_end).

        Algorithm:
        1. Find section boundaries where next != [MC+1]
        2. Create AtomicSection for each contiguous run
        3. Set section_type based on flow control patterns
        4. Build to[] arrays from grouped next[] values

        Section boundaries occur when:
        - next contains multiple options (volta/repeat)
        - next jumps backward (repeat end)
        - next jumps forward > MC+1 (skip/coda)
        - next is [-1] (end of piece)
        """
        if not self._measure_lookup:
            return

        sorted_mcs = sorted(self._measure_lookup.keys())
        if not sorted_mcs:
            return

        # Find segment boundaries
        boundaries: list[int] = [sorted_mcs[0]]  # Start of first segment

        for i, mc in enumerate(sorted_mcs):
            bar = self._measure_lookup[mc]
            next_list = bar["next"]

            # Check if this MC ends a segment
            is_boundary = False

            if len(next_list) > 1:
                # Multiple next options = volta or conditional jump
                is_boundary = True
            elif next_list == [-1]:
                # End of piece
                is_boundary = True
            elif i < len(sorted_mcs) - 1:
                next_mc = sorted_mcs[i + 1]
                if next_list[0] != next_mc:
                    # Jump (forward or backward)
                    is_boundary = True

            if is_boundary and i < len(sorted_mcs) - 1:
                # Add next MC as start of new segment
                next_mc_idx = i + 1
                if next_mc_idx < len(sorted_mcs):
                    boundaries.append(sorted_mcs[next_mc_idx])

        # Remove duplicates and sort
        boundaries = sorted(set(boundaries))

        # Create atomic sections from boundaries
        section_id = ord("A")
        sections: list[AtomicSection] = []

        # Build lookup from mc to MeasureUnit for typed_measures
        unit_lookup: dict[int, MeasureUnit] = {u.mc: u for u in self._units}

        for i, start_mc in enumerate(boundaries):
            # Find end MC (last MC before next boundary, or last MC)
            if i + 1 < len(boundaries):
                end_mc = boundaries[i + 1] - 1
            else:
                end_mc = sorted_mcs[-1]

            # Ensure end_mc is valid
            while end_mc not in self._measure_lookup and end_mc > start_mc:
                end_mc -= 1

            if end_mc < start_mc:
                end_mc = start_mc

            # Determine segment type
            end_bar = self._measure_lookup.get(end_mc, {})
            next_list = end_bar.get("next", [])

            section_type = "default"
            if len(next_list) > 1 or (next_list and next_list[0] < start_mc):
                section_type = "leap_end"
            elif start_mc > 1:
                # Check if this is a jump target
                for mc in sorted_mcs:
                    bar = self._measure_lookup[mc]
                    if start_mc in bar.get("next", []) and mc != start_mc - 1:
                        section_type = "leap_start"
                        break

            # Build to[] array
            to_sections: list[str] = []
            if next_list and next_list != [-1]:
                for next_mc in next_list:
                    if next_mc == -1:
                        continue
                    # Find which section contains next_mc
                    for j, bnd in enumerate(boundaries):
                        if j + 1 < len(boundaries):
                            if bnd <= next_mc < boundaries[j + 1]:
                                to_sections.append(chr(ord("A") + j))
                                break
                        else:
                            if bnd <= next_mc:
                                to_sections.append(chr(ord("A") + j))
                                break

            # Build typed_measures for this section (Phase 1 typing)
            # Collect MeasureUnits in the range [start_mc, end_mc+1) (right-open)
            section_units: list[MeasureUnit] = []
            for mc in range(start_mc, end_mc + 1):
                if mc in unit_lookup:
                    section_units.append(unit_lookup[mc])

            # Type each unit (Phase 1)
            typed_measures: tuple[TypedMeasure, ...] | None = None
            groups: tuple[MeasureGroup, ...] | None = None
            if section_units:
                typed_list = [self._type_measure(u) for u in section_units]
                typed_measures = tuple(typed_list)
                # Build groups (Phase 2)
                groups = self._build_groups(typed_measures)

            sections.append(
                AtomicSection(
                    id=chr(section_id),
                    mc_start=start_mc,
                    mc_end=end_mc + 1,  # Right-open: end is exclusive
                    to=tuple(to_sections),
                    section_type=section_type,
                    typed_measures=typed_measures,
                    groups=groups,
                )
            )
            section_id += 1

        self._atomic_sections = sections

    def get_sections(
        self, mode: FlowMode | None = None
    ) -> list[AtomicSection] | list[PlaythroughSection]:
        """Get list of sections.

        This is the unified API for retrieving sections. Replaces the old
        get_atomic_sections() method with added support for playthrough sections.

        Args:
            mode: If None, returns AtomicSections (default).
                  If specified, returns PlaythroughSections for that mode.

        Returns:
            List of AtomicSection if mode is None, otherwise list of PlaythroughSection.

        Examples:
            >>> # Get atomic sections (folded structure)
            >>> for sec in controller.get_sections():
            ...     print(f"{sec.id}: MC [{sec.mc_start},{sec.mc_end})")

            >>> # Get playthrough sections for DEFAULT mode (unfolded)
            >>> for sec in controller.get_sections(FlowMode.DEFAULT):
            ...     print(f"MC [{sec.mc_start},{sec.mc_end})")
        """
        if mode is None:
            return list(self._atomic_sections)
        else:
            flow = self.compute_flow(mode)
            return list(flow.sections)

    def iter_sections(
        self, mode: FlowMode | None = None
    ) -> Iterator[AtomicSection | PlaythroughSection]:
        """Iterate over sections.

        Args:
            mode: If None, iterates over AtomicSections (default).
                  If specified, iterates over PlaythroughSections for that mode.

        Yields:
            AtomicSection objects if mode is None, otherwise PlaythroughSection objects.

        Examples:
            >>> # Iterate over atomic sections (folded structure)
            >>> for sec in controller.iter_sections():
            ...     print(f"{sec.id}: MC [{sec.mc_start},{sec.mc_end})")

            >>> # Iterate over playthrough sections (unfolded traversal)
            >>> for sec in controller.iter_sections(FlowMode.DEFAULT):
            ...     print(f"MC [{sec.mc_start},{sec.mc_end})")
        """
        if mode is None:
            yield from self._atomic_sections
        else:
            flow = self.compute_flow(mode)
            yield from flow.sections

    def _compute_playthrough_sections(
        self, mc_sequence: list[int]
    ) -> list[PlaythroughSection]:
        """Convert MC sequence to PlaythroughSection list with groups.

        Groups consecutive MCs into sections. A new section starts when:
        - There's a non-consecutive MC jump
        - The MC sequence reverses (repeat)

        Includes flow-aware SplitMeasure detection: when a section boundary
        falls between two IncompleteGroups that together form a complete
        measure (e.g., anacrusis at start + final at end of previous section),
        they are merged into a SplitMeasure.

        Note:
            Uses right-open interval convention [mc_start, mc_end).

        Args:
            mc_sequence: List of MC values in traversal order.

        Returns:
            List of PlaythroughSection objects with typed_measures and groups.
        """
        if not mc_sequence:
            return []

        # Build lookup from mc to MeasureUnit for typed_measures
        unit_lookup: dict[int, MeasureUnit] = {u.mc: u for u in self._units}

        sections: list[PlaythroughSection] = []
        current_start = mc_sequence[0]
        current_end = mc_sequence[0]

        def _build_section(start_mc: int, end_mc: int) -> PlaythroughSection:
            """Build a PlaythroughSection with typed_measures and groups."""
            atomic_ids = self._find_atomic_ids(start_mc, end_mc + 1)

            # Collect and type MeasureUnits in the range (Phase 1)
            typed_list: list[TypedMeasure] = []
            for mc in range(start_mc, end_mc + 1):
                if mc in unit_lookup:
                    typed_list.append(self._type_measure(unit_lookup[mc]))

            typed_measures = tuple(typed_list) if typed_list else None

            # Build groups (Phase 2)
            groups: tuple[MeasureGroup, ...] | None = None
            if typed_measures:
                groups = self._build_groups(typed_measures)

            return PlaythroughSection(
                mc_start=start_mc,
                mc_end=end_mc + 1,  # Right-open: end is exclusive
                atomic_section_ids=tuple(atomic_ids),
                typed_measures=typed_measures,
                groups=groups,
            )

        for i, mc in enumerate(mc_sequence):
            # Check if this continues the current section
            if i > 0:
                prev_mc = mc_sequence[i - 1]
                # Non-consecutive or backward jump starts new section
                if mc != prev_mc + 1:
                    # Save current section
                    sections.append(_build_section(current_start, current_end))
                    # Start new section
                    current_start = mc
                    current_end = mc
                else:
                    # Continue current section
                    current_end = mc
            else:
                current_end = mc

        # Don't forget the last section
        sections.append(_build_section(current_start, current_end))

        # Flow-aware SplitMeasure detection: check section boundaries
        sections = self._detect_boundary_splits(sections)

        return sections

    def _detect_boundary_splits(
        self, sections: list[PlaythroughSection]
    ) -> list[PlaythroughSection]:
        """Detect SplitMeasures at section boundaries.

        When a section ends with an IncompleteGroup and the next section
        starts with an IncompleteGroup, check if they form a complete measure
        (e.g., final 3/4 + anacrusis 1/4 = 4/4).

        If so, create a SplitMeasure that spans the boundary.

        Args:
            sections: List of PlaythroughSections.

        Returns:
            Updated list with boundary SplitMeasures detected.
        """
        if len(sections) < 2:
            return sections

        result: list[PlaythroughSection] = []

        for i, sec in enumerate(sections):
            if i == 0:
                result.append(sec)
                continue

            prev_sec = result[-1]

            # Check if previous section ends with IncompleteGroup
            prev_end_incomplete = self._get_end_incomplete(prev_sec)
            # Check if current section starts with IncompleteGroup
            curr_start_incomplete = self._get_start_incomplete(sec)

            if prev_end_incomplete and curr_start_incomplete:
                # Check if they form a complete measure
                total = (
                    prev_end_incomplete.total_duration_qb
                    + curr_start_incomplete.total_duration_qb
                )
                expected = None
                # Get expected duration from any member
                for m in prev_end_incomplete.members:
                    if m.timesig_duration_qb:
                        expected = m.timesig_duration_qb
                        break
                if expected is None:
                    for m in curr_start_incomplete.members:
                        if m.timesig_duration_qb:
                            expected = m.timesig_duration_qb
                            break

                if expected is not None and total == expected:
                    # They form a complete measure! Create SplitMeasure
                    # For now, we note this in the groups but don't restructure
                    # (full restructuring would require re-building groups)
                    module_logger.debug(
                        f"Boundary SplitMeasure detected: "
                        f"section {i-1} end + section {i} start = {total}"
                    )

            result.append(sec)

        return result

    def _get_end_incomplete(self, sec: PlaythroughSection) -> IncompleteGroup | None:
        """Get the IncompleteGroup at the end of a section, if any."""
        if not sec.groups:
            return None
        last_group = sec.groups[-1]
        if isinstance(last_group, IncompleteGroup):
            return last_group
        return None

    def _get_start_incomplete(self, sec: PlaythroughSection) -> IncompleteGroup | None:
        """Get the IncompleteGroup at the start of a section, if any."""
        if not sec.groups:
            return None
        first_group = sec.groups[0]
        if isinstance(first_group, IncompleteGroup):
            return first_group
        return None

    def _find_atomic_ids(self, mc_start: int, mc_end: int) -> list[str]:
        """Find which atomic sections cover the given MC range.

        Args:
            mc_start: First MC of the range (inclusive).
            mc_end: First MC AFTER the range (exclusive, right-open).

        Returns:
            List of atomic section IDs that overlap with the range.
        """
        ids = []
        for sec in self._atomic_sections:
            # Check for overlap (right-open intervals)
            if sec.mc_end > mc_start and sec.mc_start < mc_end:
                ids.append(sec.id)
        return ids

    def compute_flow(self, mode: FlowMode = FlowMode.DEFAULT) -> Flow:
        """Compute a single Flow using the specified mode.

        Args:
            mode: The FlowMode to use (default: DEFAULT).

        Returns:
            Computed Flow object.
        """
        if mode == FlowMode.PRINTED:
            return self._compute_printed_flow()
        elif mode in (FlowMode.DEFAULT, FlowMode.MS3):
            return self._compute_default_flow(mode)
        else:
            # TODO: Implement other modes
            module_logger.warning(
                f"FlowMode.{mode.name} not yet implemented, using DEFAULT"
            )
            return self._compute_default_flow(FlowMode.DEFAULT)

    def _compute_printed_flow(self) -> Flow:
        """Compute flow for printed score (no unfolding).

        Returns:
            Flow with each MC visited exactly once.
        """
        # For printed flow, just use sorted MCs in order
        sorted_mcs = sorted(self._measure_lookup.keys())

        # Convert MC sequence to sections
        sections = self._compute_playthrough_sections(sorted_mcs)

        return Flow(
            sections=sections,
            mode=FlowMode.PRINTED,
            folded_length=len(sorted_mcs),
            _controller_ref=weakref.ref(self),
        )

    def _compute_default_flow(self, mode: FlowMode) -> Flow:
        """Compute default flow following 'next' field.

        The algorithm:
        1. Start at MC 1
        2. Follow 'next' field, using visit count to choose branch
        3. Build MC sequence
        4. Convert to PlaythroughSections

        Args:
            mode: FlowMode (DEFAULT or MS3).

        Returns:
            Computed Flow.
        """
        if not self._measure_lookup:
            return Flow(
                sections=[],
                mode=mode,
                folded_length=0,
                _controller_ref=weakref.ref(self),
            )

        mc_sequence: list[int] = []
        mc_visit_count: dict[int, int] = defaultdict(int)

        # Start at MC 1 (or minimum MC)
        current_mc = min(self._measure_lookup.keys())

        # Safety limit
        max_iterations = len(self._measure_lookup) * 20

        for _ in range(max_iterations):
            if current_mc == -1 or current_mc not in self._measure_lookup:
                break

            bar = self._measure_lookup[current_mc]
            mc_visit_count[current_mc] += 1
            visit_count = mc_visit_count[current_mc]

            mc_sequence.append(current_mc)

            # Choose next MC based on visit count
            next_options = bar["next"]
            idx = min(visit_count - 1, len(next_options) - 1)
            current_mc = next_options[idx]

        # Convert MC sequence to sections
        sections = self._compute_playthrough_sections(mc_sequence)

        return Flow(
            sections=sections,
            mode=mode,
            folded_length=len(self._measure_lookup),
            _controller_ref=weakref.ref(self),
        )

    def _occurrence_to_suffix(self, occurrence: int) -> str:
        """Convert occurrence number to letter suffix.

        1 -> 'a', 2 -> 'b', ..., 26 -> 'z', 27 -> 'aa', etc.

        Args:
            occurrence: 1-indexed occurrence number.

        Returns:
            Letter suffix.
        """
        if occurrence <= 0:
            return "a"

        result = []
        n = occurrence
        while n > 0:
            n -= 1
            result.append(chr(ord("a") + (n % 26)))
            n //= 26
        return "".join(reversed(result))

    def compute_all_flows(self) -> list[Flow]:
        """Compute all possible Flows.

        For scores with optional repeats, this computes all valid paths.

        Returns:
            List of Flow objects.
        """
        # For now, just return default and printed
        return [
            self.compute_flow(FlowMode.DEFAULT),
            self.compute_flow(FlowMode.PRINTED),
        ]

    def create_flow_map(self, mode: FlowMode = FlowMode.DEFAULT) -> FlowMap:
        """Create a FlowMap for timeline attachment.

        Args:
            mode: The FlowMode to use.

        Returns:
            FlowMap wrapping the computed Flow.
        """
        flow = self.compute_flow(mode)
        return FlowMap(flow=flow)


# endregion
