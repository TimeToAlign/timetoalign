"""Load Rekordbox XML collections as structured physical timelines."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from timetoalign.loader.base import Loader


@dataclass(frozen=True)
class RekordboxTempo:
    """One Rekordbox beat-grid declaration."""

    inizio: Fraction
    bpm: Fraction
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
    def beat_seconds(self) -> Fraction:
        """Return one grid beat in seconds."""
        return Fraction(60) / self.bpm

    @property
    def bar_seconds(self) -> Fraction:
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
    total_time: Fraction
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
            total_time = Fraction(attributes["TotalTime"])
        except KeyError as exc:
            raise ValueError(f"Collection TRACK is missing {exc.args[0]}") from exc

        tempos = tuple(
            RekordboxTempo(
                inizio=Fraction(child.attrib["Inizio"]),
                bpm=Fraction(child.attrib["Bpm"]),
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
        from timetoalign.maps import SecondsToSamples, TableMap
        from timetoalign.timelines import ContinuousPhysicalTimeline

        downbeats = cls._downbeats(track)
        measures = cls._measure_map(track, downbeats)
        measure_map = MeasureMap(measures)
        seconds, floating_measures = cls._conversion_anchors(
            track, downbeats, measure_map
        )

        timeline = ContinuousPhysicalTimeline(
            length=float(track.total_time),
            unit=TimeUnit.seconds,
            number_type=NumberType.float,
            uid=cls._track_uid(track),
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
        if track.sample_rate is not None:
            timeline.add_conversion_map(SecondsToSamples(sample_rate=track.sample_rate))
        hierarchy = SectionHierarchy.from_measures(measure_map)
        TimeSkeleton(hierarchy, uid=f"{track.name}/skeleton").attach(timeline)
        return timeline

    @staticmethod
    def _track_uid(track: RekordboxTrack) -> str:
        """Return the track's stable identity: the decoded file-name stem.

        Collection artifacts cross-reference tracks by file name, while the
        XML ``Name`` is display metadata; a track without a ``Location``
        falls back to that display name.
        """
        if track.location is None:
            return track.name
        return Path(unquote(urlparse(track.location).path)).stem

    @staticmethod
    def _downbeats(track: RekordboxTrack) -> list[tuple[Fraction, RekordboxTempo]]:
        downbeats: list[tuple[Fraction, RekordboxTempo]] = []
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
        from timetoalign.core import (
            IrregularMeasure,
            MeasureConstituent,
            RegularMeasure,
        )

        measures: list[Any] = []
        first_tempo = track.tempos[0]
        if first_tempo.battito != 1:
            remaining_beats = first_tempo.numerator - first_tempo.battito + 1
            measures.append(
                MeasureConstituent(
                    number=0,
                    time_signature=first_tempo.metro,
                    nominal_length=first_tempo.nominal_quarters,
                    actual_length=Fraction(
                        remaining_beats * 4, first_tempo.denominator
                    ),
                    offset_within_measure=Fraction(
                        (first_tempo.battito - 1) * 4,
                        first_tempo.denominator,
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
            actual_length = cls._quarters_between(track, downbeat, next_downbeat)
            measure_type = (
                RegularMeasure
                if actual_length == tempo.nominal_quarters
                else IrregularMeasure
            )
            measures.append(
                measure_type(
                    number=index + 1,
                    time_signature=tempo.metro,
                    nominal_length=tempo.nominal_quarters,
                    actual_length=actual_length,
                )
            )

        if not measures:
            raise ValueError(f"Rekordbox track {track.name!r} contains no measures")
        return measures

    @classmethod
    def _conversion_anchors(
        cls,
        track: RekordboxTrack,
        downbeats: list[tuple[Fraction, RekordboxTempo]],
        measure_map: Any,
    ) -> tuple[list[Fraction], list[Fraction]]:
        from timetoalign.maps import QuartersToFloatingMeasures

        downbeat_instants = [instant for instant, _ in downbeats]
        anchors: dict[Fraction, Fraction] = {}

        first_tempo = track.tempos[0]
        first_bar = bisect_right(downbeat_instants, first_tempo.inizio)
        first_fm = Fraction(first_bar) + Fraction(
            first_tempo.battito - 1, first_tempo.numerator
        )
        anchors[Fraction(0)] = first_fm - first_tempo.inizio / first_tempo.bar_seconds

        for tempo in track.tempos:
            bar_number = bisect_right(downbeat_instants, tempo.inizio)
            anchors[tempo.inizio] = Fraction(bar_number) + Fraction(
                tempo.battito - 1, tempo.numerator
            )

        for index, (instant, _) in enumerate(downbeats, start=1):
            anchors[instant] = Fraction(index)

        canonical = QuartersToFloatingMeasures.from_measure_map(measure_map)
        total_quarters = measure_map.total_actual_length
        assert total_quarters is not None
        anchors[track.total_time] = Fraction(str(canonical(total_quarters)))

        result = sorted(anchors.items())
        return [item[0] for item in result], [item[1] for item in result]

    @classmethod
    def _quarters_between(
        cls,
        track: RekordboxTrack,
        start: Fraction,
        end: Fraction,
    ) -> Fraction:
        """Integrate exact quarter-note length over a seconds interval."""
        cursor = start
        active = cls._tempo_at(track, start)
        quarters = Fraction(0)
        for tempo in track.tempos:
            if tempo.inizio <= start:
                continue
            if tempo.inizio >= end:
                break
            quarters += (tempo.inizio - cursor) * active.bpm / 60
            cursor = tempo.inizio
            active = tempo
        return quarters + (end - cursor) * active.bpm / 60

    @staticmethod
    def _tempo_at(track: RekordboxTrack, instant: Fraction) -> RekordboxTempo:
        selected = track.tempos[0]
        for tempo in track.tempos:
            if tempo.inizio > instant:
                break
            selected = tempo
        return selected
