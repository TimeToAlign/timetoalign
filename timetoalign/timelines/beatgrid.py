"""BeatGrid: a metrical timeline measured in quarter notes.

BeatGrid is the timeline-shaped face of musical meter. It is a
ContinuousLogicalTimeline whose measure and beat structure is carried by an
attached meter-map family: MetricMap supplies measure boundaries,
BeatInMeasureMap supplies beat-in-measure conversion, and MetricalPositionMap
combines those values.

BeatGrid and MetricMap converge as metrical conversion becomes more capable.
MetricMap already represents irregular measures, anacrusis, and meter changes
through ``from_boundaries()``; that richer structure is intended to flow into
BeatGrid over time. BeatGrid keeps the timeline responsibilities of events,
regions, hierarchy, and cross-domain conversion while exposing metrical queries
on an exact quarter-note axis.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from timetoalign.core import CoordinateSpec, NumberType, TimeUnit
from timetoalign.maps import ConversionMap, LinearMap
from timetoalign.maps.meter import BeatInMeasureMap, MetricalPositionMap, MetricMap

from .base import SEGMENT_EVENT_TYPE
from .types import ContinuousLogicalTimeline

if TYPE_CHECKING:
    from numpy.typing import NDArray


class BeatGrid(ContinuousLogicalTimeline):
    """A metrical timeline whose native coordinate axis is quarter notes.

    BeatGrid delegates measure-boundary lookup to its attached MetricMap,
    beat-in-measure lookup to its attached BeatInMeasureMap, and combined
    measure/beat lookup to its attached MetricalPositionMap. Its public beat
    queries also apply ``beat_unit`` so that a musical beat need not equal a
    quarter note.

    BeatGrid and MetricMap are converging representations of meter. BeatGrid
    provides the Timeline interface; MetricMap provides an increasingly rich
    conversion model. Irregular measures, anacrusis, and meter changes modeled
    by ``MetricMap.from_boundaries()`` are intended to become available through
    BeatGrid as that model develops.

    Attributes:
        beats_per_measure: Number of beats per measure.
        beat_unit: The note value of one beat (e.g., Fraction(1, 4) for quarter note).
        start_measure: The number of the first measure (default 1).
        quarters_per_measure: Derived: quarters per measure.

    C-Maps (automatically created):
        - quarters -> mc (MetricMap): Integer measure count.
        - quarters -> beat (BeatInMeasureMap): Beat position as Fraction.
        - quarters -> {mc, beat} (MetricalPositionMap): Combined output.

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
        >>> grid.measure_at(100)  # -> 26 (integer!)
        >>> grid.beat_at(100)     # -> Fraction(1, 1) (proper Fraction!)
        >>> grid.metrical_position(100)  # -> {"mc": 26, "beat": Fraction(1, 1)}
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

    # Instance attributes (set in __init__ or from_tempo)
    _beats_per_measure: int
    _beat_unit: Fraction
    _start_measure: int
    _start_mn: str
    _anacrusis_quarters: Fraction | None
    _quarters_per_beat: Fraction
    _quarters_per_measure: Fraction
    _n_measures: int
    _meter_map: MetricMap
    _beat_map: BeatInMeasureMap
    _metrical_map: MetricalPositionMap

    # Optional attributes (only set when using from_tempo)
    _tempo_bpm: float | None
    _start_seconds: float
    _tempo_map: LinearMap | None

    def __init__(
        self,
        length: Fraction | int,
        beats_per_measure: int = 4,
        beat_unit: Fraction = Fraction(1, 4),
        start_measure: int = 1,
        start_mn: str | None = None,
        anacrusis_quarters: Fraction | None = None,
        uid: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize a BeatGrid.

        Args:
            length: Length in quarter notes (Fraction or int).
            beats_per_measure: Number of beats per measure. Default 4.
            beat_unit: Note value of one beat. Default Fraction(1, 4) (quarter note).
                       Use Fraction(1, 8) for eighth-note beats (e.g., 6/8 time).
            start_measure: MC (measure count) of the first measure. Default 1.
            start_mn: MN (measure number label) of the first measure.
                     Default: same as start_measure. Use "0" for anacrusis.
            anacrusis_quarters: If set, the first measure is shorter (pickup).
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
        self._start_mn = start_mn if start_mn is not None else str(start_measure)
        self._anacrusis_quarters = anacrusis_quarters

        # Calculate quarters per measure/beat
        # beat_unit is the fraction of a whole note that equals one beat
        # quarters_per_beat = beat_unit * 4 (since 4 quarters = 1 whole note)
        self._quarters_per_beat = self._beat_unit * 4
        self._quarters_per_measure = self._quarters_per_beat * beats_per_measure

        # Calculate number of measures
        if anacrusis_quarters is not None:
            remaining = length - anacrusis_quarters
            n_full = int(remaining // self._quarters_per_measure)
            self._n_measures = 1 + n_full
        else:
            self._n_measures = int(length // self._quarters_per_measure)
            if self._n_measures == 0:
                self._n_measures = 1

        # Initialize optional tempo attributes (set by from_tempo())
        self._tempo_bpm = None
        self._start_seconds = 0.0
        self._tempo_map = None

        # Create and attach metrical C-Maps using the new MetricMap infrastructure
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
        """MC (measure count) of the first measure."""
        return self._start_measure

    @property
    def start_mn(self) -> str:
        """MN (measure number label) of the first measure."""
        return self._start_mn

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
        return self._n_measures

    def _setup_metrical_cmaps(self) -> None:
        """Create and attach the metrical conversion maps using MetricMap."""
        # Create the MetricMap with uniform measure lengths
        self._meter_map = MetricMap.from_uniform(
            n_measures=self._n_measures,
            quarters_per_measure=self._quarters_per_measure,
            start_mc=self._start_measure,
            start_mn=self._start_mn,
            anacrusis_quarters=self._anacrusis_quarters,
            uid=f"{self.id}_meter_map",
        )
        self.add_conversion_map(self._meter_map)

        # Create the BeatInMeasureMap
        self._beat_map = BeatInMeasureMap(
            self._meter_map,
            uid=f"{self.id}_beat_map",
        )
        self.add_conversion_map(self._beat_map)

        # Create the MetricalPositionMap (combination of both)
        self._metrical_map = MetricalPositionMap(
            self._meter_map,
            uid=f"{self.id}_metrical_map",
        )
        self.add_conversion_map(self._metrical_map)

    def _resolve_quarter_value(
        self, quarters: CoordinateSpec
    ) -> int | float | Fraction:
        """Resolve a public query coordinate to the native quarter-note axis."""
        if isinstance(quarters, np.generic):
            quarters = quarters.item()
        return self._resolve_axis_value(quarters)

    def measure_at(self, quarters: CoordinateSpec) -> int:
        """Get the measure count (MC) at a given quarter-note position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            The measure count (integer, 1-indexed by default).
        """
        quarter_value = self._resolve_quarter_value(quarters)
        return self._meter_map(float(quarter_value))

    def mn_at(self, quarters: CoordinateSpec) -> str | None:
        """Get the measure number label (MN) at a given quarter-note position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            The measure number label (string like "1", "0", "1a").
        """
        quarter_value = self._resolve_quarter_value(quarters)
        mc = self._meter_map(float(quarter_value))
        return self._meter_map.get_mn(mc)

    def beat_at(self, quarters: CoordinateSpec) -> Fraction:
        """Get the beat position within the measure at a given quarter-note position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            The beat position as Fraction (1-indexed, e.g., Fraction(3, 2) for beat 1.5).
        """
        quarter_value = self._resolve_quarter_value(quarters)
        mc = self._meter_map(float(quarter_value))
        measure = self._meter_map.get_measure_info(mc)
        if measure is None:
            raise ValueError(f"MC {mc} not found in meter map")
        return (
            Fraction(quarter_value) - measure["start"]
        ) / self._quarters_per_beat + 1

    def metrical_position(self, quarters: CoordinateSpec) -> dict[str, Any]:
        """Get the full metrical position (mc and beat) at a given quarter position.

        Args:
            quarters: Position in quarter notes.

        Returns:
            Dictionary with 'mc' (int), 'beat' (Fraction), and 'mn' (str) keys.
        """
        quarter_value = self._resolve_quarter_value(quarters)
        mc = self._meter_map(float(quarter_value))
        beat = self.beat_at(quarter_value)
        return {"mc": mc, "beat": beat, "mn": self._meter_map.get_mn(mc)}

    def quarter_at(
        self, measure: int, beat: float | Fraction = Fraction(1, 1)
    ) -> Fraction:
        """Get the quarter-note position for a given measure and beat.

        Args:
            measure: Measure count (MC, uses start_measure as reference).
            beat: Beat within the measure (1-indexed). Default Fraction(1, 1).

        Returns:
            Position in quarter notes.

        Raises:
            ValueError: If measure < start_measure or beat < 1.
        """
        measure_info = self._meter_map.get_measure_info(measure)
        if measure_info is None:
            raise ValueError(f"MC {measure} not found in meter map")
        return measure_info["start"] + (Fraction(beat) - 1) * self._quarters_per_beat

    def to_dict(self) -> dict[str, Any]:
        """Convert the grid and its construction parameters to a dictionary.

        Returns:
            A dictionary representation that reconstructs the attached meter maps.
        """
        data = super().to_dict()
        data["beats_per_measure"] = self._beats_per_measure
        data["beat_unit"] = str(self._beat_unit)
        data["start_measure"] = self._start_measure
        data["start_mn"] = self._start_mn
        data["anacrusis_quarters"] = (
            str(self._anacrusis_quarters)
            if self._anacrusis_quarters is not None
            else None
        )
        data["tempo_bpm"] = self._tempo_bpm
        data["start_seconds"] = self._start_seconds
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeatGrid:
        """Create a BeatGrid from a serialized dictionary.

        The constructor recreates the meter-map family. Serialized meter maps
        are skipped so they are not attached a second time.

        Args:
            data: Dictionary created by :meth:`to_dict`.

        Returns:
            The reconstructed BeatGrid.
        """
        anacrusis = data.get("anacrusis_quarters")
        grid = cls(
            length=Fraction(data["length"]),
            beats_per_measure=data["beats_per_measure"],
            beat_unit=Fraction(data["beat_unit"]),
            start_measure=data["start_measure"],
            start_mn=data["start_mn"],
            anacrusis_quarters=Fraction(anacrusis) if anacrusis is not None else None,
            uid=data["id"],
            name=data.get("name"),
        )
        grid._locked = data.get("locked", False)
        grid._meta = dict(data.get("meta") or {})

        events = []
        for serialized_event in data.get("events", []):
            if serialized_event.get("event_type") == SEGMENT_EVENT_TYPE:
                continue
            event = dict(serialized_event)
            for coord_col in ("instant", "start", "end", "duration"):
                coord = event.get(coord_col)
                if isinstance(coord, dict) and "value" in coord:
                    event[coord_col] = coord["value"]
            events.append(event)
        if events:
            grid._add_events_unchecked(events)

        for child_data in data.get("children", {}).values():
            child = cls.from_dict(child_data["timeline"])
            grid.add_child(child, offset=child_data["offset"])

        meter_map_ids = {grid._meter_map.id, grid._beat_map.id, grid._metrical_map.id}
        for map_data in data.get("conversion_maps", []):
            if map_data.get("id") in meter_map_ids:
                continue
            cmap = ConversionMap.from_dict(map_data)
            grid.add_conversion_map(cmap)
            if cmap.target_unit == TimeUnit.seconds:
                grid._tempo_map = cmap  # type: ignore[assignment]

        tempo_bpm = data.get("tempo_bpm")
        if tempo_bpm is not None:
            grid._tempo_bpm = tempo_bpm
            grid._start_seconds = data.get("start_seconds", 0.0)

        return grid

    # region Vectorized Accessors

    @property
    def n_beats(self) -> int:
        """Total number of beats in this grid."""
        return int(float(self._length.value) / float(self._quarters_per_beat))

    def beat_quarters(self) -> "NDArray[np.floating[Any]]":
        """All beat positions in quarters. Vectorized O(1).

        Returns:
            numpy array of beat positions in quarter notes.

        Examples:
            >>> grid = BeatGrid(length=16, beats_per_measure=4)
            >>> grid.beat_quarters()
            array([ 0.,  1.,  2.,  3.,  4.,  5., ...])
        """
        return np.arange(self.n_beats, dtype=np.float64) * float(
            self._quarters_per_beat
        )

    def measure_quarters(self) -> "NDArray[np.floating[Any]]":
        """All measure start positions in quarters. Vectorized O(1).

        Returns:
            numpy array of measure start positions in quarter notes.

        Examples:
            >>> grid = BeatGrid(length=16, beats_per_measure=4)
            >>> grid.measure_quarters()
            array([ 0.,  4.,  8., 12.])
        """
        return np.arange(self._n_measures, dtype=np.float64) * float(
            self._quarters_per_measure
        )

    def beat_seconds(self) -> "NDArray[np.floating[Any]]":
        """All beat times in seconds. Vectorized O(1).

        Requires the grid to have been created with from_tempo() and start_seconds,
        or to have a tempo_map attached.

        Returns:
            numpy array of beat times in seconds.

        Raises:
            RuntimeError: If no tempo information is available.

        Examples:
            >>> grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=60, start_seconds=0.5)
            >>> grid.beat_seconds()[:4]
            array([0.5 , 1.0 , 1.5 , 2.0 ])
        """
        if not hasattr(self, "_tempo_bpm") or self._tempo_bpm is None:
            raise RuntimeError(
                "beat_seconds() requires tempo. Use from_tempo() to create the grid."
            )
        start = getattr(self, "_start_seconds", 0.0)
        beat_duration = 60.0 / self._tempo_bpm * float(self._quarters_per_beat)
        return start + np.arange(self.n_beats, dtype=np.float64) * beat_duration

    def measure_seconds(self) -> "NDArray[np.floating[Any]]":
        """All measure start times in seconds. Vectorized O(1).

        Requires the grid to have been created with from_tempo() and start_seconds,
        or to have a tempo_map attached.

        Returns:
            numpy array of measure start times in seconds.

        Raises:
            RuntimeError: If no tempo information is available.

        Examples:
            >>> grid = BeatGrid.from_tempo(tempo_bpm=120, beats_per_measure=4,
            ...                            length_seconds=60, start_seconds=0.5)
            >>> grid.measure_seconds()[:4]
            array([0.5 , 2.5 , 4.5 , 6.5 ])
        """
        if not hasattr(self, "_tempo_bpm") or self._tempo_bpm is None:
            raise RuntimeError(
                "measure_seconds() requires tempo. Use from_tempo() to create the grid."
            )
        start = getattr(self, "_start_seconds", 0.0)
        measure_duration = 60.0 / self._tempo_bpm * float(self._quarters_per_measure)
        return start + np.arange(self._n_measures, dtype=np.float64) * measure_duration

    def downbeat_seconds(self) -> "NDArray[np.floating[Any]]":
        """Alias for measure_seconds(). All downbeat times in seconds."""
        return self.measure_seconds()

    def measure_at_seconds(self, seconds: float) -> int:
        """Get the measure number at a given time in seconds.

        Args:
            seconds: Time position in seconds.

        Returns:
            Measure count (MC, 1-indexed by default).

        Raises:
            RuntimeError: If no tempo information is available.
            ValueError: If seconds is before the first beat.
        """
        if not hasattr(self, "_tempo_bpm") or self._tempo_bpm is None:
            raise RuntimeError(
                "measure_at_seconds() requires tempo. Use from_tempo() to create the grid."
            )
        start = getattr(self, "_start_seconds", 0.0)
        if seconds < start:
            raise ValueError(f"seconds ({seconds}) is before first beat ({start})")

        measure_duration = 60.0 / self._tempo_bpm * float(self._quarters_per_measure)
        measure_index = int((seconds - start) / measure_duration)
        return self._start_measure + min(measure_index, self._n_measures - 1)

    def beat_at_seconds(self, seconds: float) -> int:
        """Get the beat number within the measure at a given time in seconds.

        Args:
            seconds: Time position in seconds.

        Returns:
            Beat number (1-indexed).

        Raises:
            RuntimeError: If no tempo information is available.
            ValueError: If seconds is before the first beat.
        """
        if not hasattr(self, "_tempo_bpm") or self._tempo_bpm is None:
            raise RuntimeError(
                "beat_at_seconds() requires tempo. Use from_tempo() to create the grid."
            )
        start = getattr(self, "_start_seconds", 0.0)
        if seconds < start:
            raise ValueError(f"seconds ({seconds}) is before first beat ({start})")

        beat_duration = 60.0 / self._tempo_bpm * float(self._quarters_per_beat)
        beat_index = int((seconds - start) / beat_duration)
        beat_in_measure = (beat_index % self._beats_per_measure) + 1
        return beat_in_measure

    # endregion

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
            mc = self.measure_at(position)
            mn = self.mn_at(position)

            # Check if we should include this beat
            is_downbeat = beat == Fraction(1, 1)
            if include_downbeats_only and not is_downbeat:
                position += self._quarters_per_beat
                continue

            events.append(
                {
                    "id": f"beat_{len(events)}",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": float(position),
                    "mc": mc,
                    "mn": mn,
                    "beat": str(beat),  # Store as string to preserve Fraction
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

        for i in range(self._n_measures):
            mc = self._meter_map._mcs[i]
            info = self._meter_map.get_measure_info(int(mc))
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
        start_seconds: float = 0.0,
        start_measure: int = 1,
        start_mn: str | None = None,
        anacrusis_quarters: Fraction | None = None,
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
                If start_seconds > 0, this should be the TOTAL audio duration;
                the grid will span from start_seconds to length_seconds.
            length_quarters: Duration in quarter notes.
            start_seconds: Offset in seconds where the first beat occurs.
                Default 0.0. Used by beat_seconds() and measure_seconds().
            start_measure: MC of the first measure. Default 1.
            start_mn: MN label of the first measure. Default: same as start_measure.
            anacrusis_quarters: If set, first measure is shorter (pickup).
            uid: Explicit unique identifier.
            name: Human-readable name.

        Returns:
            A new BeatGrid instance with vectorized accessors for beat/measure times.

        Raises:
            ValueError: If neither length_seconds nor length_quarters is provided.
            ValueError: If both length_seconds and length_quarters are provided.

        Examples:
            >>> # Audio track: 279 seconds, first beat at 0.092s, 160 BPM, 4/4
            >>> grid = BeatGrid.from_tempo(
            ...     tempo_bpm=160.0,
            ...     beats_per_measure=4,
            ...     length_seconds=279.0,
            ...     start_seconds=0.092,
            ... )
            >>> grid.n_measures
            186
            >>> grid.beat_seconds()[:4]
            array([0.092, 0.467, 0.842, 1.217])
            >>> grid.measure_seconds()[:4]
            array([0.092, 1.592, 3.092, 4.592])
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
            # If start_seconds is provided, grid spans from start_seconds to length_seconds
            effective_duration = length_seconds - start_seconds
            if effective_duration <= 0:
                raise ValueError(
                    f"length_seconds ({length_seconds}) must be greater than "
                    f"start_seconds ({start_seconds})"
                )
            quarters_per_beat = Fraction(beat_unit) * 4
            beats_per_second = tempo_bpm / 60.0
            quarters_per_second = float(quarters_per_beat) * beats_per_second
            length = Fraction(
                effective_duration * quarters_per_second
            ).limit_denominator(10000)

        grid = cls(
            length=length,
            beats_per_measure=beats_per_measure,
            beat_unit=beat_unit,
            start_measure=start_measure,
            start_mn=start_mn,
            anacrusis_quarters=anacrusis_quarters,
            uid=uid,
            name=name,
        )

        # Store tempo and start offset for vectorized accessors
        grid._tempo_bpm = tempo_bpm
        grid._start_seconds = start_seconds

        # Create a tempo C-Map: quarters -> seconds
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

    @property
    def meter_map(self) -> MetricMap:
        """The underlying MetricMap (for advanced access)."""
        return self._meter_map

    def export_to_csv(  # type: ignore[override]
        self,
        filepath: str,
        *,
        format: str = "default",
        labels: str = "beats",
        **kwargs: Any,
    ) -> int:
        """Export BeatGrid data to a CSV file.

        Extends the base Timeline.export_to_csv() with special formats for
        audio annotation tools.

        Args:
            filepath: Output CSV file path.
            format: Output format. Options:
                - "default": Standard timestamp table (inherited behavior).
                - "sonic_visualiser": Sonic Visualiser / Audacity label track.
                  Two fields (TIME, LABEL) with header row.
                - "tilia": Tilia beat track format.
                  Four fields (time, measure, beat, is_first_in_measure).
            labels: What to export when using "sonic_visualiser" format:
                - "beats": All beat positions with labels like "M1B1", "M1B2".
                - "measures": Measure start positions with labels like "M1", "M2".
                - "both": Both beats and measures.
            **kwargs: Additional arguments passed to base export_to_csv() when
                using "default" format.

        Returns:
            Number of rows written.

        Raises:
            RuntimeError: If format requires tempo but none is available.
            ValueError: If format is not recognized.

        Examples:
            >>> grid = BeatGrid.from_tempo(tempo_bpm=120, length_seconds=60)

            >>> # Export for Sonic Visualiser
            >>> grid.export_to_csv("beats.csv", format="sonic_visualiser")
            120

            >>> # Export for Tilia
            >>> grid.export_to_csv("beats.csv", format="tilia")
            120

            >>> # Standard timestamp table
            >>> grid.export_to_csv("data.csv", format="default")
            120
        """
        if format == "default":
            return super().export_to_csv(filepath, **kwargs)

        if format not in ("sonic_visualiser", "tilia"):
            raise ValueError(
                f"Unknown format '{format}'. "
                "Use 'default', 'sonic_visualiser', or 'tilia'."
            )

        # Both formats require tempo for seconds conversion
        if not hasattr(self, "_tempo_bpm") or self._tempo_bpm is None:
            raise RuntimeError(
                f"export_to_csv() with format='{format}' requires tempo. "
                "Use BeatGrid.from_tempo() to create the grid."
            )

        if format == "tilia":
            return self._export_tilia(filepath)

        # sonic_visualiser format
        return self._export_sonic_visualiser(filepath, labels)

    def _export_sonic_visualiser(self, filepath: str, labels: str) -> int:
        """Export in Sonic Visualiser format (TIME, LABEL fields with header)."""
        import pandas as pd

        dfs = []

        if labels in ("beats", "both"):
            times = self.beat_seconds()
            n_times = len(times)
            n_measures_needed = (
                n_times + self._beats_per_measure - 1
            ) // self._beats_per_measure
            measures = np.repeat(
                np.arange(self._start_measure, self._start_measure + n_measures_needed),
                self._beats_per_measure,
            )[:n_times]
            beats = np.tile(
                np.arange(1, self._beats_per_measure + 1), n_measures_needed
            )[:n_times]
            dfs.append(
                pd.DataFrame(
                    {
                        "TIME": np.round(times, 6),
                        "LABEL": [f"M{m}B{b}" for m, b in zip(measures, beats)],
                    }
                )
            )

        if labels in ("measures", "both"):
            times = self.measure_seconds()
            dfs.append(
                pd.DataFrame(
                    {
                        "TIME": np.round(times, 6),
                        "LABEL": [
                            f"M{m}"
                            for m in range(
                                self._start_measure,
                                self._start_measure + len(times),
                            )
                        ],
                    }
                )
            )

        if not dfs:
            raise ValueError(
                f"Unknown labels '{labels}'. Use 'beats', 'measures', or 'both'."
            )

        df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
        df = df.sort_values("TIME").reset_index(drop=True)
        df.to_csv(filepath, index=False)
        return len(df)

    def _export_tilia(self, filepath: str) -> int:
        """Export in Tilia format (time, measure, beat, is_first_in_measure)."""
        import pandas as pd

        times = self.beat_seconds()
        n_times = len(times)
        n_measures_needed = (
            n_times + self._beats_per_measure - 1
        ) // self._beats_per_measure
        measures = np.repeat(
            np.arange(self._start_measure, self._start_measure + n_measures_needed),
            self._beats_per_measure,
        )[:n_times]
        beats = np.tile(np.arange(1, self._beats_per_measure + 1), n_measures_needed)[
            :n_times
        ]

        df = pd.DataFrame(
            {
                "time": np.round(times, 6),
                "measure": measures,
                "beat": beats,
                "is_first_in_measure": beats == 1,
            }
        )
        df.to_csv(filepath, index=False)
        return len(df)

    def __repr__(self) -> str:
        return (
            f"BeatGrid(length={self._length.value}, "
            f"beats_per_measure={self._beats_per_measure}, "
            f"measures={self.n_measures})"
        )
