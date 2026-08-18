"""Exact validation for Rekordbox collection loading."""

from fractions import Fraction
from pathlib import Path

import pytest

from timetoalign import Coordinate, Interval, NumberType, TimeUnit
from timetoalign.core.events import IrregularMeasure, MeasureConstituent
from timetoalign.loader import RekordboxLoader
from timetoalign.maps import QuartersToFloatingMeasures

SPECIMEN = Path(
    "/home/laser/git/tta/tta_test_data/data/audio/moriero_dj_set/rekordbox.xml"
)


_DEFAULT_LOCATION = object()


def _track_xml(
    track_id: str,
    name: str,
    *,
    total_time: str = "8",
    tempos: str = "",
    sample_rate: str | None = "48000",
    location: object = _DEFAULT_LOCATION,
) -> str:
    if not tempos:
        tempos = '<TEMPO Inizio="0" Bpm="60" Metro="4/4" Battito="1" />'
    if location is _DEFAULT_LOCATION:
        location = f"file:///{name}.wav"
    optional = ""
    if sample_rate is not None:
        optional += f' SampleRate="{sample_rate}"'
    if location is not None:
        optional += f' Location="{location}"'
    return f"""
    <TRACK TrackID="{track_id}" Name="{name}" TotalTime="{total_time}"
           AverageBpm="90"{optional}>
      {tempos}
      <POSITION_MARK Name="cue" Type="0" Start="1.25" Num="0" />
    </TRACK>
    """


