"""Domain-specific Timeline subclasses.

This module provides the 6 concrete Timeline types:
- ContinuousLogicalTimeline, DiscreteLogicalTimeline
- ContinuousPhysicalTimeline, DiscretePhysicalTimeline
- ContinuousGraphicalTimeline, DiscreteGraphicalTimeline

Each class restricts valid units to its domain and modality,
and provides sensible defaults.

Additionally provides:
- SegmentLine: A timeline where all children are contiguous (Segments)
- Convenience methods for creating metrical timelines via TimelineGroups
  (NOT as children, per TTA specification that children must share parent's unit)
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Iterator, Literal, TypeVar

from timetoalign.core import Coordinate, CoordinateValue, NumberType, TimeUnit

from .base import Timeline
from .mixins import ContinuousMixin, DiscreteMixin

# TypeVar for SegmentLine's generic segment type parameter.
# Bound to Timeline so that SegmentLine[ContinuousLogicalTimeline] etc. work.
T = TypeVar("T", bound=Timeline)

if TYPE_CHECKING:
    from timetoalign.alignment.groups import TimelineGroup
    from timetoalign.maps.meter import MetricalPositionMap, MetricMap


# region MetricalResult


@dataclass
class MetricalResult:
    """Result of creating a metrical timeline from a physical timeline.

    Per TTA specification (Section 3.4), children must share the parent's unit.
    Cross-domain relationships (physical-logical) are established via
    TimelineGroups with bidirectional C-Maps, not parent-child embedding.

    Attributes:
        grid: The created ContinuousLogicalTimeline (in quarters).
        group: TimelineGroup connecting the physical and logical timelines.
        physical_timeline: The original physical timeline.
        meter_map: The MetricMap providing measure boundaries.
        metrical_map: The MetricalPositionMap for {mc, beat} lookups.
    """

    grid: ContinuousLogicalTimeline
    group: TimelineGroup
    physical_timeline: ContinuousPhysicalTimeline
    meter_map: MetricMap
    metrical_map: MetricalPositionMap

    def timestamp_at_seconds(self, seconds: float) -> dict[str, Any]:
        """Get timestamp with metrical info at a given second.

        Args:
            seconds: Coordinate on the physical timeline.

        Returns:
            Dictionary with 'seconds', 'quarters', 'mc', 'beat', 'mn' keys.
        """
        ts = self.group.get_timestamp_at(seconds, self.physical_timeline.id)
        quarters = ts[self.grid.id]
        if quarters is None:
            return {
                "seconds": seconds,
                "quarters": None,
                "mc": None,
                "beat": None,
                "mn": None,
            }

        position = self.metrical_map(quarters)
        return {
            "seconds": seconds,
            "quarters": quarters,
            "mc": position["mc"],
            "beat": position["beat"],
            "mn": self.meter_map.get_mn(position["mc"]),
        }

    def seconds_at(self, mc: int, beat: Fraction | float = Fraction(1, 1)) -> float:
        """Get seconds coordinate for a given measure and beat.

        Args:
            mc: Measure count (1-indexed).
            beat: Beat within measure (1-indexed). Default: beat 1.

        Returns:
            Coordinate in seconds on the physical timeline.

        Raises:
            ValueError: If the measure/beat position is outside the aligned range.
        """
        quarters = self.metrical_map.quarters_at(mc, beat)
        result = self.group.convert(
            float(quarters), self.grid.id, self.physical_timeline.id
        )
        if result is None:
            raise ValueError(
                f"Metrical position (MC={mc}, beat={beat}) at quarter {quarters} "
                f"is outside the aligned range"
            )
        return result


# endregion

# region Unit Sets by Domain

# Logical domain units (symbolic/musical time)
LOGICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.beats,
        TimeUnit.quarters,
        TimeUnit.measures,
        TimeUnit.ticks,
        TimeUnit.number,
    }
)

# Physical domain units (acoustic/real time)
PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.seconds,
        TimeUnit.milliseconds,
        TimeUnit.minutes,
        TimeUnit.samples,
        TimeUnit.frames,
    }
)

# Graphical domain units (visual/spatial)
GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.pixels,
        TimeUnit.meters,
        TimeUnit.centimeters,
        TimeUnit.millimeters,
        TimeUnit.inches,
        TimeUnit.points,
    }
)

# Continuous vs discrete unit categorization
CONTINUOUS_LOGICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.beats, TimeUnit.quarters, TimeUnit.measures, TimeUnit.number}
)
DISCRETE_LOGICAL_UNITS: frozenset[TimeUnit] = frozenset({TimeUnit.ticks})

CONTINUOUS_PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.seconds, TimeUnit.milliseconds, TimeUnit.minutes}
)
DISCRETE_PHYSICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {TimeUnit.samples, TimeUnit.frames}
)

CONTINUOUS_GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset(
    {
        TimeUnit.meters,
        TimeUnit.centimeters,
        TimeUnit.millimeters,
        TimeUnit.inches,
        TimeUnit.points,
    }
)
DISCRETE_GRAPHICAL_UNITS: frozenset[TimeUnit] = frozenset({TimeUnit.pixels})

# endregion


# region Domain Base Classes


class LogicalTimeline(Timeline):
    """A timeline representing logical/musical time.

    Logical timelines measure symbolic musical time such as beats,
    quarter notes, measures, or MIDI ticks. They are used for
    score-based representations of music.

    Allowed units: beats, quarters, measures, ticks, number.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters


