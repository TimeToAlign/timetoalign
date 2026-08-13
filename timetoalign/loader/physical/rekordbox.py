"""Load Rekordbox XML collections as structured physical timelines."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from timetoalign.loader.base import Loader


@dataclass(frozen=True)
class RekordboxTempo:
    """One Rekordbox beat-grid declaration."""

    inizio: float
    bpm: float
    metro: str
    battito: int

    @property
    def numerator(self) -> int:
        """Return the meter numerator."""
        return int(self.metro.split("/", maxsplit=1)[0])

    @property
    def denominator(self) -> int:
        """Return the meter denominator."""
        return int(self.metro.split("/", maxsplit=1)[1])

    @property
    def beat_seconds(self) -> float:
        """Return one grid beat in seconds."""
        return 60.0 / self.bpm

    @property
    def bar_seconds(self) -> float:
        """Return one grid bar in seconds."""
        return self.numerator * self.beat_seconds

    @property
    def nominal_quarters(self) -> Fraction:
        """Return one nominal bar in exact quarter notes."""
        return Fraction(self.numerator * 4, self.denominator)


@dataclass(frozen=True)
class RekordboxTrack:
    """Metadata and grids parsed from one collection track."""

    track_id: str
    name: str
    total_time: float
    average_bpm: float | None
    sample_rate: int | None
    location: str | None
    tempos: tuple[RekordboxTempo, ...]
    position_marks: tuple[dict[str, str], ...]


class RekordboxLoader(Loader[list[RekordboxTrack]]):
    """Parse the collection tracks in a Rekordbox XML export."""

    def __init__(self) -> None:
        super().__init__()
        self._tracks: list[RekordboxTrack] = []

    @classmethod
    def from_file(cls, path: Path | str) -> RekordboxLoader:
        """Parse *path* and return a loaded collection reader."""
        return cls().load(path)

    @property
    def tracks(self) -> tuple[RekordboxTrack, ...]:
        """Return collection tracks in XML order."""
        return tuple(self._tracks)

    def clear(self) -> None:
        """Clear parsed tracks and shared source state."""
        super().clear()
        self._tracks.clear()

    def _load_source(self, source: Path) -> list[RekordboxTrack]:
        root = ET.parse(source).getroot()
        collection = root if root.tag == "COLLECTION" else root.find("COLLECTION")
        if collection is None:
            raise ValueError(f"Rekordbox XML {source} has no COLLECTION element")
        return [self._parse_track(element) for element in collection.findall("TRACK")]

    def _accept_source(
        self,
        path: Path,
        source_meta: dict[str, Any],
        payload: list[RekordboxTrack],
    ) -> None:
        super()._accept_source(path, source_meta, payload)
        self._tracks.extend(payload)

    @staticmethod
    def _parse_track(element: ET.Element) -> RekordboxTrack:
        attributes = element.attrib
        try:
            track_id = attributes["TrackID"]
            name = attributes["Name"]
            total_time = float(attributes["TotalTime"])
        except KeyError as exc:
            raise ValueError(f"Collection TRACK is missing {exc.args[0]}") from exc

        tempos = tuple(
            RekordboxTempo(
                inizio=float(child.attrib["Inizio"]),
                bpm=float(child.attrib["Bpm"]),
                metro=child.attrib["Metro"],
                battito=int(child.attrib["Battito"]),
            )
            for child in element.findall("TEMPO")
        )
        if not tempos:
            raise ValueError(f"Rekordbox track {name!r} has no TEMPO grid")
        tempos = tuple(sorted(tempos, key=lambda tempo: tempo.inizio))
        for tempo in tempos:
            if tempo.bpm <= 0:
                raise ValueError(f"Rekordbox track {name!r} has non-positive BPM")
            if not 1 <= tempo.battito <= tempo.numerator:
                raise ValueError(
                    f"Rekordbox track {name!r} has Battito {tempo.battito} "
                    f"outside meter {tempo.metro}"
                )

        average_bpm = attributes.get("AverageBpm")
        sample_rate = attributes.get("SampleRate")
        return RekordboxTrack(
            track_id=track_id,
            name=name,
            total_time=total_time,
            average_bpm=float(average_bpm) if average_bpm is not None else None,
            sample_rate=int(sample_rate) if sample_rate is not None else None,
            location=attributes.get("Location"),
            tempos=tempos,
            position_marks=tuple(
                dict(child.attrib) for child in element.findall("POSITION_MARK")
            ),
        )

    def create_timelines(self) -> list[Any]:
        """Create and structure one seconds timeline per collection track."""
        if not self._tracks:
            raise RuntimeError("No Rekordbox collection loaded. Call load() first.")
        return [self._create_track_timeline(track) for track in self._tracks]

    def create_timeline(self) -> Any:
        """Create the only loaded track, rejecting ambiguous collections."""
        if len(self._tracks) != 1:
            available = ", ".join(repr(track.name) for track in self._tracks) or "none"
            raise ValueError(
                "create_timeline() requires exactly one Rekordbox collection track; "
                f"available names: {available}"
            )
        return self._create_track_timeline(self._tracks[0])

    def create_bundle(self) -> Any:
        """Create an alignment bundle containing every collection track."""
        from timetoalign.alignment import AlignmentBundle

        bundle = AlignmentBundle()
        for timeline in self.create_timelines():
            bundle.add_timeline(timeline, uid=timeline.id)
        return bundle

    @classmethod
    def _create_track_timeline(cls, track: RekordboxTrack) -> Any:
        from timetoalign.alignment import MeasureMap, SectionHierarchy, TimeSkeleton
        from timetoalign.core import NumberType, TimeUnit
        from timetoalign.maps import TableMap
        from timetoalign.timelines import ContinuousPhysicalTimeline

        downbeats = cls._downbeats(track)
        measures = cls._measure_map(track, downbeats)
        seconds, floating_measures = cls._conversion_anchors(track, downbeats)

        timeline = ContinuousPhysicalTimeline(
            length=track.total_time,
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
            uid=track.name,
            name=track.name,
            meta={
                "TrackID": track.track_id,
                "AverageBpm": track.average_bpm,
                "Location": track.location,
                "SampleRate": track.sample_rate,
                "POSITION_MARK": [dict(mark) for mark in track.position_marks],
            },
        )
        timeline.add_conversion_map(
            TableMap(
                x_values=seconds,
                y_values=floating_measures,
                source_unit=TimeUnit.seconds,
                target_unit=TimeUnit.floating_measures,
                name="rekordbox_floating_measures",
            )
        )
        hierarchy = SectionHierarchy.from_measures(MeasureMap(measures))
        TimeSkeleton(hierarchy, uid=f"{track.name}/skeleton").attach(timeline)
        return timeline

    @staticmethod
    def _downbeats(track: RekordboxTrack) -> list[tuple[float, RekordboxTempo]]:
        downbeats: list[tuple[float, RekordboxTempo]] = []
        for index, tempo in enumerate(track.tempos):
            grid_end = (
                track.tempos[index + 1].inizio
                if index + 1 < len(track.tempos)
                else track.total_time
            )
            offset_beats = (
                0 if tempo.battito == 1 else tempo.numerator - tempo.battito + 1
            )
            first = tempo.inizio + offset_beats * tempo.beat_seconds
            bar_index = 0
            while True:
                downbeat = first + bar_index * tempo.bar_seconds
                if downbeat >= grid_end or downbeat > track.total_time:
                    break
                if not downbeats or downbeat > downbeats[-1][0]:
                    downbeats.append((downbeat, tempo))
                bar_index += 1
        return downbeats

    @classmethod
    def _measure_map(cls, track: RekordboxTrack, downbeats: list[Any]) -> list[Any]:
        from timetoalign.core import IrregularMeasure, RegularMeasure

        measures: list[Any] = []
        first_tempo = track.tempos[0]
        if first_tempo.battito != 1:
            remaining_beats = first_tempo.numerator - first_tempo.battito + 1
            measures.append(
                IrregularMeasure(
                    time_signature=first_tempo.metro,
                    nominal_length=first_tempo.nominal_quarters,
                    actual_length=Fraction(
                        remaining_beats * 4, first_tempo.denominator
                    ),
                )
            )

        for index, (downbeat, tempo) in enumerate(downbeats):
            next_downbeat = (
                downbeats[index + 1][0]
                if index + 1 < len(downbeats)
                else track.total_time
            )
            if next_downbeat <= downbeat:
                continue
            if index + 1 < len(downbeats):
                measure_type = RegularMeasure
                actual_length = tempo.nominal_quarters
            else:
                last_grid = cls._tempo_at(track, downbeat)
                fraction = (track.total_time - downbeat) / last_grid.bar_seconds
                actual_length = last_grid.nominal_quarters * Fraction(fraction)
                measure_type = (
                    RegularMeasure
                    if actual_length == last_grid.nominal_quarters
                    else IrregularMeasure
                )
                tempo = last_grid
            measures.append(
                measure_type(
                    time_signature=tempo.metro,
                    nominal_length=tempo.nominal_quarters,
                    actual_length=actual_length,
                )
            )

        if not measures:
            raise ValueError(f"Rekordbox track {track.name!r} contains no measures")
        return measures

    @staticmethod
    def _conversion_anchors(
        track: RekordboxTrack, downbeats: list[tuple[float, RekordboxTempo]]
    ) -> tuple[list[float], list[float]]:
        pickup = track.tempos[0].battito != 1
        first_bar = 2.0 if pickup else 1.0
        anchors = [
            (instant, first_bar + index) for index, (instant, _) in enumerate(downbeats)
        ]

        if anchors and anchors[0][0] == 0.0:
            result = anchors
        elif pickup:
            result = [(0.0, 1.0), *anchors]
        elif anchors:
            first_time, first_fm = anchors[0]
            start_fm = first_fm - first_time / track.tempos[0].bar_seconds
            result = [(0.0, start_fm), *anchors]
        else:
            result = [(0.0, 1.0)]

        if result[-1][0] < track.total_time:
            last_time, last_fm = result[-1]
            last_grid = RekordboxLoader._tempo_at(track, last_time)
            end_fm = last_fm + (track.total_time - last_time) / last_grid.bar_seconds
            result.append((track.total_time, end_fm))
        return [item[0] for item in result], [item[1] for item in result]

    @staticmethod
    def _tempo_at(track: RekordboxTrack, instant: float) -> RekordboxTempo:
        selected = track.tempos[0]
        for tempo in track.tempos:
            if tempo.inizio > instant:
                break
            selected = tempo
        return selected
