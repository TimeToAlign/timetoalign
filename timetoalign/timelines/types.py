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
from typing import TYPE_CHECKING, Any, ClassVar, Iterator, Literal

from timetoalign.core import Coordinate, CoordinateSpec, NumberType, TimeUnit

from .base import Timeline
from .mixins import ContinuousMixin, DiscreteMixin

if TYPE_CHECKING:
    from timetoalign.maps.meter import MetricalPositionMap, MetricMap
    from timetoalign.timelines.groups import TimelineGroup


# region MetricalResult


@dataclass
class MetricalResult:
    """Result of creating a metrical timeline from a physical timeline.

    Children must share the parent's unit. Cross-domain relationships
    (physical-logical) are established via TimelineGroups with bidirectional
    C-Maps, not parent-child embedding.

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
        TimeUnit.floating_measures,
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
    {TimeUnit.beats, TimeUnit.quarters, TimeUnit.floating_measures, TimeUnit.number}
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

        A timeline can accommodate other timelines as Children when they use
        the same measuring unit. Therefore, a logical timeline (quarters)
        cannot be a child of a physical timeline (seconds). Instead, this
        method creates a standalone ContinuousLogicalTimeline and connects it
        to this physical timeline via a TimelineGroup with bidirectional linear
        interpolation.

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
        from timetoalign.maps import LinearMap
        from timetoalign.maps.meter import MetricalPositionMap, MetricMap
        from timetoalign.timelines.groups import TimelineGroup

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
                    "start": info["start"],
                    "end": info["end"],
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
                    "instant": position,
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
                    "start": position,
                    "end": end_pos,
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

    @classmethod
    def _validate_serialized_payload(cls, data: dict[str, Any]) -> None:
        """Explain legacy graphical payloads that predate unit validation."""
        if data.get("unit") == str(TimeUnit.pixels):
            raise ValueError(
                "Serialized ContinuousGraphicalTimeline payload uses unit 'pixels', "
                "which is discrete-only. This payload predates unit enforcement; "
                "use DiscreteGraphicalTimeline instead."
            )


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


class SegmentLineMixin:
    """Enforce and expose contiguous, homogeneously typed child segments."""

    _segment_type: ClassVar[type[Timeline] | None] = None

    def __init__(self, **kwargs: Any) -> None:
        """Initialize segment ordering before accepting children."""
        super().__init__(**kwargs)
        self._segment_order: list[str] = []

    @classmethod
    def _from_dict_initial_length(cls, data: dict[str, Any]) -> int:
        """Start empty so restored segments can be appended contiguously."""
        return 0

    def _finalize_from_dict(self, data: dict[str, Any]) -> None:
        """Restore the serialized length after rebuilding the segments."""
        self._length = self._make_coordinate(Timeline._from_dict_initial_length(data))

    @property
    def segment_type(self) -> type[Timeline] | None:
        """Return the enforced class, inferred on first append for a bare line."""
        return self._segment_type

    @property
    def class_name(self) -> str:
        """Return the dynamic class name or a bare line's inferred wire tag."""
        if type(self) is SegmentLine and self._segment_type is not None:
            return f"SegmentLine[{self._segment_type.__name__}]"
        return type(self).__name__

    def validate_child(
        self,
        child: Timeline,
        offset: CoordinateSpec,
    ) -> None:
        """Validate the segment class and its exact contiguous offset."""
        super().validate_child(child, offset)

        if self._segment_type is not None:
            if not isinstance(child, self._segment_type):
                raise TypeError(
                    f"SegmentLine expects segments of type "
                    f"{self._segment_type.__name__}, got "
                    f"{type(child).__name__}. All segments in a "
                    f"SegmentLine must be the same Timeline subclass."
                )

        offset_val = self._resolve_axis_value(offset)
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
        offset: CoordinateSpec,
        allow_expansion: bool = False,
    ) -> None:
        """Add a validated segment and record its insertion order."""
        super().add_child(child, offset, allow_expansion)

        if self._segment_type is None:
            self._segment_type = type(child)
        self._segment_order.append(child.id)

    def append_segment(
        self,
        segment: Timeline,
        name: str | None = None,
    ) -> None:
        """Append a segment at the current end coordinate."""
        self.append_child(segment, name=name, allow_expansion=True)

    def get_segment_at(
        self,
        coord: CoordinateSpec,
    ) -> tuple[int, Timeline, Any]:
        """Return the index, segment, and local timestamp at a coordinate."""
        ts = self.get_timestamp(coord)
        coord_val = float(self._resolve_axis_value(coord))

        for i, seg_id in enumerate(self._segment_order):
            seg_coord = ts.get(seg_id)
            if seg_coord is not None and seg_coord >= 0:
                segment = self._children[seg_id]
                if seg_coord <= segment.length.value:
                    seg_ts = segment.get_timestamp(seg_coord)
                    return (i, segment, seg_ts)

        raise ValueError(f"No segment contains coordinate {coord_val}")

    def get_segment_by_index(self, index: int) -> tuple[Coordinate, Timeline]:
        """Return a segment's offset and timeline by zero-based index."""
        if index < 0 or index >= len(self._segment_order):
            raise IndexError(f"Segment index {index} out of range")

        seg_id = self._segment_order[index]
        return (self._child_offsets[seg_id], self._children[seg_id])

    @property
    def n_segments(self) -> int:
        """Number of segments."""
        return len(self._segment_order)

    def list_segments(self) -> list[str]:
        """Return segment IDs in insertion order."""
        return list(self._segment_order)

    def has_segment(self, segment_id: str) -> bool:
        """Return whether a segment ID exists."""
        return segment_id in self._segment_order

    def __contains__(self, item: Any) -> bool:
        """Return whether a region, child, or segment belongs to this line."""
        if isinstance(item, str):
            return (
                item in self._regions
                or item in self._children
                or item in self._segment_order
            )
        return super().__contains__(item)

    def iter_segments(self) -> Iterator[tuple[int, Coordinate, Timeline]]:
        """Yield each segment's index, offset, and timeline."""
        for i, seg_id in enumerate(self._segment_order):
            yield (i, self._child_offsets[seg_id], self._children[seg_id])

    def get_slice_from_segments(
        self,
        start_id: str,
        end_id: str,
        **kwargs: Any,
    ) -> "Timeline":
        """Slice from the start of one segment through the end of another."""
        if start_id not in self._segment_order:
            raise KeyError(
                f"Segment '{start_id}' not found on SegmentLine '{self._id}'. "
                f"Available segments: {list(self._segment_order)}"
            )
        if end_id not in self._segment_order:
            raise KeyError(
                f"Segment '{end_id}' not found on SegmentLine '{self._id}'. "
                f"Available segments: {list(self._segment_order)}"
            )

        start_idx = self._segment_order.index(start_id)
        end_idx = self._segment_order.index(end_id)

        if start_idx > end_idx:
            raise ValueError(
                f"start_id '{start_id}' (index {start_idx}) comes after "
                f"end_id '{end_id}' (index {end_idx})"
            )

        slice_start = float(self._child_offsets[start_id].value)
        end_seg = self._children[end_id]
        end_offset = float(self._child_offsets[end_id].value)
        slice_end = end_offset + float(end_seg.length.value)

        return self.get_slice(slice_start, slice_end, **kwargs)

    def get_slice(
        self,
        start: CoordinateSpec,
        end: CoordinateSpec,
        *,
        truncate_events: bool = True,
        include_children: bool = True,
        copy_cmaps: bool = True,
    ) -> "Timeline":
        """Extract a slice while preserving the parameterized line class."""
        # Coerce to native number type
        start_value = self._resolve_axis_value(start)
        end_value = self._resolve_axis_value(end)
        nt = self._number_type
        if nt == NumberType.fraction:
            s = Fraction(start_value)
            e = Fraction(end_value)
        elif nt == NumberType.int:
            s = int(start_value)
            e = int(end_value)
        else:
            s = float(start_value)
            e = float(end_value)

        # Validate
        if s >= e:
            raise ValueError(f"start ({s}) must be less than end ({e})")
        if s < 0:
            raise ValueError(
                f"start ({s}) is outside timeline bounds " f"[0, {self._length.value})"
            )
        if e > self._length.value:
            raise ValueError(
                f"end ({e}) is outside timeline bounds " f"[0, {self._length.value}]"
            )

        sliced = type(self)(
            length=0,
            unit=self._unit,
            number_type=self._number_type,
        )

        # Copy events (SegmentLines usually have none, but handle it)
        self._copy_events_to_slice(sliced, s, e, truncate_events)

        # Recursively slice children (segments)
        if include_children:
            self._copy_children_to_slice(sliced, s, e)

        # Copy conversion maps
        if copy_cmaps:
            self._copy_cmaps_to_slice(sliced, s, e)

        # If no children were added (slice falls between segments) the
        # length is still 0.  Set it to the expected slice length so
        # the caller gets a correctly-sized timeline.
        expected_length = e - s
        if sliced._length.value < expected_length:
            sliced._length = Coordinate(expected_length, self._unit)

        return sliced

    def _typed_class(self) -> type[Timeline]:
        """Return a line parameterized by the recursively typed child class."""
        if self._children:
            first_child = next(iter(self._children.values()))
            child_class = first_child._typed_class()
            return SegmentLine[child_class]
        if type(self) is not SegmentLine:
            return type(self)
        return Timeline.resolve_subclass(self.unit, self.number_type)

    def to_timeline(self) -> Timeline:
        """Return the parameter timeline type without segment enforcement."""
        target_class = self.segment_type
        if target_class is None:
            target_class = Timeline.resolve_subclass(self.unit, self.number_type)

        initial_length = (
            0 if issubclass(target_class, SegmentLineMixin) else self._length.value
        )
        timeline = target_class(
            length=initial_length,
            unit=self._unit,
            number_type=self._number_type,
            uid=self._id,
            name=self._name,
            locked=False,
            meta=dict(self._meta) if self._meta else None,
        )
        events = [
            dict(event)
            for event in self._events
            if event.get("event_type") != "Segment"
        ]
        if events:
            timeline._add_events_unchecked(events)
        timeline._external_references = self._external_references
        for child_id, child in self._children.items():
            timeline.add_child(
                child,
                offset=self._child_offsets[child_id],
                allow_expansion=isinstance(timeline, SegmentLineMixin),
            )
        for cmap in self._conversion_maps.values():
            timeline.add_conversion_map(cmap)
        timeline._regions.update(self._regions)
        timeline._flow_maps.update(self._flow_maps)
        timeline._length = timeline._make_coordinate(self._length.value)
        timeline._locked = self._locked
        return timeline

    def concatenate_cmaps(
        self,
        target_unit: TimeUnit,
    ) -> Any:
        """Concatenate every segment's map to a target unit."""
        from timetoalign.maps import PiecewiseMap

        pieces = []
        cumulative_offset = 0.0

        for i, offset, segment in self.iter_segments():
            cmap = segment.get_conversion_map(target_unit)
            if cmap is None:
                raise ValueError(
                    f"Segment '{segment.id}' has no C-map to {target_unit}"
                )

            segment_start = float(offset.value)
            segment_end = segment_start + float(segment.length.value)
            pieces.append(
                {
                    "start": segment_start,
                    "end": segment_end,
                    "map": cmap,
                    "offset": cumulative_offset,
                }
            )

            converted_length = cmap(segment.length.value)
            cumulative_offset += float(converted_length)

        return PiecewiseMap.from_segments(
            pieces=pieces,
            source_unit=self.unit,
            target_unit=target_unit,
        )