class PhysicalTimeline(Timeline):
    """A timeline representing physical/acoustic time.

    Physical timelines measure real-world time in units like
    seconds, milliseconds, or audio samples. They are used for
    performance and audio representations.

    Allowed units: seconds, milliseconds, minutes, samples, frames.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds


class GraphicalTimeline(Timeline):
    """A timeline representing graphical/spatial coordinates.

    Graphical timelines measure visual positions for score
    visualization and plotting. They can be in pixels or
    physical measurements.

    Allowed units: pixels, meters, centimeters, millimeters, inches, points.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.pixels


# endregion


# region Continuous Timeline Types


class ContinuousLogicalTimeline(ContinuousMixin, LogicalTimeline):
    """A logical timeline with continuous coordinates.

    Used for score representations where fractional beat positions
    are meaningful (e.g., a note at beat 2.5 or quarter beat 3/4).

    Default unit: quarters (quarter notes).
    Default number type: Fraction (for exact rhythmic representation).
    Allowed units: beats, quarters, measures, number (NOT ticks).
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters
    _default_number_type: ClassVar[NumberType] = NumberType.fraction


class ContinuousPhysicalTimeline(ContinuousMixin, PhysicalTimeline):
    """A physical timeline with continuous coordinates.

    Used for acoustic time measurements where arbitrary precision
    is needed (e.g., note onsets at 1.234 seconds).

    Default unit: seconds.
    Default number type: float.
    Allowed units: seconds, milliseconds, minutes (NOT samples/frames).

    Provides convenience methods for creating metrical timelines
    connected via TimelineGroups (per TTA specification, children must
    share the parent's unit; cross-domain relationships use groups).
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    _default_number_type: ClassVar[NumberType] = NumberType.float

    def create_metrical_grid(
        self,
        first_beat_at: float,
        tempo_bpm: float,
        beats_per_measure: int = 4,
        beat_unit: Fraction = Fraction(1, 4),
        end_at: float | None = None,
        start_mc: int = 1,
        start_mn: str = "1",
        anacrusis_quarters: Fraction | None = None,
        measure_type: Literal["none", "events", "children"] = "none",
        beat_type: Literal["none", "instants", "intervals", "segments"] = "none",
        name: str | None = None,
    ) -> MetricalResult:
        """Create a metrical grid timeline with automatic beat/measure computation.

        This is the primary convenience method for users who have an audio file
        and know: (1) tempo, (2) meter, and (3) where the first beat is.
        They do NOT need to know the total length in quarters - the library
        computes that automatically.

        Per TTA specification (Section 3.4 - Nested Timelines): "A timeline can
        accommodate other timelines as Children, as long as they use the same
        measuring unit." Therefore, a logical timeline (quarters) cannot be a
        child of a physical timeline (seconds). Instead, this method creates
        a standalone ContinuousLogicalTimeline and connects it to this physical
        timeline via a TimelineGroup with bidirectional linear interpolation.

        The returned MetricalResult provides convenient access to:
        - The created grid (ContinuousLogicalTimeline in quarters)
        - The TimelineGroup connecting physical and logical coordinates
        - Methods for timestamp queries with metrical information

        Args:
            first_beat_at: Coordinate (in seconds) of the first beat.
            tempo_bpm: Tempo in beats per minute.
            beats_per_measure: Number of beats per measure. Default 4.
            beat_unit: Note value of one beat. Default 1/4 (quarter note).
                      Use Fraction(1, 8) for eighth-note beats (e.g., 6/8 time).
            end_at: Coordinate (in seconds) where the grid ends.
                   If None, extends to the end of the physical timeline.
            start_mc: MC (measure count) of the first measure. Default 1.
            start_mn: MN (measure number label) of the first measure.
                     Default "1". Use "0" for anacrusis (pickup measure).
            anacrusis_quarters: If set, the first measure is shorter (pickup).
                               Specified in quarter notes.
            measure_type: How to represent measures in the grid:
                        - "none": No measure entities (default)
                        - "events": Create Measure as IntervalEvents
                        - "children": Create each measure as a Child timeline
            beat_type: How to represent beats in the grid:
                        - "none": No beat entities (default)
                        - "instants": Create Beat as InstantEvents
                        - "intervals": Create Beat as IntervalEvents (with duration)
                        - "segments": Create a SegmentLine with beat Segments
            name: Human-readable name for the grid timeline.

        Returns:
            MetricalResult containing the grid, group, and accessor methods.

        Raises:
            ValueError: If first_beat_at is negative or after end_at.

        Examples:
            >>> # Audio file at 120 BPM, 4/4, first beat at 0.5 seconds
            >>> audio = ContinuousPhysicalTimeline(length=180.0)
            >>> result = audio.create_metrical_grid(
            ...     first_beat_at=0.5,
            ...     tempo_bpm=120.0,
            ...     beats_per_measure=4,
            ... )
            >>> # Query metrical info at 60 seconds
            >>> result.timestamp_at_seconds(60.0)
            {'seconds': 60.0, 'quarters': 119.0, 'mc': 30, 'beat': Fraction(4, 1), 'mn': '30'}

            >>> # Find where measure 10, beat 1 is
            >>> result.seconds_at(mc=10, beat=Fraction(1, 1))
            18.5

            >>> # Access the group for general coordinate conversion
            >>> result.group.convert(100.0, result.grid.id, audio.id)  # quarters -> seconds
            50.5

            >>> # With anacrusis (pickup beat)
            >>> result = audio.create_metrical_grid(
            ...     first_beat_at=0.25,
            ...     tempo_bpm=100.0,
            ...     beats_per_measure=3,
            ...     start_mn="0",
            ...     anacrusis_quarters=Fraction(1, 1),  # 1 beat pickup
            ... )
        """
        from timetoalign.alignment.groups import TimelineGroup
        from timetoalign.maps import LinearMap
        from timetoalign.maps.meter import MetricalPositionMap, MetricMap

        # Validate inputs
        if first_beat_at < 0:
            raise ValueError(f"first_beat_at must be non-negative, got {first_beat_at}")

        # Determine end coordinate
        if end_at is None:
            end_at = float(self._length.value)
        elif end_at <= first_beat_at:
            raise ValueError(
                f"end_at ({end_at}) must be after first_beat_at ({first_beat_at})"
            )

        # Calculate duration in seconds
        duration_seconds = end_at - first_beat_at

        # Calculate quarters per second from tempo
        # BPM = beats per minute
        # quarters_per_beat = beat_unit * 4 (since 4 quarters = 1 whole note)
        # beats_per_second = BPM / 60
        # quarters_per_second = beats_per_second * quarters_per_beat
        quarters_per_beat = Fraction(beat_unit) * 4
        beats_per_second = tempo_bpm / 60.0
        quarters_per_second = float(quarters_per_beat) * beats_per_second

        # Calculate total quarters
        total_quarters = duration_seconds * quarters_per_second

        # Calculate number of measures (accounting for anacrusis if present)
        quarters_per_measure = quarters_per_beat * beats_per_measure

        if anacrusis_quarters is not None:
            # First measure is shorter
            remaining_quarters = total_quarters - float(anacrusis_quarters)
            n_full_measures = int(remaining_quarters // float(quarters_per_measure))
            n_measures = 1 + n_full_measures  # anacrusis + full measures
        else:
            n_measures = int(total_quarters // float(quarters_per_measure))
            if n_measures == 0:
                n_measures = 1  # At least one measure

        # Create the MetricMap
        meter_map = MetricMap.from_uniform(
            n_measures=n_measures,
            quarters_per_measure=quarters_per_measure,
            start_mc=start_mc,
            start_mn=start_mn,
            anacrusis_quarters=anacrusis_quarters,
        )

        # Compute actual length from meter map
        length_quarters = meter_map.total_length

        # Create the logical timeline (NOT a child - standalone timeline)
        grid = ContinuousLogicalTimeline(
            length=length_quarters,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            name=name or f"meter_{self.id}",
        )

        # Add the MetricalPositionMap to the grid
        metrical_map = MetricalPositionMap(meter_map)
        grid.add_conversion_map(metrical_map)
        grid.add_conversion_map(meter_map)

        # Add tempo C-Map: quarters -> seconds (relative to grid's origin)
        # seconds = quarters / quarters_per_second
        tempo_map = LinearMap(
            scalar=1.0 / quarters_per_second,
            offset=0.0,
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.seconds,
            uid=f"{grid.id}_tempo_map",
        )
        grid.add_conversion_map(tempo_map)

        # Materialize measures if requested
        if measure_type == "events":
            self._materialize_measures_as_events(grid, meter_map)
        elif measure_type == "children":
            self._materialize_measures_as_children(grid, meter_map)

        # Materialize beats if requested
        if beat_type == "instants":
            self._materialize_beats_as_instants(grid, meter_map, quarters_per_beat)
        elif beat_type == "intervals":
            self._materialize_beats_as_intervals(grid, meter_map, quarters_per_beat)
        elif beat_type == "segments":
            self._materialize_beats_as_segments(grid, meter_map, quarters_per_beat)

        # Create TimelineGroup to connect physical and logical timelines
        # Per TTA: Cross-domain relationships use groups, not parent-child
        group = TimelineGroup()

        # Add this physical timeline as reference (defines initial group extent)
        # Group boundaries: [first_beat_at, end_at] in seconds
        group.add_timeline(
            self,
            start=first_beat_at,
            end=end_at,
        )

        # Add the logical grid, aligned with the physical timeline
        # The grid's [0, length_quarters] maps to physical [first_beat_at, end_at]
        # Since the group already has the physical timeline, the grid is automatically
        # aligned to map 0 -> first_beat_at and length_quarters -> end_at
        group.add_timeline(grid)

        return MetricalResult(
            grid=grid,
            group=group,
            physical_timeline=self,
            meter_map=meter_map,
            metrical_map=metrical_map,
        )

    def _materialize_measures_as_events(
        self,
        grid: ContinuousLogicalTimeline,
        meter_map: MetricMap,
    ) -> int:
        """Create Measure IntervalEvents in the grid timeline."""
        events = []
        for i in range(meter_map.n_measures):
            info = meter_map.get_measure_info(meter_map._mcs[i])
            if info is None:
                continue

            events.append(
                {
                    "id": f"measure_{info['mc']}",
                    "name": f"M{info['mn']}",
                    "temporal_type": "interval",
                    "event_type": "Measure",
                    "start": float(info["start"]),
                    "end": float(info["end"]),
                    "mc": info["mc"],
                    "mn": info["mn"],
                }
            )

        if events:
            grid.add_events(events)
        return len(events)

    def _materialize_measures_as_children(
        self,
        grid: ContinuousLogicalTimeline,
        meter_map: MetricMap,
    ) -> int:
        """Create each measure as a Child timeline of the grid.

        Per TTA specification, children share the parent's unit (quarters),
        so this is a valid nesting.
        """
        for i in range(meter_map.n_measures):
            info = meter_map.get_measure_info(meter_map._mcs[i])
            if info is None:
                continue

            # Create a child timeline for this measure
            measure_child = ContinuousLogicalTimeline(
                length=info["length"],
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
                name=f"M{info['mn']}",
            )

            # Add as child at the measure's start offset
            grid.add_child(measure_child, offset=info["start"])

        return meter_map.n_measures

    def _materialize_beats_as_instants(
        self,
        grid: ContinuousLogicalTimeline,
        meter_map: MetricMap,
        quarters_per_beat: Fraction,
    ) -> int:
        """Create Beat InstantEvents in the grid timeline."""
        events = []
        position = Fraction(0, 1)
        beat_num = 0

        while position < meter_map.total_length:
            mc = meter_map(float(position))
            beat = meter_map.beat_in_measure(position)
            is_downbeat = beat == Fraction(1, 1)

            events.append(
                {
                    "id": f"beat_{beat_num}",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": float(position),
                    "mc": mc,
                    "mn": meter_map.get_mn(mc),
                    "beat": str(beat),  # Store as string to preserve Fraction
                    "is_downbeat": is_downbeat,
                }
            )

            position += quarters_per_beat
            beat_num += 1

        if events:
            grid.add_events(events)
        return len(events)

    def _materialize_beats_as_intervals(
        self,
        grid: ContinuousLogicalTimeline,
        meter_map: MetricMap,
        quarters_per_beat: Fraction,
    ) -> int:
        """Create Beat IntervalEvents (with duration) in the grid timeline."""
        events = []
        position = Fraction(0, 1)
        beat_num = 0

        while position < meter_map.total_length:
            mc = meter_map(float(position))
            beat = meter_map.beat_in_measure(position)
            is_downbeat = beat == Fraction(1, 1)
            end_pos = position + quarters_per_beat

            # Clamp to total length
            if end_pos > meter_map.total_length:
                end_pos = meter_map.total_length

            events.append(
                {
                    "id": f"beat_{beat_num}",
                    "temporal_type": "interval",
                    "event_type": "Beat",
                    "start": float(position),
                    "end": float(end_pos),
                    "mc": mc,
                    "mn": meter_map.get_mn(mc),
                    "beat": str(beat),
                    "is_downbeat": is_downbeat,
                }
            )

            position += quarters_per_beat
            beat_num += 1

        if events:
            grid.add_events(events)
        return len(events)

    def _materialize_beats_as_segments(
        self,
        grid: ContinuousLogicalTimeline,
        meter_map: MetricMap,
        quarters_per_beat: Fraction,
    ) -> int:
        """Create beats as a SegmentLine (contiguous Child timelines).

        Per TTA Table 2, Segments are Children that are contiguous with their
        siblings, forming a SegmentLine.
        """
        position = Fraction(0, 1)
        beat_num = 0

        while position < meter_map.total_length:
            mc = meter_map(float(position))
            beat = meter_map.beat_in_measure(position)
            end_pos = position + quarters_per_beat

            # Clamp to total length
            if end_pos > meter_map.total_length:
                end_pos = meter_map.total_length

            segment_length = end_pos - position
            if segment_length <= 0:
                break

            # Create a Segment (Child timeline) for this beat
            beat_segment = ContinuousLogicalTimeline(
                length=segment_length,
                unit=TimeUnit.quarters,
                number_type=NumberType.fraction,
                name=f"Beat_{mc}_{beat}",
            )

            # Add as child at the beat's start offset (contiguous placement)
            grid.add_child(beat_segment, offset=position)

            position = end_pos
            beat_num += 1

        return beat_num

    def create_metrical_region(
        self,
        region_name: str,
        tempo_bpm: float,
        beats_per_measure: int = 4,
        beat_unit: Fraction = Fraction(1, 4),
        start_mc: int = 1,
        start_mn: str = "1",
        anacrusis_quarters: Fraction | None = None,
        measure_type: Literal["none", "events", "children"] = "none",
        beat_type: Literal["none", "instants", "intervals", "segments"] = "none",
    ) -> MetricalResult:
        """Create a metrical grid for an existing region.

        This method creates a metrical grid that corresponds to a named region
        on this physical timeline. Per TTA Table 2, regions are named parts of
        a timeline defined by a TimeInterval. This method creates the metrical
        structure for that region.

        Args:
            region_name: Name of an existing region on this timeline.
            tempo_bpm: Tempo in beats per minute.
            beats_per_measure: Number of beats per measure. Default 4.
            beat_unit: Note value of one beat. Default 1/4 (quarter note).
            start_mc: MC (measure count) of the first measure. Default 1.
            start_mn: MN (measure number label) of the first measure.
            anacrusis_quarters: If set, the first measure is shorter (pickup).
            measure_type: How to represent measures:
                        - "none": No measure entities (default)
                        - "events": Create Measure as IntervalEvents
                        - "children": Create each measure as a Child timeline
            beat_type: How to represent beats:
                        - "none": No beat entities (default)
                        - "instants": Create Beat as InstantEvents
                        - "intervals": Create Beat as IntervalEvents
                        - "segments": Create a SegmentLine with beat Segments

        Returns:
            MetricalResult containing the grid, group, and accessor methods.

        Raises:
            KeyError: If the region does not exist.

        Examples:
            >>> audio = ContinuousPhysicalTimeline(length=300.0)
            >>> audio.add_region("verse", start=10.0, end=50.0)
            >>> result = audio.create_metrical_region(
            ...     region_name="verse",
            ...     tempo_bpm=100.0,
            ...     beats_per_measure=4,
            ... )
            >>> result.timestamp_at_seconds(25.0)
            {'seconds': 25.0, 'quarters': 25.0, 'mc': 7, 'beat': Fraction(2, 1), 'mn': '7'}
        """
        region = self.get_region(region_name)  # Raises KeyError if not found

        start = float(region.start.value)
        end = float(region.end.value)

        return self.create_metrical_grid(
            first_beat_at=start,
            tempo_bpm=tempo_bpm,
            beats_per_measure=beats_per_measure,
            beat_unit=beat_unit,
            end_at=end,
            start_mc=start_mc,
            start_mn=start_mn,
            anacrusis_quarters=anacrusis_quarters,
            measure_type=measure_type,
            beat_type=beat_type,
            name=f"meter_{region_name}",
        )


class ContinuousGraphicalTimeline(ContinuousMixin, GraphicalTimeline):
    """A graphical timeline with continuous coordinates.

    Used for visualization where real-valued positions are needed
    (e.g., a note head at x=12.75 centimeters).

    Default unit: centimeters.
    Default number type: float.
    Allowed units: meters, centimeters, millimeters, inches, points.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = CONTINUOUS_GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.centimeters
    _default_number_type: ClassVar[NumberType] = NumberType.float


# endregion


# region Discrete Timeline Types


class DiscreteLogicalTimeline(DiscreteMixin, LogicalTimeline):
    """A logical timeline with discrete (integer) coordinates.

    Used for MIDI-based representations where time is measured in
    quantized ticks. Essential for MIDI file parsing and generation.

    Default unit: ticks.
    Default number type: int.
    Allowed units: ticks only.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_LOGICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.ticks
    _default_number_type: ClassVar[NumberType] = NumberType.int


class DiscretePhysicalTimeline(DiscreteMixin, PhysicalTimeline):
    """A physical timeline with discrete (integer) coordinates.

    Used for audio sample-based representations where time is
    measured in discrete sample indices or video frames.

    Default unit: samples.
    Default number type: int.
    Allowed units: samples, frames.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_PHYSICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.samples
    _default_number_type: ClassVar[NumberType] = NumberType.int


class DiscreteGraphicalTimeline(DiscreteMixin, GraphicalTimeline):
    """A graphical timeline with discrete (integer) coordinates.

    Used for pixel-based visualization where positions are
    quantized to screen coordinates.

    Default unit: pixels.
    Default number type: int.
    Allowed units: pixels only.
    """

    _allowed_units: ClassVar[frozenset[TimeUnit]] = DISCRETE_GRAPHICAL_UNITS
    _default_unit: ClassVar[TimeUnit] = TimeUnit.pixels
    _default_number_type: ClassVar[NumberType] = NumberType.int


# endregion


# region SegmentLine


class SegmentLine(Timeline, Generic[T]):
    """A timeline containing only contiguous Segments.

    SegmentLine is parameterized by the segment type ``T`` (a Timeline
    subclass), enabling both runtime type enforcement and static type
    checking.  When ``segment_type`` is provided, every appended segment
    must be an instance of that class (or a subclass).  When omitted,
    the type is inferred from the first segment added.

    Segments are children that:
    - Start exactly where the previous segment ends
    - Have no gaps or overlaps

    SegmentLine provides additional convenience methods for
    segment-based access patterns and C-map concatenation.

    From TTA manuscript (Section 3.4):
    "When all Children of the same parent timeline ('siblings') are
    contiguous with each other, we call them Segments and the parent
    a SegmentLine."

    The key advantage of SegmentLine is that C-maps from individual
    segments can be concatenated into a single PiecewiseMap, enabling
    cumulative coordinate conversion across the entire timeline.

    Attributes:
        segment_order: Ordered list of segment IDs (insertion order).
        segment_type: The Timeline subclass that all segments must be
            instances of (or None if not yet determined).

    Examples:
        >>> # Typed SegmentLine -- enforces segment class
        >>> score: SegmentLine[ContinuousLogicalTimeline] = SegmentLine(
        ...     unit=TimeUnit.quarters,
        ...     segment_type=ContinuousLogicalTimeline,
        ... )
        >>> for i in range(4):
        ...     measure = ContinuousLogicalTimeline(length=Fraction(4))
        ...     score.append_segment(measure, name=f"m{i+1}")
        >>> score.segment_type
        <class 'ContinuousLogicalTimeline'>

        >>> # Inferred type -- locks on first append
        >>> sl = SegmentLine.empty(unit=TimeUnit.quarters)
        >>> sl.append_segment(ContinuousLogicalTimeline(length=Fraction(4)))
        >>> sl.segment_type
        <class 'ContinuousLogicalTimeline'>

        >>> # Access by index
        >>> offset, segment = score.get_segment_by_index(2)
        >>> offset
        Coordinate(8, quarters)

        >>> # Find segment containing a coordinate
        >>> idx, seg, ts = score.get_segment_at(10.0)
        >>> idx
        2  # Third segment (0-indexed)
    """

    def __init__(
        self,
        segment_type: type[Timeline] | None = None,
        inner_segment_type: type[Timeline] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a SegmentLine.

        Args:
            segment_type: The Timeline subclass that all segments must be
                instances of.  If ``None`` (default), the type is inferred
                from the first segment added.  Providing it explicitly
                enables early validation and clearer static typing.
            inner_segment_type: When ``segment_type`` is ``SegmentLine``,
                specifies the ``segment_type`` that each child SegmentLine
                must have.  This enables recursive type enforcement
                (e.g. ``SegmentLine[SegmentLine[DiscreteGraphicalTimeline]]``).
                Inferred from the first child's ``segment_type`` if not set.
            **kwargs: Arguments passed to Timeline.__init__.
        """
        super().__init__(**kwargs)
        self._segment_order: list[str] = []
        self._segment_type: type[Timeline] | None = segment_type
        self._inner_segment_type: type[Timeline] | None = inner_segment_type

    @property
    def segment_type(self) -> type[Timeline] | None:
        """The Timeline subclass that all segments must be instances of.

        Returns ``None`` if no ``segment_type`` was specified at construction
        and no segments have been added yet (the type will be inferred from
        the first segment).

        Returns:
            The segment class, or None if not yet determined.

        Examples:
            >>> sl = SegmentLine(
            ...     unit=TimeUnit.quarters,
            ...     segment_type=ContinuousLogicalTimeline,
            ... )
            >>> sl.segment_type
            <class 'ContinuousLogicalTimeline'>
        """
        return self._segment_type

    @property
    def class_name(self) -> str:
        """The class name including the segment type parameter (recursive).

        When ``segment_type`` is set, returns ``SegmentLine[<type>]``.
        When segments are themselves SegmentLines with a known
        ``inner_segment_type``, the display is recursive:
        ``SegmentLine[SegmentLine[DiscreteGraphicalTimeline]]``.

        Examples:
            >>> sl = SegmentLine(
            ...     unit=TimeUnit.quarters,
            ...     segment_type=ContinuousLogicalTimeline,
            ... )
            >>> sl.class_name
            'SegmentLine[ContinuousLogicalTimeline]'

            >>> nested = SegmentLine(
            ...     unit=TimeUnit.pixels,
            ...     segment_type=SegmentLine,
            ...     inner_segment_type=DiscreteGraphicalTimeline,
            ... )
            >>> nested.class_name
            'SegmentLine[SegmentLine[DiscreteGraphicalTimeline]]'
        """
        if self._segment_type is None:
            return "SegmentLine"
        if self._segment_type is SegmentLine and self._inner_segment_type is not None:
            return f"SegmentLine[SegmentLine[{self._inner_segment_type.__name__}]]"
        return f"SegmentLine[{self._segment_type.__name__}]"

    def validate_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
    ) -> None:
        """Override to enforce contiguity and segment type consistency.

        Segments must start exactly where the previous segment ends.
        The first segment must start at 0.  All segments must be instances
        of the same Timeline subclass (either specified at construction or
        inferred from the first segment added).

        When the segment type is ``SegmentLine``, child SegmentLines must
        also share the same ``segment_type`` (i.e. differently-parameterized
        SegmentLines are treated as incompatible types).

        Args:
            child: The timeline to validate.
            offset: The proposed start coordinate.

        Raises:
            ValueError: If offset doesn't produce contiguous placement.
            TypeError: If child's class does not match the segment type.
            TypeError: If child is a SegmentLine with a different
                ``segment_type`` than the expected inner segment type.
        """
        super().validate_child(child, offset)

        # Enforce segment type consistency
        if self._segment_type is not None:
            if not isinstance(child, self._segment_type):
                raise TypeError(
                    f"SegmentLine expects segments of type "
                    f"{self._segment_type.__name__}, got "
                    f"{type(child).__name__}. All segments in a "
                    f"SegmentLine must be the same Timeline subclass."
                )

            # When segments are SegmentLines, enforce matching inner type
            if (
                self._segment_type is SegmentLine
                and isinstance(child, SegmentLine)
                and self._inner_segment_type is not None
            ):
                child_inner = child.segment_type
                if child_inner != self._inner_segment_type:
                    expected = self._inner_segment_type.__name__
                    got = child_inner.__name__ if child_inner else "None"
                    raise TypeError(
                        f"SegmentLine expects SegmentLine[{expected}] "
                        f"segments, got SegmentLine[{got}]. All child "
                        f"SegmentLines must have the same segment_type."
                    )

        offset_val = offset.value if isinstance(offset, Coordinate) else offset

        # First segment must start at 0 (or current length if empty)
        expected_offset = self.length.value if self._segment_order else 0

        if offset_val != expected_offset:
            raise ValueError(
                f"SegmentLine requires contiguous segments. "
                f"Expected offset {expected_offset}, got {offset_val}. "
                f"Use append_segment() for automatic offset calculation."
            )

    def add_child(
        self,
        child: Timeline,
        offset: CoordinateValue | Coordinate,
        allow_expansion: bool = False,
    ) -> None:
        """Add a segment at the specified offset.

        Overrides Timeline.add_child to also track segment order and
        infer/enforce the segment type.

        Args:
            child: The segment to add.
            offset: The start coordinate (must be contiguous).
            allow_expansion: If True, expand timeline if needed.

        Raises:
            ValueError: If placement would not be contiguous.
            TypeError: If child's class does not match the segment type.
        """
        # Validate first (will check contiguity and segment type)
        super().add_child(child, offset, allow_expansion)

        # Infer segment_type from first segment if not explicitly set
        if self._segment_type is None:
            self._segment_type = type(child)

        # Infer inner_segment_type from first SegmentLine child
        if (
            self._inner_segment_type is None
            and isinstance(child, SegmentLine)
            and child.segment_type is not None
        ):
            self._inner_segment_type = child.segment_type

        # Track segment order
        self._segment_order.append(child.id)

    def append_segment(
        self,
        segment: Timeline,
        name: str | None = None,
    ) -> None:
        """Append a segment at the current end coordinate.

        The segment's offset is automatically set to current length.

        Args:
            segment: Timeline to add as segment.
            name: Optional name override for the segment.
        """
        offset = self.length

        # Override name if provided
        if name:
            segment._name = name

        # Use add_child (validates unit match, builds InterpolationMap)
        self.add_child(segment, offset, allow_expansion=True)

    def get_segment_at(
        self,
        coord: CoordinateValue,
    ) -> tuple[int, Timeline, Any]:
        """Get segment containing a coordinate.

        Args:
            coord: Coordinate in this SegmentLine.

        Returns:
            Tuple of (segment_index, segment, timestamp_in_segment).

        Raises:
            ValueError: If no segment contains the coordinate.
        """
        ts = self.get_timestamp(coord)
        coord_val = (
            float(coord) if not isinstance(coord, Coordinate) else float(coord.value)
        )

        for i, seg_id in enumerate(self._segment_order):
            seg_coord = ts.get(seg_id)
            if seg_coord is not None and seg_coord >= 0:
                segment = self._children[seg_id]
                if seg_coord <= segment.length.value:
                    seg_ts = segment.get_timestamp(seg_coord)
                    return (i, segment, seg_ts)

        raise ValueError(f"No segment contains coordinate {coord_val}")

    def get_segment_by_index(self, index: int) -> tuple[Coordinate, Timeline]:
        """Get segment by 0-based index.

        Args:
            index: Segment index (0-based).

        Returns:
            Tuple of (offset, segment).

        Raises:
            IndexError: If index is out of range.
        """
        if index < 0 or index >= len(self._segment_order):
            raise IndexError(f"Segment index {index} out of range")

        seg_id = self._segment_order[index]
        return (self._child_offsets[seg_id], self._children[seg_id])

    @property
    def n_segments(self) -> int:
        """Number of segments."""
        return len(self._segment_order)

    def list_segments(self) -> list[str]:
        """List segment IDs in order.

        Returns:
            List of segment IDs (child IDs) in insertion order.
        """
        return list(self._segment_order)

    def has_segment(self, segment_id: str) -> bool:
        """Check if a segment with the given ID exists.

        Args:
            segment_id: The segment ID to check.

        Returns:
            True if a segment with that ID exists.
        """
        return segment_id in self._segment_order

    def __contains__(self, item: Any) -> bool:
        """Check if a region, child, or segment is part of this SegmentLine.

        Extends Timeline.__contains__ to also check segments by ID.
        For strings, checks regions, children, AND segments.

        Args:
            item: A string ID, Region, or Timeline object.
        """
        if isinstance(item, str):
            return (
                item in self._regions
                or item in self._children
                or item in self._segment_order
            )
        return super().__contains__(item)

    def iter_segments(self) -> Iterator[tuple[int, Coordinate, Timeline]]:
        """Iterate over segments in order.

        Yields:
            Tuples of (index, offset, segment).
        """
        for i, seg_id in enumerate(self._segment_order):
            yield (i, self._child_offsets[seg_id], self._children[seg_id])

    def concatenate_cmaps(
        self,
        target_unit: TimeUnit,
    ) -> Any:
        """Concatenate segment C-maps into a single PiecewiseMap.

        Each segment must have a C-map to the target unit.
        The resulting map converts SegmentLine coordinates to the
        cumulative target unit coordinates.

        From manuscript (Section 3.4):
        "The main technical reason why a contiguous subtype is useful is
        that it allows us to concatenate local coordinate systems by
        cumulatively summing segment lengths, but also to apply the same
        operation to the segments' C-maps."

        Args:
            target_unit: The target unit all segment C-maps must convert to.

        Returns:
            PiecewiseMap combining all segment conversions.

        Raises:
            ValueError: If any segment lacks a C-map to target_unit.
        """
        from timetoalign.maps import PiecewiseMap

        pieces = []
        cumulative_offset = 0.0

        for i, offset, segment in self.iter_segments():
            cmap = segment.get_conversion_map(target_unit)
            if cmap is None:
                raise ValueError(
                    f"Segment '{segment.id}' has no C-map to {target_unit}"
                )

            # Get segment bounds in SegmentLine coordinates
            segment_start = float(offset.value)
            segment_end = segment_start + float(segment.length.value)

            # Create piece definition
            pieces.append(
                {
                    "start": segment_start,
                    "end": segment_end,
                    "map": cmap,
                    "offset": cumulative_offset,
                }
            )

            # Cumulate the converted length
            converted_length = cmap(segment.length.value)
            cumulative_offset += float(converted_length)

        return PiecewiseMap.from_segments(
            pieces=pieces,
            source_unit=self.unit,
            target_unit=target_unit,
        )

    @classmethod
    def from_segmentation(
        cls,
        source: Timeline,
        split_coords: list[CoordinateValue],
        copy_events: bool = True,
    ) -> "SegmentLine":
        """Create a SegmentLine by segmenting an existing timeline.

        From manuscript (Section 3.4):
        "A special case of partitioning is segmentation, which is the
        creation of one or several Segments from two or more segmentation
        points on a timeline."

        Note: The segmented timeline is NOT modified. A new SegmentLine
        is created with copies of the relevant portions.

        The ``segment_type`` of the resulting SegmentLine is set to the
        concrete class of ``source``, and segments are instantiated as
        that class. This preserves domain-specific constraints.

        Args:
            source: Timeline to segment (not modified).
            split_coords: Coordinates defining segment boundaries.
                k+1 coordinates create k segments.
            copy_events: If True, copy events to their respective segments.

        Returns:
            New SegmentLine with segments typed to match ``source``.

        Raises:
            ValueError: If source already has children (ambiguous nesting).
            ValueError: If fewer than 2 split coordinates provided.

        Examples:
            >>> source = ContinuousLogicalTimeline(length=100)
            >>> source.add_events([...])  # Some events
            >>> # Split into 4 segments at [0, 25, 50, 75, 100]
            >>> segments = SegmentLine.from_segmentation(
            ...     source, [0, 25, 50, 75, 100]
            ... )
            >>> segments.n_segments
            4
            >>> segments.segment_type
            <class 'ContinuousLogicalTimeline'>
        """
        if source.n_children > 0:
            raise ValueError(
                "Cannot segment a timeline that already has children. "
                "This would create conflicting nesting hierarchies."
            )

        if len(split_coords) < 2:
            raise ValueError(
                f"Segmentation requires at least 2 coordinates, got {len(split_coords)}"
            )

        # Sort and validate coordinates
        coords = sorted(float(c) for c in split_coords)

        # Determine the segment class from the source's concrete type
        source_class = type(source)

        # Create the SegmentLine with length=0 (will expand as segments are added)
        segment_line = cls(
            segment_type=source_class,
            length=0,
            unit=source.unit,
            number_type=source.number_type,
        )

        # Create segments using the source's concrete class
        for i in range(len(coords) - 1):
            start = coords[i]
            end = coords[i + 1]
            length = end - start

            segment = source_class(
                length=length,
                unit=source.unit,
                number_type=source.number_type,
                name=f"segment_{i}",
            )

            if copy_events:
                # Get events in this range from source
                events_in_range = source.get_events(
                    min_coord=start,
                    max_coord=end,
                )

                # Convert EventData to list of dicts and adjust coordinates
                adjusted_events = []
                for event in events_in_range:
                    adjusted = dict(event)
                    for coord_col in ("instant", "start", "end"):
                        val = adjusted.get(coord_col)
                        if val is not None:
                            # Handle coordinate struct or raw value
                            if isinstance(val, dict) and "value" in val:
                                adjusted[coord_col] = val["value"] - start
                            else:
                                adjusted[coord_col] = float(val) - start
                    adjusted_events.append(adjusted)

                if adjusted_events:
                    segment.add_events(adjusted_events)

            segment_line.append_segment(segment)

        return segment_line


# endregion


# region Factory Function


def get_timeline_class(
    domain: str,
    discrete: bool = False,
) -> type[Timeline]:
    """Get the appropriate Timeline class for a domain and modality.

    Args:
        domain: One of "logical", "physical", "graphical".
        discrete: If True, return discrete variant; else continuous.

    Returns:
        The appropriate Timeline subclass.

    Raises:
        ValueError: If domain is not recognized.

    Examples:
        >>> get_timeline_class("logical", discrete=False)
        <class 'ContinuousLogicalTimeline'>
        >>> get_timeline_class("physical", discrete=True)
        <class 'DiscretePhysicalTimeline'>
    """
    classes = {
        ("logical", False): ContinuousLogicalTimeline,
        ("logical", True): DiscreteLogicalTimeline,
        ("physical", False): ContinuousPhysicalTimeline,
        ("physical", True): DiscretePhysicalTimeline,
        ("graphical", False): ContinuousGraphicalTimeline,
        ("graphical", True): DiscreteGraphicalTimeline,
    }

    key = (domain.lower(), discrete)
    if key not in classes:
        raise ValueError(f"Unknown domain '{domain}'")

    return classes[key]


# endregion
