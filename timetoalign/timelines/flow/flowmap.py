"""Map coordinates between folded and unfolded flows."""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from .sections import Flow, _coerce_intervals


@dataclass
class FlowMapSection:
    """A section mapping in a FlowMap.

    Represents one contiguous section that maps from a source coordinate range
    to a target coordinate range. Used internally by FlowMap for coordinate
    transformation.

    In the context of flow control:
    - Source coordinates: The "folded" timeline (with repeats/jumps compressed)
    - Target coordinates: The "unfolded" timeline (linear playthrough order)

    Attributes:
        source_start: Start coordinate in source timeline (inclusive).
        source_end: End coordinate in source timeline (exclusive).
        target_start: Start coordinate in target timeline.
    """

    source_start: Fraction
    source_end: Fraction
    target_start: Fraction

    @property
    def duration(self) -> Fraction:
        """Duration of this section."""
        return self.source_end - self.source_start

    @property
    def target_end(self) -> Fraction:
        """End coordinate in target timeline."""
        return self.target_start + self.duration


class FlowMap:
    """Coordinate transformation map for flow control.

    A FlowMap enables bidirectional coordinate conversion between a source
    timeline (with flow control) and a target (linearized) timeline:

    - Source -> Target conversion (1:N, since repeats duplicate coordinates)
    - Target -> Source lookup (N:1, always unique)

    The single positional argument, *source*, is polymorphic:

    - ``None`` — an empty map (no sections). Used by internal construction
      such as :meth:`inverse`, which fills the section tables afterwards.
    - a :class:`Flow` — sections are derived from the flow's measure-count
      ranges (integer MC space); *id* defaults to the flow's mode value.
    - a single interval-like descriptor **or** an iterable of them — sections
      are built directly from the resulting ``(start, end)`` ranges with a
      cumulative target position, so the played spans concatenate in the
      target axis and any gaps between them map to nothing. *id* defaults to
      ``"default"``. Accepted descriptors are region names (resolved through
      *resolve*), ``Region`` objects, ``(start, end)`` coordinate pairs,
      ``Timeline`` objects, and interval events — see
      :func:`~timetoalign.timelines.flow.sections._coerce_intervals`.

    FlowMap stores sections for efficient lookup:

    - ``_sections``: List of FlowMapSection objects
    - ``_target_boundaries``: Sorted list of target section starts for
      binary search

    Attributes:
        flow: The computed Flow, or ``None`` for interval-built maps.
        id: Identifier for this FlowMap.
    """

    def __init__(
        self,
        source: Flow | object | None = None,
        *,
        id: str = "",
        resolve: Callable[[str], object] | None = None,
    ) -> None:
        """Build a FlowMap from a Flow, interval-like descriptors, or nothing.

        Args:
            source: ``None`` for an empty map, a :class:`Flow` for MC-space
                sections, or a single/collection of interval-like descriptors
                for directly-built sections.
            id: Identifier for this FlowMap. Defaults to the flow's mode value
                for a Flow source, or ``"default"`` for interval descriptors.
            resolve: Callable mapping a region name to an interval-like object
                (e.g. a timeline's ``get_region``), used only when *source*
                carries region-name strings.
        """
        self.flow: Flow | None = None
        self.id: str = id
        self._sections: list[FlowMapSection] = []
        self._target_boundaries: list[Fraction] = []

        if source is None:
            return

        if isinstance(source, Flow):
            self.flow = source
            if not self.id:
                self.id = source.mode.value
            self._build_section_tables()
            return

        # Interval-like singleton or collection: build sections directly in
        # the source coordinate space of the descriptors (e.g. quarterbeats).
        if not self.id:
            self.id = "default"
        intervals = _coerce_intervals(source, resolve=resolve)
        self._build_from_intervals(intervals)

    def _build_from_intervals(self, intervals: list[tuple[Fraction, Fraction]]) -> None:
        """Build section tables from ``(start, end)`` source ranges.

        Each interval becomes one FlowMapSection whose target position is the
        cumulative sum of preceding interval durations, so the played spans
        concatenate contiguously in the target (unfolded) axis.

        Args:
            intervals: The ``(start, end)`` source ranges, in target order.
        """
        target_position = Fraction(0)

        for source_start, source_end in intervals:
            section_duration = source_end - source_start
            self._sections.append(
                FlowMapSection(
                    source_start=source_start,
                    source_end=source_end,
                    target_start=target_position,
                )
            )
            self._target_boundaries.append(target_position)
            target_position += section_duration

    def _build_section_tables(self) -> None:
        """Build section tables from the Flow for coordinate lookup.

        Each PlaythroughSection defines a source coordinate range (start, end)
        and its position in the target sequence is determined cumulatively.
        """
        if self.flow is None or not self.flow.sections:
            return

        target_position = Fraction(0)

        for sec in self.flow.sections:
            source_start = Fraction(sec.mc_start)
            source_end = Fraction(sec.mc_end)
            section_duration = source_end - source_start

            self._sections.append(
                FlowMapSection(
                    source_start=source_start,
                    source_end=source_end,
                    target_start=target_position,
                )
            )
            self._target_boundaries.append(target_position)

            target_position += section_duration

    def unfold(self, coord: Fraction | float | int) -> list[Fraction]:
        """Map source coordinate to target coordinates.

        Since a source coordinate may be visited multiple times (due to repeats),
        this returns a list of all corresponding target coordinates.

        Args:
            coord: Coordinate in source timeline.

        Returns:
            List of coordinates in target timeline. Empty list if coord
            is not within any section.

        Examples:
            >>> # Source coord 3 appears twice due to repeat
            >>> flow_map.unfold(3)
            [Fraction(2), Fraction(6)]
        """
        coord = Fraction(coord)
        results: list[Fraction] = []

        for sec in self._sections:
            # Check if coord falls within this section [start, end)
            if sec.source_start <= coord < sec.source_end:
                offset = coord - sec.source_start
                results.append(sec.target_start + offset)

        return results

    def fold(self, coord: Fraction | float | int) -> Fraction:
        """Map target coordinate back to source coordinate.

        The target timeline has unique coordinates, so this always returns
        a single value.

        Args:
            coord: Coordinate in target timeline.

        Returns:
            Coordinate in source timeline.

        Raises:
            ValueError: If coordinate is outside the flow range.

        Examples:
            >>> # Target coord 6 maps back to source coord 3
            >>> flow_map.fold(6)
            Fraction(3)
        """
        coord = Fraction(coord)

        if not self._sections:
            raise ValueError(f"FlowMap has no sections, cannot fold coordinate {coord}")

        # Binary search to find the section containing this target coordinate
        idx = bisect.bisect_right(self._target_boundaries, coord) - 1

        if idx < 0:
            raise ValueError(
                f"Coordinate {coord} is before the start of the flow "
                f"(starts at {self._target_boundaries[0]})"
            )

        if idx >= len(self._sections):
            raise ValueError(f"Coordinate {coord} is beyond the end of the flow")

        sec = self._sections[idx]

        # Check if coord is within this section's target range
        if coord >= sec.target_end:
            raise ValueError(
                f"Coordinate {coord} is beyond the end of the flow "
                f"(ends at {self._sections[-1].target_end})"
            )

        offset = coord - sec.target_start
        return sec.source_start + offset

    def inverse(self) -> "FlowMap":
        """Create the inverse FlowMap (target -> source becomes source -> target).

        The inverse FlowMap swaps the source and target coordinate systems.
        This is useful for attaching to a target timeline to enable
        tracing back to the original source.

        Note:
            The inverse FlowMap's unfold() returns coordinates in the original
            source space, which may yield multiple results if the source coord
            is visited multiple times.

        Returns:
            A new FlowMap with inverted sections.
        """
        inverse_sections = []

        for sec in self._sections:
            inverse_sections.append(
                FlowMapSection(
                    source_start=sec.target_start,
                    source_end=sec.target_end,
                    target_start=sec.source_start,
                )
            )

        inverse = FlowMap(id=f"{self.id}_inverse")
        inverse.flow = self.flow
        inverse._sections = inverse_sections
        inverse._target_boundaries = [sec.source_start for sec in inverse_sections]

        return inverse

    @property
    def total_target_length(self) -> Fraction:
        """Total length of the target timeline."""
        if not self._sections:
            return Fraction(0)
        return self._sections[-1].target_end

    @property
    def n_sections(self) -> int:
        """Number of sections in this FlowMap."""
        return len(self._sections)

    @classmethod
    def from_qb_sections(
        cls,
        flow: Flow,
        qb_sections: list[tuple[Fraction, Fraction]],
        *,
        id: str = "",
    ) -> "FlowMap":
        """Create a FlowMap with QB-space source coordinates.

        Unlike the default constructor which derives source coordinates from
        MC numbers (integers), this factory accepts pre-computed quarterbeat
        boundaries.  This is the correct approach for scores with non-uniform
        measure durations, where MC-number space != QB-coordinate space.

        Args:
            flow: The computed Flow (retained for metadata and inverse ops).
            qb_sections: List of ``(qb_start, qb_end)`` tuples giving the
                quarterbeat boundaries of each section in the **folded**
                source timeline.  Must have the same length as ``flow.sections``.
            id: Optional identifier.  Defaults to ``flow.mode.value``.

        Returns:
            FlowMap with sections in QB-space.

        Raises:
            ValueError: If ``len(qb_sections) != len(flow.sections)``.

        See Also:
            `compute_qb_sections`: Computes QB boundaries from a Flow and
                ScoreFlowController.
        """
        if len(qb_sections) != len(flow.sections):
            raise ValueError(
                f"qb_sections has {len(qb_sections)} entries but flow has "
                f"{len(flow.sections)} sections"
            )

        fm = cls.__new__(cls)
        fm.flow = flow
        fm.id = id or flow.mode.value
        fm._sections = []
        fm._target_boundaries = []

        target_position = Fraction(0)

        for qb_start, qb_end in qb_sections:
            section_duration = qb_end - qb_start
            fm._sections.append(
                FlowMapSection(
                    source_start=qb_start,
                    source_end=qb_end,
                    target_start=target_position,
                )
            )
            fm._target_boundaries.append(target_position)
            target_position += section_duration

        return fm

    def __repr__(self) -> str:
        return f"FlowMap({self.id}: {self.n_sections} sections)"
