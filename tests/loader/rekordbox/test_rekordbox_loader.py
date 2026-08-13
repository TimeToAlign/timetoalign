"""Exact validation for Rekordbox collection loading."""

from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from timetoalign import Coordinate, Interval, TimeUnit
from timetoalign.loader import RekordboxLoader

SPECIMEN = Path(
    "/home/laser/git/tta/tta_test_data/data/audio/moriero_dj_set/rekordbox.xml"
)


def _track_xml(
    track_id: str,
    name: str,
    *,
    total_time: str = "8",
    tempos: str = "",
) -> str:
    if not tempos:
        tempos = '<TEMPO Inizio="0" Bpm="60" Metro="4/4" Battito="1" />'
    return f"""
    <TRACK TrackID="{track_id}" Name="{name}" TotalTime="{total_time}"
           AverageBpm="90" SampleRate="48000" Location="file:///{name}.wav">
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
    assert [measure.actual_length for measure in measures] == [
        Fraction(1),
        Fraction(4),
        Fraction(4),
        Fraction(2),
    ]
    assert [measure.nominal_length for measure in measures] == [Fraction(4)] * 4
    assert floating_measures is not None
    assert floating_measures.x_values.tolist() == [0.0, 1.0, 5.0, 7.0, 8.0]
    assert floating_measures.y_values.tolist() == [1.0, 2.0, 3.0, 4.0, 4.5]
    assert floating_measures(3.0) == 2.5
    assert floating_measures(7.5) == 4.25
    assert timeline.create_skeleton() is timeline.skeleton
    assert timeline.meta == {
        "TrackID": "1",
        "AverageBpm": 90.0,
        "Location": "file:///Grid Study.wav",
        "SampleRate": 48000,
        "POSITION_MARK": [{"Name": "cue", "Type": "0", "Start": "1.25", "Num": "0"}],
    }


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


def test_real_specimen_collection_and_mix_grids_are_exact() -> None:
    if not SPECIMEN.exists():
        pytest.skip(f"Test data file not found: {SPECIMEN}")

    loader = RekordboxLoader.from_file(SPECIMEN)
    mix = next(track for track in loader.tracks if track.track_id == "147337955")
    expected_spans = [
        Decimal("212.639"),
        Decimal("459.757"),
        Decimal("324.001"),
        Decimal("432.007"),
        Decimal("669.011"),
        Decimal("96.023"),
        Decimal("60.014"),
        Decimal("432.011"),
        Decimal("726.008"),
        Decimal("67.508"),
        Decimal("670.494"),
        Decimal("151.496"),
        Decimal("134.679"),
        Decimal("841.019"),
    ]
    spans = [
        Decimal(
            str(mix.tempos[index + 1].inizio if index + 1 < len(mix.tempos) else 5277.0)
        )
        - Decimal(str(tempo.inizio))
        for index, tempo in enumerate(mix.tempos)
    ]

    assert len(loader.tracks) == 46
    assert sum(len(track.tempos) for track in loader.tracks) == 155
    assert mix.name == "001-samuel_moriero-impact_halloween_xxl_2025_full_set"
    assert mix.total_time == 5277.0
    assert len(mix.tempos) == 14
    assert spans == expected_spans
    assert (mix.tempos[0].inizio, mix.tempos[0].bpm, mix.tempos[0].battito) == (
        0.333,
        160.0,
        4,
    )
    assert mix.tempos[1].battito == 3
    assert mix.tempos[5].bpm == 159.96
    assert mix.tempos[6].bpm == 159.96
    assert mix.tempos[12].bpm == 160.38
    assert loader.create_bundle().n_timelines == 46
