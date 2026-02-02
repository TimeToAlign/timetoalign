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
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING, Any

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

# region AtomicSegment


@dataclass(frozen=True)
class AtomicSegment:
    """Smallest indivisible traversal unit (partitura's segment model).

    Atomic segments are derived from:
    - partitura's add_segments()/get_segments() for MusicXML/MEI
    - next[] array analysis for TSV/MeasureMap

    Segment IDs (A, B, C, ...) form a canonical reference for mapping all
    flow modes. The partitura_minimal flow mode defines these canonical segments.

    Attributes:
        id: Letter identifier (A, B, C...) from partitura or generated.
        mc_start: First MC of this segment (inclusive).
        mc_end: Last MC of this segment (inclusive).
        to: List of possible next segment IDs.
        await_to: Destinations available after a leap (D.C./D.S. patterns).
        segment_type: "default", "leap_end", or "leap_start".

    Examples:
        >>> seg = AtomicSegment(
        ...     id="A",
        ...     mc_start=1,
        ...     mc_end=4,
        ...     to=("A", "B"),
        ...     segment_type="leap_end",
        ... )
        >>> seg.mc_range
        (1, 4)
        >>> seg.mc_count
        4
    """

    id: str
    mc_start: int
    mc_end: int
    to: tuple[str, ...] = ()
    await_to: tuple[str, ...] = ()
    segment_type: str = "default"  # "default" | "leap_end" | "leap_start"

    def __post_init__(self) -> None:
        """Validate segment configuration."""
        if self.mc_end < self.mc_start:
            raise ValueError(
                f"AtomicSegment '{self.id}': mc_end ({self.mc_end}) "
                f"cannot be before mc_start ({self.mc_start})"
            )
        if self.segment_type not in ("default", "leap_end", "leap_start"):
            raise ValueError(
                f"AtomicSegment '{self.id}': invalid segment_type '{self.segment_type}'"
            )

    @property
    def mc_range(self) -> tuple[int, int]:
        """Return (mc_start, mc_end) tuple."""
        return (self.mc_start, self.mc_end)

    @property
    def mc_count(self) -> int:
        """Number of MCs in this segment (inclusive count)."""
        return self.mc_end - self.mc_start + 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "mc_start": self.mc_start,
            "mc_end": self.mc_end,
            "to": list(self.to),
            "await_to": list(self.await_to),
            "segment_type": self.segment_type,
        }

    def __repr__(self) -> str:
        return f"AtomicSegment({self.id}: MC {self.mc_start}-{self.mc_end}, {self.segment_type})"


# endregion

# region PlaythroughSegment


