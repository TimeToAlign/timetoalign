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
    repeats, jumps, and voltas. It is computed by FlowController from
    MeasureData.

    Attributes:
        steps: The sequence of FlowStep objects.
        mode: The FlowMode used to compute this flow.
        folded_length: Number of unique MCs (measures in printed score).
        source_metadata: Optional metadata from the source MeasureData.
    """

    steps: list[FlowStep]
    mode: FlowMode
    folded_length: int
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def unfolded_length(self) -> int:
        """Number of measure visitations in the unfolded sequence."""
        return len(self.steps)

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

    def to_mc_sequence(self) -> list[int]:
        """Return the sequence of MCs in traversal order.

        Returns:
            List of MC values in the order they are visited.
        """
        return [step.mc for step in self.steps]

    def to_dataframe(self) -> pd.DataFrame:
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
        return (
            f"Flow({self.mode.value}: {self.folded_length} folded -> "
            f"{self.unfolded_length} unfolded, ratio={ratio:.2f})"
        )


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
    """Compute Flow paths from MeasureData.

    The FlowController analyzes flow control data (repeats, jumps, voltas)
    and computes all possible Flows through the score.

    The algorithm follows the 'next' field in measure data, using visit
    counts to choose which branch to take at repeat points. This matches
    the ms3 unfolding algorithm.

    Attributes:
        measures: The source MeasureData.

    Examples:
        >>> controller = FlowController(measure_data)
        >>> flow = controller.compute_flow()
        >>> print(f"Unfolded: {flow.unfolded_length} measures")

        >>> # Get DataFrame matching ms3 unfolded format
        >>> df = flow.to_dataframe()
    """

    def __init__(self, measures: MeasureData) -> None:
        """Initialize FlowController.

        Args:
            measures: MeasureData containing flow control fields.
        """
        self._measures = measures
        self._measure_lookup: dict[int, dict[str, Any]] = {}
        self._build_lookup()

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

        return Flow(
            steps=steps,
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

        return Flow(
            steps=steps,
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