def _write_collection(tmp_path: Path, tracks: str) -> Path:
    path = tmp_path / "rekordbox.xml"
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <DJ_PLAYLISTS>
          <COLLECTION Entries="2">{tracks}</COLLECTION>
          <PLAYLISTS><NODE><TRACK Key="not-a-collection-track" /></NODE></PLAYLISTS>
        </DJ_PLAYLISTS>
        """,
        encoding="utf-8",
    )
    return path


def test_pickup_grid_change_and_trailing_measure_are_exact(tmp_path: Path) -> None:
    tempos = """
      <TEMPO Inizio="0" Bpm="60" Metro="4/4" Battito="4" />
      <TEMPO Inizio="3.5" Bpm="120" Metro="4/4" Battito="2" />
      <TEMPO Inizio="7" Bpm="120" Metro="4/4" Battito="1" />
    """
    path = _write_collection(
        tmp_path,
        _track_xml("1", "Grid Study", tempos=tempos),
    )

    loader = RekordboxLoader.from_file(path)
    timeline = loader.create_timeline()
    measures = timeline.skeleton.section_hierarchy.measure_map.measures
    floating_measures = timeline.get_conversion_map(TimeUnit.floating_measures)

    assert len(loader.tracks) == 1
    assert [tempo.inizio for tempo in loader.tracks[0].tempos] == [0.0, 3.5, 7.0]
    assert [tempo.battito for tempo in loader.tracks[0].tempos] == [4, 2, 1]
    assert [measure.id for measure in measures] == ["m1", "m2", "m3", "m4"]
    assert [measure.number for measure in measures] == [0, 1, 2, 3]
    assert isinstance(measures[0], MeasureConstituent)
    assert measures[0].offset_within_measure == Fraction(3)
    assert isinstance(measures[1], IrregularMeasure)
    assert [measure.actual_length for measure in measures] == [
        # Beat 4 is the sole represented quarter of nominal bar 0.
        Fraction(1),
        # 1 -> 3.5 at 60 BPM is 5/2 q; 3.5 -> 5 at 120 BPM is 3 q.
        Fraction(5, 2) + Fraction(3),
        Fraction(4),
        # 7 -> 8 at 120 BPM is 1 s * 120/60 = 2 q.
        Fraction(2),
    ]
    assert [measure.nominal_length for measure in measures] == [Fraction(4)] * 4
    assert floating_measures is not None
    assert floating_measures.x_values.tolist() == [0.0, 1.0, 3.5, 5.0, 7.0, 8.0]
    assert floating_measures.y_values.tolist() == [0.75, 1.0, 1.25, 2.0, 3.0, 4.0]
    assert floating_measures(3.0) == 1.2
    assert floating_measures(7.5) == 3.5
    assert timeline.create_skeleton() is timeline.skeleton
    assert timeline.meta == {
        "TrackID": "1",
        "AverageBpm": 90.0,
        "Location": "file:///Grid Study.wav",
        "SampleRate": 48000,
        "POSITION_MARK": [{"Name": "cue", "Type": "0", "Start": "1.25", "Num": "0"}],
    }


def test_timeline_id_is_decoded_location_stem(tmp_path: Path) -> None:
    path = _write_collection(
        tmp_path,
        _track_xml(
            "1",
            "Habstrakt - Tonight FREE DL",
            location="file://localhost/~/music/02.%20Tonight%20(Remix).mp3",
        ),
    )
    timeline = RekordboxLoader.from_file(path).create_timeline()

    assert timeline.id == "02. Tonight (Remix)"
    assert timeline.name == "Habstrakt - Tonight FREE DL"
    assert timeline.skeleton.id == "02. Tonight (Remix)/skeleton"


def test_timeline_id_falls_back_to_name_without_location(tmp_path: Path) -> None:
    path = _write_collection(tmp_path, _track_xml("1", "Display Only", location=None))
    timeline = RekordboxLoader.from_file(path).create_timeline()

    assert timeline.id == "Display Only"
    assert timeline.name == "Display Only"
    assert timeline.skeleton.id == "Display Only/skeleton"
    assert timeline.meta["Location"] is None


def test_sample_rate_affords_exact_seconds_to_samples_conversion(
    tmp_path: Path,
) -> None:
    path = _write_collection(tmp_path, _track_xml("1", "Sampled"))
    timeline = RekordboxLoader.from_file(path).create_timeline()
    samples_map = timeline.get_conversion_map(TimeUnit.samples)

    assert samples_map is not None
    assert samples_map.sample_rate == 48000
    converted = timeline.get_timestamp_at(Coordinate(1.5, TimeUnit.seconds)).get_unit(
        TimeUnit.samples
    )
    assert isinstance(converted, Coordinate)
    assert converted.timeline_id == "Sampled"
    assert converted.unit is TimeUnit.samples
    assert converted.number_type is NumberType.int
    assert isinstance(converted.value, int)
    assert converted.value == 72000


def test_absent_sample_rate_attaches_no_samples_axis(tmp_path: Path) -> None:
    path = _write_collection(tmp_path, _track_xml("1", "Unsampled", sample_rate=None))
    timeline = RekordboxLoader.from_file(path).create_timeline()

    assert timeline.meta["SampleRate"] is None
    assert timeline.get_conversion_map(TimeUnit.samples) is None


def test_collection_scope_bundle_and_claim_tuple_ingestion(tmp_path: Path) -> None:
    path = _write_collection(
        tmp_path,
        _track_xml("1", "Mix") + _track_xml("2", "Source"),
    )
    loader = RekordboxLoader.from_file(path)

    assert [track.name for track in loader.tracks] == ["Mix", "Source"]
    with pytest.raises(ValueError, match=r"'Mix'.*'Source'"):
        loader.create_timeline()

    bundle = loader.create_bundle()
    mix = bundle.get_timeline("Mix")
    source = bundle.get_timeline("Source")
    claims = [
        [
            (
                mix.id,
                Interval(2.0, 3.0, "fm"),
                source.id,
                Interval(4.0, 5.0, "fm"),
            )
        ]
    ]
    bundle.add_match_claims(claims)

    assert bundle.n_timelines == 2
    assert bundle.n_cross_group_claims == 1


def test_interval_positional_construction_and_coordinate_passthrough() -> None:
    positional = Interval(64.0, 65.0, "fm")
    start = Coordinate(64.0, TimeUnit.floating_measures)
    end = Coordinate(65.0, TimeUnit.floating_measures)

    assert positional == Interval(start, end)
    assert positional == Interval(start=start, end=end)
    assert positional.unit is TimeUnit.floating_measures

    with pytest.raises(ValueError, match="does not match requested unit"):
        Interval(start, end, TimeUnit.seconds)

    positional_fraction = Interval(Fraction(1, 3), Fraction(2, 3), "fm")
    assert positional_fraction.number_type is NumberType.float
    assert positional_fraction.start.value == float(Fraction(1, 3))
    assert positional_fraction.end.value == float(Fraction(2, 3))

    exact_start = Coordinate(Fraction(1, 3), TimeUnit.floating_measures)
    exact_end = Coordinate(Fraction(2, 3), TimeUnit.floating_measures)
    assert Interval(start=exact_start, end=exact_end).number_type is NumberType.fraction

    with pytest.raises(ValueError, match="cannot be stored in an integer-valued field"):
        Interval(Fraction(1, 3), Fraction(2, 3), TimeUnit.ticks)


def test_real_specimen_collection_and_mix_grids_are_exact() -> None:
    if not SPECIMEN.exists():
        pytest.skip(f"Test data file not found: {SPECIMEN}")

    loader = RekordboxLoader.from_file(SPECIMEN)
    mix = next(track for track in loader.tracks if track.track_id == "147337955")
    expected_spans = [
        Fraction("212.639"),
        Fraction("459.757"),
        Fraction("324.001"),
        Fraction("432.007"),
        Fraction("669.011"),
        Fraction("96.023"),
        Fraction("60.014"),
        Fraction("432.011"),
        Fraction("726.008"),
        Fraction("67.508"),
        Fraction("670.494"),
        Fraction("151.496"),
        Fraction("134.679"),
        Fraction("841.019"),
    ]
    spans = [
        (
            mix.tempos[index + 1].inizio
            if index + 1 < len(mix.tempos)
            else mix.total_time
        )
        - tempo.inizio
        for index, tempo in enumerate(mix.tempos)
    ]

    assert len(loader.tracks) == 46
    assert sum(len(track.tempos) for track in loader.tracks) == 155
    assert mix.name == "001-samuel_moriero-impact_halloween_xxl_2025_full_set"
    assert mix.total_time == Fraction(5277)
    assert len(mix.tempos) == 14
    assert spans == expected_spans
    assert (mix.tempos[0].inizio, mix.tempos[0].bpm, mix.tempos[0].battito) == (
        Fraction("0.333"),
        Fraction(160),
        4,
    )
    assert mix.tempos[1].battito == 3
    assert mix.tempos[5].bpm == Fraction("159.96")
    assert mix.tempos[6].bpm == Fraction("159.96")
    assert mix.tempos[12].bpm == Fraction("160.38")

    bundle = loader.create_bundle()
    assert bundle.n_timelines == 46
    mix_timeline = bundle.get_timeline(mix.name)
    measure_map = mix_timeline.skeleton.section_hierarchy.measure_map
    floating_measures = mix_timeline.get_conversion_map(TimeUnit.floating_measures)

    pickup = measure_map[0]
    assert pickup.id == "m1"
    assert pickup.number == 0
    assert isinstance(pickup, MeasureConstituent)
    assert pickup.offset_within_measure == Fraction(3)
    assert pickup.actual_length == Fraction(1)
    assert pickup.nominal_length == Fraction(4)

    # Battito 4 occupies 3/4 of nominal bar 0; one 160-BPM beat later is bar 1.
    assert floating_measures(Fraction("0.333")) == 0.75
    assert floating_measures(Fraction("0.708")) == 1.0
    # The second grid opens on Battito 3 in bar 142: 142 + (3 - 1)/4.
    assert floating_measures(Fraction("212.972")) == 142.5

    # m450 spans 672.722 -> 672.729: 7/1000 s * 160/60 = 7/375 q.
    sliver = measure_map[449]
    assert sliver.id == "m450"
    assert isinstance(sliver, IrregularMeasure)
    assert sliver.actual_length == Fraction(7, 1000) * Fraction(160, 60)
    assert all(
        measure.actual_length is not None and measure.actual_length.denominator < 10**7
        for measure in measure_map.measures
    )

    canonical = QuartersToFloatingMeasures.from_measure_map(measure_map)
    total_quarters = sum(
        (measure.actual_length for measure in measure_map.measures), Fraction(0)
    )
    assert floating_measures(Fraction(5277)) == canonical(total_quarters)

    brace = bundle.get_timeline("40. Brace For Impact")
    brace_grid = next(
        track for track in loader.tracks if track.name == brace.name
    ).tempos[0]
    brace_fm = brace.get_conversion_map(TimeUnit.floating_measures)
    # Battito 2 needs three 0.4 s beats: 0.145 + 3 * (60/150) = 1.345.
    first_downbeat = brace_grid.inizio + 3 * brace_grid.beat_seconds
    assert first_downbeat == Fraction("1.345")
    assert brace_fm(first_downbeat) == 1.0


def test_real_specimen_timeline_ids_are_decoded_file_stems() -> None:
    if not SPECIMEN.exists():
        pytest.skip(f"Test data file not found: {SPECIMEN}")

    bundle = RekordboxLoader.from_file(SPECIMEN).create_bundle()
    ids = set(bundle.timelines)

    assert len(ids) == 46
    assert {
        "01. See Me Coming",
        "05. HUMBLE (Samuel Moriero REMIX)",
        "41b. Vielleicht Vielleicht",
        "001-samuel_moriero-impact_halloween_xxl_2025_full_set",
    } <= ids
    # The csv placeholder labels have no audio file in the collection.
    assert ids.isdisjoint({"04. ID", "06. ID", "16. ID", "17. ID", "36. ID", "41a. ID"})