@dataclass(frozen=True)
class PlaythroughSegment:
    """A contiguous group of atomic segments in a specific traversal.

    This is what gets written to .flow.csv and compared via is_equivalent().
    Each PlaythroughSegment represents a contiguous run of MCs in the unfolded
    sequence.

    Attributes:
        mc_start: First MC of this playthrough segment (inclusive).
        mc_end: Last MC of this playthrough segment (inclusive).
        atomic_segment_ids: Which atomic segments this covers.

    Examples:
        >>> seg = PlaythroughSegment(mc_start=1, mc_end=8, atomic_segment_ids=("A", "B"))
        >>> seg.mc_range
        (1, 8)
        >>> seg.mc_count
        8
    """

    mc_start: int
    mc_end: int
    atomic_segment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate segment configuration."""
        if self.mc_end < self.mc_start:
            raise ValueError(
                f"PlaythroughSegment: mc_end ({self.mc_end}) "
                f"cannot be before mc_start ({self.mc_start})"
            )

    @property
    def mc_range(self) -> tuple[int, int]:
        """Return (mc_start, mc_end) tuple."""
        return (self.mc_start, self.mc_end)

    @property
    def mc_count(self) -> int:
        """Number of MCs in this segment (inclusive count)."""
        return self.mc_end - self.mc_start + 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mc_start": self.mc_start,
            "mc_end": self.mc_end,
            "atomic_segments": ";".join(self.atomic_segment_ids),
        }

    def to_mc_sequence(self) -> list[int]:
        """Return list of all MCs in this segment.

        Returns:
            List of MC values from mc_start to mc_end (inclusive).
        """
        return list(range(self.mc_start, self.mc_end + 1))

    def __repr__(self) -> str:
        segs = ";".join(self.atomic_segment_ids) if self.atomic_segment_ids else "?"
        return f"PlaythroughSegment(MC {self.mc_start}-{self.mc_end} [{segs}])"


# endregion

# region FlowStep


@dataclass(frozen=True)
class FlowStep:
    """A single step in a Flow sequence.

    Each FlowStep represents one measure visitation in the unfolded sequence.
    The fields directly correspond to the unfolded TSV columns from ms3.

    Attributes:
        mc: Original Measure Count (may repeat in sequence).
        mn: Original Measure Number label (may repeat).
        mc_playthrough: Monotonic index in unfolded sequence (1-indexed).
        mn_playthrough: MN with occurrence suffix (e.g., "19a", "19b").
        quarterbeats: Cumulative position in unfolded time.
        duration_qb: Duration of this measure in quarter beats.
        visit_count: Which visit to this MC (1-indexed).
    """

    mc: int
    mn: str
    mc_playthrough: int
    mn_playthrough: str
    quarterbeats: Fraction
    duration_qb: Fraction
    visit_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame creation."""
        return {
            "mc": self.mc,
            "mn": self.mn,
            "mc_playthrough": self.mc_playthrough,
            "mn_playthrough": self.mn_playthrough,
            "quarterbeats": self.quarterbeats,
            "duration_qb": self.duration_qb,
            "visit_count": self.visit_count,
        }


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

    The Flow class supports two representations:
    - **Segment-based** (new): Uses `segments` (list of PlaythroughSegment)
    - **Step-based** (legacy): Uses `steps` (list of FlowStep)

    Segment-based flows are used for .flow.csv serialization and is_equivalent()
    comparison. Step-based flows provide detailed per-MC information.

    Attributes:
        steps: The sequence of FlowStep objects (legacy, detailed per-MC).
        segments: The sequence of PlaythroughSegment objects (new, grouped).
        mode: The FlowMode used to compute this flow.
        folded_length: Number of unique MCs (measures in printed score).
        source_metadata: Optional metadata from the source MeasureData.
    """

    steps: list[FlowStep] = field(default_factory=list)
    mode: FlowMode = FlowMode.DEFAULT
    folded_length: int = 0
    source_metadata: dict[str, Any] = field(default_factory=dict)
    segments: list[PlaythroughSegment] = field(default_factory=list)

    # === Class Methods (Constructors) ===

    @classmethod
    def from_segments(
        cls,
        segments: list[PlaythroughSegment],
        mode: FlowMode,
        folded_length: int | None = None,
    ) -> "Flow":
        """Create a Flow from PlaythroughSegments.

        Args:
            segments: List of PlaythroughSegment objects.
            mode: The FlowMode for this flow.
            folded_length: Number of unique MCs. If None, computed from segments.

        Returns:
            New Flow instance with segments populated.
        """
        if folded_length is None:
            # Estimate from segment ranges (may not be accurate for repeated sections)
            all_mcs = set()
            for seg in segments:
                all_mcs.update(range(seg.mc_start, seg.mc_end + 1))
            folded_length = len(all_mcs)

        return cls(
            steps=[],
            segments=segments,
            mode=mode,
            folded_length=folded_length,
        )

    @classmethod
    def from_records(cls, records: list[dict], mode: FlowMode) -> "Flow":
        """Create Flow from list of dicts with mc_start, mc_end, atomic_segments.

        Args:
            records: List of dicts, each with keys:
                - mc_start: int
                - mc_end: int
                - atomic_segments: str (semicolon-separated, e.g., "A;B")
            mode: The FlowMode for this flow.

        Returns:
            New Flow instance with segments populated.
        """
        segments = []
        for rec in records:
            atomic_ids_str = rec.get("atomic_segments", "")
            atomic_ids = tuple(
                s.strip() for s in atomic_ids_str.split(";") if s.strip()
            )
            segments.append(
                PlaythroughSegment(
                    mc_start=int(rec["mc_start"]),
                    mc_end=int(rec["mc_end"]),
                    atomic_segment_ids=atomic_ids,
                )
            )
        return cls.from_segments(segments, mode)

    @classmethod
    def from_dataframe(cls, df: "pd.DataFrame", mode: FlowMode) -> "Flow":
        """Create Flow from DataFrame with mc_start, mc_end, atomic_segments columns.

        Args:
            df: DataFrame with columns: mc_start, mc_end, atomic_segments.
            mode: The FlowMode for this flow.

        Returns:
            New Flow instance with segments populated.
        """
        records = df.to_dict("records")
        return cls.from_records(records, mode)

    @classmethod
    def from_csv(cls, path: "Path | str", mode: FlowMode) -> "Flow":
        """Load Flow for specific mode from .flow.csv file.

        Filters CSV to rows matching the given flow_mode.

        Args:
            path: Path to the .flow.csv file.
            mode: The FlowMode to load.

        Returns:
            New Flow instance with segments populated.

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
        """Export as list of dicts (segment-based).

        Returns:
            List of dicts with keys: mc_start, mc_end, atomic_segments.
        """
        return [seg.to_dict() for seg in self.segments]

    def to_segment_dataframe(self) -> "pd.DataFrame":
        """Export as DataFrame (segment-based).

        Returns:
            DataFrame with columns: mc_start, mc_end, atomic_segments.
        """
        import pandas as pd

        return pd.DataFrame(self.to_records())

    def to_csv_rows(self, source_file: str, software_version: str) -> list[dict]:
        """Export as .flow.csv format rows.

        Returns list of dicts with keys:
            flow_mode, source_file, software_version, mc_start, mc_end, atomic_segments

        Args:
            source_file: The file that was parsed to produce this flow.
            software_version: Software name and version for reproducibility.

        Returns:
            List of dicts ready for CSV writing.
        """
        rows = []
        for seg in self.segments:
            rows.append(
                {
                    "flow_mode": self.mode.value,
                    "source_file": source_file,
                    "software_version": software_version,
                    "mc_start": seg.mc_start,
                    "mc_end": seg.mc_end,
                    "atomic_segments": ";".join(seg.atomic_segment_ids),
                }
            )
        return rows

    # === Comparison Methods ===

    def is_equivalent(self, other: "Flow") -> bool:
        """Compare by zipped (mc_start, mc_end) ranges.

        Two flows are equivalent if they have the same number of segments
        and each corresponding segment has matching mc_start and mc_end.

        Note: atomic_segment_ids are NOT compared - only MC ranges matter.

        Args:
            other: Another Flow to compare against.

        Returns:
            True if flows are equivalent, False otherwise.
        """
        if len(self.segments) != len(other.segments):
            return False
        return all(
            (a.mc_start, a.mc_end) == (b.mc_start, b.mc_end)
            for a, b in zip(self.segments, other.segments)
        )

    # === Properties (Backward Compatible) ===

    @property
    def unfolded_length(self) -> int:
        """Number of measure visitations in the unfolded sequence."""
        if self.steps:
            return len(self.steps)
        # Compute from segments
        return sum(seg.mc_count for seg in self.segments)

    @property
    def total_quarterbeats(self) -> Fraction:
        """Total duration of the unfolded sequence in quarter beats."""
        if not self.steps:
            return Fraction(0)
        last = self.steps[-1]
        return last.quarterbeats + last.duration_qb

    @property
    def has_repeats(self) -> bool:
        """Whether the flow contains repeated measures."""
        return self.unfolded_length > self.folded_length

    # === Convenience Methods ===

    def to_mc_sequence(self) -> list[int]:
        """Return the sequence of MCs in traversal order.

        Returns:
            List of MC values in the order they are visited.
        """
        if self.steps:
            return [step.mc for step in self.steps]
        # Compute from segments
        result = []
        for seg in self.segments:
            result.extend(range(seg.mc_start, seg.mc_end + 1))
        return result

    def to_dataframe(self) -> "pd.DataFrame":
        """Convert to pandas DataFrame matching unfolded TSV format.

        Returns:
            DataFrame with columns: mc, mn, mc_playthrough, mn_playthrough,
            quarterbeats, duration_qb, visit_count.
        """
        import pandas as pd

        rows = [step.to_dict() for step in self.steps]
        return pd.DataFrame(rows)

    def __repr__(self) -> str:
        ratio = self.unfolded_length / self.folded_length if self.folded_length else 0
        seg_info = f", {len(self.segments)} segments" if self.segments else ""
        return (
            f"Flow({self.mode.value}: {self.folded_length} folded -> "
            f"{self.unfolded_length} unfolded, ratio={ratio:.2f}{seg_info})"
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
        ...     print(f"{mode.value}: {len(flow.segments)} segments")
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
        """
        qb = Fraction(qb) if not isinstance(qb, Fraction) else qb
        results: list[Fraction] = []

        # Find all steps that contain this folded coordinate
        # We need to look at the original measure boundaries
        # For now, simplified: find steps by MC that would contain qb
        # TODO: Implement proper coordinate-to-MC lookup
        for step in self.flow.steps:
            # step_end = step.quarterbeats + step.duration_qb
            # Check if qb falls within this step's range in unfolded time
            # This is a placeholder - proper implementation needs folded qb mapping
            results.append(step.quarterbeats)

        return results

    def unfolded_to_folded(self, qb: Fraction | float) -> Fraction:
        """Convert an unfolded coordinate to folded coordinate.

        Args:
            qb: Quarter beat position in unfolded timeline.

        Returns:
            Quarter beat position in folded timeline.

        Raises:
            ValueError: If coordinate is outside the flow range.
        """
        qb = Fraction(qb) if not isinstance(qb, Fraction) else qb

        for step in self.flow.steps:
            step_end = step.quarterbeats + step.duration_qb
            if step.quarterbeats <= qb < step_end:
                # Found the step - compute offset within step
                # offset = qb - step.quarterbeats
                # TODO: Need original folded qb for this MC
                # For now, return the unfolded position
                return qb

        raise ValueError(f"Coordinate {qb} outside flow range")

    def __repr__(self) -> str:
        return f"FlowMap({self.flow})"


# endregion

# region FlowController


class FlowController:
    """Compute Flow paths from MeasureData or atomic segments.

    The FlowController operates at the segment level:
    1. Derives atomic segments from next[] arrays OR accepts from partitura
    2. Uses flow control markers + volta attributes to execute flow logic
    3. Groups atomic segments into playthrough segments per FlowMode

    The algorithm follows the 'next' field in measure data, using visit
    counts to choose which branch to take at repeat points. This matches
    the ms3 unfolding algorithm.

    Attributes:
        measures: The source MeasureData.

    Examples:
        >>> controller = FlowController(measure_data)
        >>> flow = controller.compute_flow()
        >>> print(f"Unfolded: {flow.unfolded_length} measures")

        >>> # Get segment-based flow for .flow.csv comparison
        >>> flow = controller.compute_flow()
        >>> for seg in flow.segments:
        ...     print(f"MC {seg.mc_start}-{seg.mc_end}")

        >>> # Get atomic segments for debugging
        >>> for seg in controller.get_atomic_segments():
        ...     print(f"{seg.id}: MC {seg.mc_start}-{seg.mc_end}")
    """

    def __init__(self, measures: "MeasureData") -> None:
        """Initialize FlowController from MeasureData.

        Args:
            measures: MeasureData containing flow control fields.
        """
        self._measures = measures
        self._measure_lookup: dict[int, dict[str, Any]] = {}
        self._atomic_segments: list[AtomicSegment] = []
        self._build_lookup()
        self._build_atomic_segments()

    @classmethod
    def from_atomic_segments(
        cls,
        segments: list[AtomicSegment],
        measures: "MeasureData | None" = None,
    ) -> "FlowController":
        """Initialize directly from atomic segments (e.g., from partitura).

        Args:
            segments: List of AtomicSegment objects.
            measures: Optional MeasureData for detailed step computation.

        Returns:
            FlowController with pre-built atomic segments.
        """
        # Create instance without calling __init__
        instance = object.__new__(cls)
        instance._measures = measures
        instance._measure_lookup = {}
        instance._atomic_segments = list(segments)

        # Build lookup if measures provided
        if measures is not None:
            instance._build_lookup()

        return instance

    def _build_lookup(self) -> None:
        """Build MC -> measure dict lookup from MeasureData."""
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
            }

    def _build_atomic_segments(self) -> None:
        """Derive atomic segments from next[] arrays.

        Algorithm:
        1. Find segment boundaries where next != [MC+1]
        2. Create AtomicSegment for each contiguous run
        3. Set segment_type based on flow control patterns
        4. Build to[] arrays from grouped next[] values

        Segment boundaries occur when:
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

        # Create atomic segments from boundaries
        segment_id = ord("A")
        segments: list[AtomicSegment] = []

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

            segment_type = "default"
            if len(next_list) > 1 or (next_list and next_list[0] < start_mc):
                segment_type = "leap_end"
            elif start_mc > 1:
                # Check if this is a jump target
                for mc in sorted_mcs:
                    bar = self._measure_lookup[mc]
                    if start_mc in bar.get("next", []) and mc != start_mc - 1:
                        segment_type = "leap_start"
                        break

            # Build to[] array
            to_segments: list[str] = []
            if next_list and next_list != [-1]:
                for next_mc in next_list:
                    if next_mc == -1:
                        continue
                    # Find which segment contains next_mc
                    for j, bnd in enumerate(boundaries):
                        if j + 1 < len(boundaries):
                            if bnd <= next_mc < boundaries[j + 1]:
                                to_segments.append(chr(ord("A") + j))
                                break
                        else:
                            if bnd <= next_mc:
                                to_segments.append(chr(ord("A") + j))
                                break

            segments.append(
                AtomicSegment(
                    id=chr(segment_id),
                    mc_start=start_mc,
                    mc_end=end_mc,
                    to=tuple(to_segments),
                    segment_type=segment_type,
                )
            )
            segment_id += 1

        self._atomic_segments = segments

    def get_atomic_segments(self) -> list[AtomicSegment]:
        """Return the atomic segments (for debugging/testing).

        Returns:
            Copy of the list of AtomicSegment objects.
        """
        return list(self._atomic_segments)

    def _steps_to_segments(self, steps: list[FlowStep]) -> list[PlaythroughSegment]:
        """Convert FlowStep list to PlaythroughSegment list.

        Groups consecutive MCs into segments. A new segment starts when:
        - There's a non-consecutive MC jump
        - The MC sequence reverses (repeat)

        Args:
            steps: List of FlowStep objects in traversal order.

        Returns:
            List of PlaythroughSegment objects.
        """
        if not steps:
            return []

        segments: list[PlaythroughSegment] = []
        current_start = steps[0].mc
        current_end = steps[0].mc
        # current_atomic_ids: list[str] = []

        for i, step in enumerate(steps):
            mc = step.mc

            # Check if this continues the current segment
            if i > 0:
                prev_mc = steps[i - 1].mc
                # Non-consecutive or backward jump starts new segment
                if mc != prev_mc + 1:
                    # Save current segment
                    atomic_ids = self._find_atomic_ids(current_start, current_end)
                    segments.append(
                        PlaythroughSegment(
                            mc_start=current_start,
                            mc_end=current_end,
                            atomic_segment_ids=tuple(atomic_ids),
                        )
                    )
                    # Start new segment
                    current_start = mc
                    current_end = mc
                    # current_atomic_ids = []
                else:
                    # Continue current segment
                    current_end = mc
            else:
                current_end = mc

        # Don't forget the last segment
        atomic_ids = self._find_atomic_ids(current_start, current_end)
        segments.append(
            PlaythroughSegment(
                mc_start=current_start,
                mc_end=current_end,
                atomic_segment_ids=tuple(atomic_ids),
            )
        )

        return segments

    def _find_atomic_ids(self, mc_start: int, mc_end: int) -> list[str]:
        """Find which atomic segments cover the given MC range.

        Args:
            mc_start: First MC of the range (inclusive).
            mc_end: Last MC of the range (inclusive).

        Returns:
            List of atomic segment IDs that overlap with the range.
        """
        ids = []
        for seg in self._atomic_segments:
            # Check for overlap
            if seg.mc_end >= mc_start and seg.mc_start <= mc_end:
                ids.append(seg.id)
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
        steps: list[FlowStep] = []
        mn_occurrence: dict[str, int] = defaultdict(int)
        cumulative_qb = Fraction(0)

        # Sort MCs
        sorted_mcs = sorted(self._measure_lookup.keys())

        for i, mc in enumerate(sorted_mcs):
            bar = self._measure_lookup[mc]
            mn = bar["mn"]
            duration = bar["duration_qb"]

            # Track MN occurrence for suffix
            mn_occurrence[mn] += 1
            suffix = self._occurrence_to_suffix(mn_occurrence[mn])

            step = FlowStep(
                mc=mc,
                mn=mn,
                mc_playthrough=i + 1,
                mn_playthrough=f"{mn}{suffix}",
                quarterbeats=cumulative_qb,
                duration_qb=duration,
                visit_count=1,
            )
            steps.append(step)
            cumulative_qb += duration

        # Convert steps to segments
        segments = self._steps_to_segments(steps)

        return Flow(
            steps=steps,
            segments=segments,
            mode=FlowMode.PRINTED,
            folded_length=len(sorted_mcs),
        )

    def _compute_default_flow(self, mode: FlowMode) -> Flow:
        """Compute default flow following 'next' field.

        The algorithm:
        1. Start at MC 1
        2. Follow 'next' field, using visit count to choose branch
        3. Track MN occurrences for mn_playthrough suffix
        4. Compute cumulative quarterbeats

        Args:
            mode: FlowMode (DEFAULT or MS3).

        Returns:
            Computed Flow.
        """
        if not self._measure_lookup:
            return Flow(steps=[], mode=mode, folded_length=0)

        steps: list[FlowStep] = []
        mc_visit_count: dict[int, int] = defaultdict(int)
        mn_occurrence: dict[str, int] = defaultdict(int)
        cumulative_qb = Fraction(0)

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

            mn = bar["mn"]
            duration = bar["duration_qb"]

            # Track MN occurrence for suffix
            mn_occurrence[mn] += 1
            suffix = self._occurrence_to_suffix(mn_occurrence[mn])

            step = FlowStep(
                mc=current_mc,
                mn=mn,
                mc_playthrough=len(steps) + 1,
                mn_playthrough=f"{mn}{suffix}",
                quarterbeats=cumulative_qb,
                duration_qb=duration,
                visit_count=visit_count,
            )
            steps.append(step)
            cumulative_qb += duration

            # Choose next MC based on visit count
            next_options = bar["next"]
            idx = min(visit_count - 1, len(next_options) - 1)
            current_mc = next_options[idx]

        # Convert steps to segments
        segments = self._steps_to_segments(steps)

        return Flow(
            steps=steps,
            segments=segments,
            mode=mode,
            folded_length=len(self._measure_lookup),
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