class SegmentLine(SegmentLineMixin, Timeline):
    """A timeline whose cached parameterized classes inherit the segment API."""

    _parameter_cache: ClassVar[dict[type[Timeline], type["SegmentLine"]]] = {}

    @classmethod
    def __class_getitem__(cls, segment_type: type[Timeline]) -> type["SegmentLine"]:
        """Return the cached dynamic class for a strict Timeline subclass."""
        if cls is not SegmentLine:
            raise TypeError("Only bare SegmentLine can be parameterized")
        if (
            not isinstance(segment_type, type)
            or not issubclass(segment_type, Timeline)
            or segment_type is Timeline
            or segment_type is SegmentLine
        ):
            raise TypeError(
                "SegmentLine parameter must be a strict Timeline subclass "
                "other than bare SegmentLine"
            )

        cached = cls._parameter_cache.get(segment_type)
        if cached is not None:
            return cached

        name = f"SegmentLine[{segment_type.__name__}]"
        attributes = {"_segment_type": segment_type, "__module__": __name__}
        try:
            parameterized = type(name, (SegmentLine, segment_type), attributes)
        except TypeError:
            if not issubclass(segment_type, SegmentLine):
                raise
            parameterized = type(name, (segment_type,), attributes)
        cls._parameter_cache[segment_type] = parameterized
        return parameterized

    @classmethod
    def from_segmentation(
        cls,
        source: Timeline,
        split_coords: list[CoordinateSpec],
        copy_events: bool = True,
    ) -> "SegmentLine":
        """Create a parameterized line from slices of an unchanged source.

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
            TypeError: If a parameterized receiver does not match the source.
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

        coords = sorted(
            float(source._resolve_axis_value(coord)) for coord in split_coords
        )
        source_class = type(source)

        if cls is SegmentLine:
            line_class = SegmentLine[source_class]
        elif cls._segment_type is not source_class:
            raise TypeError(
                f"{cls.__name__}.from_segmentation() requires source type "
                f"{cls._segment_type.__name__}, got {source_class.__name__}"
            )
        else:
            line_class = cls

        segment_line = line_class(
            length=0,
            unit=source.unit,
            number_type=source.number_type,
        )

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
                events_in_range = source.get_events(
                    min_coord=start,
                    max_coord=end,
                )

                adjusted_events = []
                for event in events_in_range:
                    adjusted = dict(event)
                    for coord_col in ("instant", "start", "end"):
                        val = adjusted.get(coord_col)
                        if val is not None:
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


def __getattr__(name: str) -> Any:
    """Materialize a serialized dynamic class requested by pickle."""
    if name.startswith("SegmentLine[") and name.endswith("]"):
        try:
            resolved = Timeline._resolve_serialized_class_hierarchy(name)
        except (TypeError, ValueError) as error:
            raise AttributeError(name) from error
        if resolved.__name__ == name:
            return resolved
    raise AttributeError(name)
