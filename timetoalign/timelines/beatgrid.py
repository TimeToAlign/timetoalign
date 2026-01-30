"""BeatGrid: A metrical timeline measured in quarter notes.

A BeatGrid is a ContinuousLogicalTimeline that represents metrical structure
(measures, beats) using quarter-note coordinates. It can be added as a child
to any parent timeline to provide metrical information.

Key features:
- Coordinate system in quarters (Fractions for exact representation)
- Built-in C-Maps: quarters -> measure_number, quarters -> beat_in_measure
- CombinationMap for (measure, beat) tuple output
- Optional materialization of Beat and Measure events
- Factory method for creation from tempo information
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, ClassVar

from timetoalign.core import NumberType, TimeUnit
from timetoalign.maps import CombinationMap, LinearMap
from timetoalign.maps.periodic import FloorMap, RotationMap

from .types import ContinuousLogicalTimeline


class BeatGrid(ContinuousLogicalTimeline):
    """A metrical grid as a ContinuousLogicalTimeline in quarters.

    A BeatGrid represents metrical structure: measures, beats, and their
    numbering. It is designed to be added as a child to any parent timeline
    (physical, logical, or graphical).

    The coordinate system uses quarter notes (Fractions) for exact rhythmic
    representation. Built-in C-Maps automatically convert quarters to
    measure numbers and beat positions.

    Attributes:
        beats_per_measure: Number of beats per measure.
        beat_unit: The note value of one beat (e.g., Fraction(1, 4) for quarter note).
        start_measure: The number of the first measure (default 1).
        quarters_per_measure: Derived: quarters per measure.

    C-Maps (automatically created):
        - quarters -> measures (FloorMap): Integer measure numbers
        - quarters -> beats (RotationMap): Beat position within measure (1-indexed)
        - quarters -> (measure, beat) (CombinationMap): Combined tuple output

    Examples:
        >>> from fractions import Fraction
        >>> from timetoalign import ContinuousPhysicalTimeline, TimeUnit
        >>>
        >>> # Create a beat grid for 4/4 time, 222 measures
        >>> grid = BeatGrid(
        ...     length=Fraction(888, 1),  # 888 quarter notes
        ...     beats_per_measure=4,
        ... )
        >>>
        >>> # Query measure and beat at quarter 100
        >>> grid.measure_at(100)  # -> 26 (measure 26)
        >>> grid.beat_at(100)     # -> 1.0 (beat 1)
        >>> grid.metrical_position(100)  # -> {"measure": 26, "beat": 1.0}
        >>>
        >>> # Attach to audio timeline
        >>> audio = ContinuousPhysicalTimeline(length=300.0, unit=TimeUnit.seconds)
        >>> audio.add_child(grid, offset=1.3)  # First beat at 1.3 seconds
        >>>
        >>> # Create from tempo
        >>> grid2 = BeatGrid.from_tempo(
        ...     tempo_bpm=120.0,
        ...     beats_per_measure=4,
        ...     length_quarters=Fraction(888, 1),
        ... )
    """

    # Force quarters unit and Fraction number type
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters
    _default_number_type: ClassVar[NumberType] = NumberType.fraction

    def __init__(
        self,
        length: Fraction | int,
        beats_per_measure: int = 4,
        beat_unit: Fraction = Fraction(1, 4),
        start_measure: int = 1,
        uid: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize a BeatGrid.

        Args:
            length: Length in quarter notes (Fraction or int).
            beats_per_measure: Number of beats per measure. Default 4.
            beat_unit: Note value of one beat. Default Fraction(1, 4) (quarter note).
                       Use Fraction(1, 8) for eighth-note beats (e.g., 6/8 time).
            start_measure: Number of the first measure. Default 1.
            uid: Explicit unique identifier.
            name: Human-readable name.

        Raises:
            ValueError: If beats_per_measure < 1 or beat_unit <= 0.
        """
        if beats_per_measure < 1:
            raise ValueError(f"beats_per_measure must be >= 1, got {beats_per_measure}")
        if beat_unit <= 0:
            raise ValueError(f"beat_unit must be positive, got {beat_unit}")

        # Convert length to Fraction
        if isinstance(length, int):
            length = Fraction(length, 1)

        # Initialize parent
        super().__init__(
            length=length,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            uid=uid,
            name=name,
        )

        # Store metrical parameters
        self._beats_per_measure = beats_per_measure
        self._beat_unit = Fraction(beat_unit)
        self._start_measure = start_measure

        # Calculate quarters per measure
        # beat_unit is the fraction of a whole note that equals one beat
        # e.g., 1/4 means quarter note = 1 beat
        # quarters per beat = (1/4) / beat_unit = 1 / (4 * beat_unit)
        # Actually: if beat_unit = 1/4, then 1 beat = 1 quarter
        #           if beat_unit = 1/8, then 1 beat = 0.5 quarters
        # quarters_per_beat = beat_unit * 4 (since 4 quarters = 1 whole note)
        self._quarters_per_beat = self._beat_unit * 4
        self._quarters_per_measure = self._quarters_per_beat * beats_per_measure

        # Create and attach metrical C-Maps
        self._setup_metrical_cmaps()

    @property
    def beats_per_measure(self) -> int:
        """Number of beats per measure."""
        return self._beats_per_measure

    @property
    def beat_unit(self) -> Fraction:
        """Note value of one beat (fraction of whole note)."""
        return self._beat_unit

    @property
    def start_measure(self) -> int:
        """Number of the first measure."""
        return self._start_measure

    @property
    def quarters_per_measure(self) -> Fraction:
        """Quarter notes per measure."""
        return self._quarters_per_measure

    @property
    def quarters_per_beat(self) -> Fraction:
        """Quarter notes per beat."""
        return self._quarters_per_beat

    @property
    def n_measures(self) -> int:
        """Number of complete measures in this grid."""
        return int(self._length.value // self._quarters_per_measure)

    def _setup_metrical_cmaps(self) -> None:
        """Create and attach the metrical conversion maps."""
        qpm = float(self._quarters_per_measure)
        qpb = float(self._quarters_per_beat)

        # quarters -> measure number (1-indexed by default)
        self._measure_map = FloorMap(
            divisor=qpm,
            base=self._start_measure,
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.measures,
            uid=f"{self.id}_measure_map",
        )
        self.add_conversion_map(self._measure_map)

        # quarters -> beat in measure (1-indexed, using rotation)
        # First normalize quarters to within-measure position, then convert to beats
        # beat = (quarters % qpm) / qpb + 1
        # RotationMap: ((input - offset) % period) * scale + base
        # We need: ((quarters - 0) % qpm) * (1/qpb) + 1
        self._beat_map = RotationMap(
            period=qpm,
            scale=1.0 / qpb,  # Convert quarter position to beat position
            base=1.0,  # 1-indexed
            offset=0.0,
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.beats,
            uid=f"{self.id}_beat_map",
        )
        self.add_conversion_map(self._beat_map)

        # Combined map for (measure, beat) tuple
        self._metrical_map = CombinationMap(
            maps={"measure": self._measure_map, "beat": self._beat_map},
            source_unit=TimeUnit.quarters,
            uid=f"{self.id}_metrical_map",
        )
        self.add_conversion_map(self._metrical_map)

    def measure_at(self, quarters: float | Fraction) -> int:
        """Get the measure number at a given quarter-note position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            The measure number (1-indexed by default).
        """
        return self._measure_map(float(quarters))

    def beat_at(self, quarters: float | Fraction) -> float:
        """Get the beat position within the measure at a given quarter-note position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            The beat position (1-indexed, may be fractional).
        """
        return self._beat_map(float(quarters))

    def metrical_position(self, quarters: float | Fraction) -> dict[str, Any]:
        """Get the full metrical position (measure and beat) at a given quarter position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            Dictionary with 'measure' and 'beat' keys.
        """
        return self._metrical_map(float(quarters))

    def quarter_at(self, measure: int, beat: float = 1.0) -> Fraction:
        """Get the quarter-note position for a given measure and beat.

        Args:
            measure: Measure number (uses start_measure as reference).
            beat: Beat within the measure (1-indexed). Default 1.0.

        Returns:
            Position in quarter notes.

        Raises:
            ValueError: If measure < start_measure or beat < 1.
        """
        if measure < self._start_measure:
            raise ValueError(
                f"Measure {measure} is before start_measure {self._start_measure}"
            )
        if beat < 1:
            raise ValueError(f"Beat must be >= 1, got {beat}")

        # Calculate quarters from measure and beat
        measure_offset = (measure - self._start_measure) * self._quarters_per_measure
        beat_offset = Fraction(beat - 1) * self._quarters_per_beat
        return measure_offset + beat_offset

    def materialize_beats(
        self,
        include_downbeats_only: bool = False,
    ) -> int:
        """Add Beat events to this timeline at each beat position.

        Args:
            include_downbeats_only: If True, only create events for beat 1 (downbeats).

        Returns:
            Number of beat events created.
        """
        events = []
        position = Fraction(0, 1)

        while position < self._length.value:
            beat = self.beat_at(position)
            measure = self.measure_at(position)

            # Check if we should include this beat
            is_downbeat = abs(beat - 1.0) < 0.001  # Beat 1 (floating point tolerance)
            if include_downbeats_only and not is_downbeat:
                position += self._quarters_per_beat
                continue

            events.append(
                {
                    "id": f"beat_{len(events)}",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": float(position),
                    "measure": measure,
                    "beat_in_measure": beat,
                    "is_downbeat": is_downbeat,
                }
            )

            position += self._quarters_per_beat

        if events:
            self.add_events(events)

        return len(events)

    def materialize_measures(self) -> int:
        """Add Measure events to this timeline at each measure boundary.

        Creates IntervalEvents for each complete measure.

        Returns:
            Number of measure events created.
        """
        events = []
        position = Fraction(0, 1)
        measure_num = self._start_measure

        while position + self._quarters_per_measure <= self._length.value:
            events.append(
                {
                    "id": f"measure_{measure_num}",
                    "temporal_type": "interval",
                    "event_type": "Measure",
                    "start": float(position),
                    "end": float(position + self._quarters_per_measure),
                    "measure_number": measure_num,
                }
            )

            position += self._quarters_per_measure
            measure_num += 1

        # Handle final partial measure if present
        if position < self._length.value:
            events.append(
                {
                    "id": f"measure_{measure_num}",
                    "temporal_type": "interval",
                    "event_type": "Measure",
                    "start": float(position),
                    "end": float(self._length.value),
                    "measure_number": measure_num,
                    "is_partial": True,
                }
            )

        if events:
            self.add_events(events)

        return len(events)

    @classmethod
    def from_tempo(
        cls,
        tempo_bpm: float,
        beats_per_measure: int = 4,
        beat_unit: Fraction = Fraction(1, 4),
        length_seconds: float | None = None,
        length_quarters: Fraction | int | None = None,
        start_measure: int = 1,
        uid: str | None = None,
        name: str | None = None,
    ) -> BeatGrid:
        """Create a BeatGrid from tempo information.

        You must provide either length_seconds or length_quarters.

        Args:
            tempo_bpm: Tempo in beats per minute.
            beats_per_measure: Number of beats per measure. Default 4.
            beat_unit: Note value of one beat. Default 1/4 (quarter note).
            length_seconds: Duration in seconds (converted using tempo).
            length_quarters: Duration in quarter notes.
            start_measure: Number of the first measure. Default 1.
            uid: Explicit unique identifier.
            name: Human-readable name.

        Returns:
            A new BeatGrid instance.

        Raises:
            ValueError: If neither length_seconds nor length_quarters is provided.
            ValueError: If both length_seconds and length_quarters are provided.
        """
        if length_seconds is None and length_quarters is None:
            raise ValueError("Must provide either length_seconds or length_quarters")
        if length_seconds is not None and length_quarters is not None:
            raise ValueError("Cannot provide both length_seconds and length_quarters")

        # Calculate length in quarters
        if length_quarters is not None:
            if isinstance(length_quarters, int):
                length = Fraction(length_quarters, 1)
            else:
                length = length_quarters
        else:
            # Convert seconds to quarters using tempo
            # tempo_bpm = beats per minute
            # quarters_per_beat = beat_unit * 4
            # beats_per_second = tempo_bpm / 60
            # quarters_per_second = beats_per_second * quarters_per_beat
            quarters_per_beat = Fraction(beat_unit) * 4
            beats_per_second = tempo_bpm / 60.0
            quarters_per_second = float(quarters_per_beat) * beats_per_second
            length = Fraction(length_seconds * quarters_per_second).limit_denominator(
                10000
            )

        grid = cls(
            length=length,
            beats_per_measure=beats_per_measure,
            beat_unit=beat_unit,
            start_measure=start_measure,
            uid=uid,
            name=name,
        )

        # Store tempo for reference
        grid._tempo_bpm = tempo_bpm

        # Create a tempo C-Map: quarters -> seconds
        # seconds = quarters / quarters_per_second
        quarters_per_beat = Fraction(beat_unit) * 4
        beats_per_second = tempo_bpm / 60.0
        quarters_per_second = float(quarters_per_beat) * beats_per_second

        tempo_map = LinearMap(
            scalar=1.0 / quarters_per_second,
            offset=0.0,
            source_unit=TimeUnit.quarters,
            target_unit=TimeUnit.seconds,
            uid=f"{grid.id}_tempo_map",
        )
        grid.add_conversion_map(tempo_map)
        grid._tempo_map = tempo_map

        return grid

    @property
    def tempo_bpm(self) -> float | None:
        """Tempo in BPM, if created via from_tempo()."""
        return getattr(self, "_tempo_bpm", None)

    def __repr__(self) -> str:
        return (
            f"BeatGrid(length={self._length.value}, "
            f"beats_per_measure={self._beats_per_measure}, "
            f"measures={self.n_measures})"
        )
