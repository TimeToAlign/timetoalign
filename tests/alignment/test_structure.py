"""Structure-level validation for the TimeSkeleton building blocks.

These tests pin the ground truths documented in ``README.md`` under
*TimeSkeleton Validation* for the ``SectionHierarchy``, ``MetricHierarchy`` and
``Measure`` scalars: construction equivalences, name-blind hierarchy equality,
name-aware policy equality, and the derived ``count``/``qstamp`` arithmetic of a
``MeasureMap``. Every expected value is exact, never a range.
"""

from __future__ import annotations

from fractions import Fraction

import pydantic
import pytest

from timetoalign.alignment import MeasureMap, MetricHierarchy, SectionHierarchy
from timetoalign.core import BeatPolicy, Measure

# The canonical three-section shape used throughout: 78 + 65 + 60 == 203.
SECTION_COUNTS = (78, 65, 60)
TOTAL_MEASURES = 203


def _abstract(count: int) -> list[Measure]:
    """A run of ``count`` length-less measures, as ``from_measure_counts`` mints."""
    return [Measure() for _ in range(count)]


def _quarter_policy() -> BeatPolicy:
    """A quarter-note beat with three beats per bar and no tempo (``3/4``)."""
    return BeatPolicy(grouping=(1, 1, 1), division=Fraction(1))


def _eighth_policy() -> BeatPolicy:
    """A three-beat bar counted in eighth notes (``3/8``)."""
    return BeatPolicy(grouping=(1, 1, 1), division=Fraction(1, 2))


# region (a) Construction equivalences


class TestSectionHierarchyConstructionEquivalence:
    """The same partition spelled every accepted way compares equal."""

    def test_nested_measures_equal_measure_counts(self) -> None:
        nested = SectionHierarchy.from_measures([_abstract(n) for n in SECTION_COUNTS])
        counts = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        assert nested == counts
        assert counts.n_sections == 3
        assert [section.n_measures for section in counts.sections] == list(
            SECTION_COUNTS
        )
        assert counts.n_measures == TOTAL_MEASURES

    def test_int_form_equals_every_single_section_spelling(self) -> None:
        as_int = SectionHierarchy.from_measure_counts(TOTAL_MEASURES)
        as_list = SectionHierarchy.from_measure_counts([TOTAL_MEASURES])
        as_map = SectionHierarchy.from_measure_counts({"whole": TOTAL_MEASURES})
        as_pairs = SectionHierarchy.from_measure_counts([("whole", TOTAL_MEASURES)])
        as_zip = SectionHierarchy.from_measure_counts(
            zip(["whole"], [TOTAL_MEASURES], strict=True)
        )
        as_nested = SectionHierarchy.from_measures([_abstract(TOTAL_MEASURES)])
        assert as_int.n_sections == 1
        for other in (as_list, as_map, as_pairs, as_zip, as_nested):
            assert as_int == other

    def test_three_section_spellings_all_equal(self) -> None:
        as_list = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        as_map = SectionHierarchy.from_measure_counts({"I": 78, "II": 65, "III": 60})
        as_pairs = SectionHierarchy.from_measure_counts(
            [("I", 78), ("II", 65), ("III", 60)]
        )
        as_zip = SectionHierarchy.from_measure_counts(
            zip(["I", "II", "III"], SECTION_COUNTS, strict=True)
        )
        for other in (as_map, as_pairs, as_zip):
            assert as_list == other

    def test_consumed_once_zip_is_materialized(self) -> None:
        # A zip is a single-use iterator; the constructor must read it once and
        # still compare equal to the eager list-of-pairs spelling.
        consumed = zip(["I", "II", "III"], SECTION_COUNTS, strict=True)
        from_zip = SectionHierarchy.from_measure_counts(consumed)
        assert list(consumed) == []  # the iterator is now exhausted
        assert from_zip == SectionHierarchy.from_measure_counts(
            [("I", 78), ("II", 65), ("III", 60)]
        )

    def test_measure_map_accepted_where_measures_expected(self) -> None:
        measure_map = MeasureMap(_abstract(TOTAL_MEASURES))
        from_map = SectionHierarchy.from_measures(measure_map)
        assert from_map.n_sections == 1
        assert from_map == SectionHierarchy.from_measure_counts(TOTAL_MEASURES)

    def test_display_names_excluded_from_equality(self) -> None:
        named = SectionHierarchy.from_measure_counts({"I": 78, "II": 65, "III": 60})
        differently_named = SectionHierarchy.from_measure_counts(
            [("intro", 78), ("middle", 65), ("finale", 60)]
        )
        anonymous = SectionHierarchy.from_measure_counts(list(SECTION_COUNTS))
        assert named == differently_named
        assert named == anonymous
        assert [section.name for section in named.sections] == ["I", "II", "III"]
        assert [section.name for section in anonymous.sections] == [None, None, None]

    def test_different_section_shape_is_unequal(self) -> None:
        assert SectionHierarchy.from_measure_counts(
            list(SECTION_COUNTS)
        ) != SectionHierarchy.from_measure_counts([78, 60, 65])
        assert SectionHierarchy.from_measure_counts(
            [3, 2, 2]
        ) != SectionHierarchy.from_measure_counts([3, 3, 1])

    def test_concrete_leaf_quarter_spans(self) -> None:
        # A concrete three-section structure (3/2/2 bars of 3/4) carries exact
        # leaf spans of 9, 6, 6 quarters and 21 total.
        def bars(count: int) -> list[Measure]:
            return [
                Measure(actual_length=Fraction(3), time_signature="3/4")
                for _ in range(count)
            ]

        hierarchy = SectionHierarchy.from_measures([bars(3), bars(2), bars(2)])
        spans = [
            section.measure_map.total_actual_length for section in hierarchy.sections
        ]
        assert spans == [Fraction(9), Fraction(6), Fraction(6)]
        assert hierarchy.measure_map.total_actual_length == Fraction(21)


# endregion


# region MeasureMap immutability


class TestMeasureMapImmutability:
    """A ``MeasureMap`` exposes no mutators and a read-only measures tuple."""

    @pytest.mark.parametrize("mutator", ["append", "insert", "replace", "set"])
    def test_no_mutator_attributes(self, mutator: str) -> None:
        measure_map = MeasureMap(_abstract(3))
        assert not hasattr(measure_map, mutator)

    def test_measures_tuple_is_not_writable(self) -> None:
        measure_map = MeasureMap(_abstract(3))
        assert isinstance(measure_map.measures, tuple)
        with pytest.raises(TypeError):
            measure_map.measures[0] = Measure()  # type: ignore[index]


# endregion


# region (b) Metric-hierarchy equivalence


class TestMetricHierarchyEquivalence:
    """Metric equality compares section shape and each policy's beat/bpm only."""

    def test_from_beat_policies_equals_from_sections(self) -> None:
        registered = MetricHierarchy.from_beat_policies({"slow": _quarter_policy()})
        registered.create_sections(["slow", "slow", "slow"])
        direct = MetricHierarchy.from_sections(
            [_quarter_policy(), _quarter_policy(), _quarter_policy()]
        )
        assert registered == direct
        assert len(registered.sections) == 3
        assert len(direct.sections) == 3

    def test_policy_display_names_excluded_from_equality(self) -> None:
        anonymous = MetricHierarchy.from_sections([_quarter_policy() for _ in range(3)])
        named = MetricHierarchy.from_sections(
            [_quarter_policy().model_copy(update={"name": "slow"}) for _ in range(3)]
        )
        assert anonymous == named

    def test_bpm_difference_breaks_equality(self) -> None:
        without_tempo = MetricHierarchy.from_sections(
            [_quarter_policy() for _ in range(3)]
        )
        with_tempo = MetricHierarchy.from_sections(
            [_quarter_policy().model_copy(update={"bpm": 120}) for _ in range(3)]
        )
        assert without_tempo != with_tempo

    def test_beat_size_difference_breaks_equality(self) -> None:
        in_quarters = MetricHierarchy.from_sections(
            [_quarter_policy() for _ in range(3)]
        )
        in_eighths = MetricHierarchy.from_sections([_eighth_policy() for _ in range(3)])
        assert in_quarters != in_eighths


class TestBeatPolicyScalarEquality:
    """The ``BeatPolicy`` scalar itself keeps its pydantic name-aware equality."""

    def test_name_participates_in_scalar_equality(self) -> None:
        first = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        second = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="b")
        assert first != second

    def test_identical_policies_including_name_are_equal(self) -> None:
        first = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        second = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="a")
        assert first == second


# endregion


# region (c) Measure scalar


class TestMeasureScalar:
    """The ``Measure`` scalar's field set and map-derived arithmetic."""

    def test_constructs_with_no_arguments(self) -> None:
        measure = Measure()
        assert measure.id is None
        assert measure.count is None
        assert measure.qstamp is None
        assert measure.actual_length is None

    def test_field_set_is_exactly_the_standard_plus_volta(self) -> None:
        assert set(Measure.model_fields) == {
            "id",
            "count",
            "qstamp",
            "number",
            "name",
            "time_signature",
            "nominal_length",
            "actual_length",
            "start_repeat",
            "end_repeat",
            "next",
            "volta",
        }

    def test_is_frozen(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Measure().count = 5  # type: ignore[misc]

    def test_count_and_qstamp_are_prefix_sums_when_omitted(self) -> None:
        measure_map = MeasureMap(
            [
                Measure(actual_length=Fraction(3)),
                Measure(actual_length=Fraction(3)),
                Measure(actual_length=Fraction(2)),
            ]
        )
        assert [measure.count for measure in measure_map] == [1, 2, 3]
        assert [measure.qstamp for measure in measure_map] == [
            Fraction(0),
            Fraction(3),
            Fraction(6),
        ]
        assert [measure.id for measure in measure_map] == ["m1", "m2", "m3"]

    def test_disagreeing_count_warns_and_is_corrected(self) -> None:
        with pytest.warns(UserWarning, match="supplies count 5"):
            measure_map = MeasureMap(
                [
                    Measure(count=5, actual_length=Fraction(3)),
                    Measure(actual_length=Fraction(3)),
                ]
            )
        # The deviation is announced, not swallowed: the printed-order value wins.
        assert [measure.count for measure in measure_map] == [1, 2]

    def test_disagreeing_qstamp_warns_and_is_corrected(self) -> None:
        with pytest.warns(UserWarning, match="supplies qstamp 99"):
            measure_map = MeasureMap(
                [
                    Measure(actual_length=Fraction(3)),
                    Measure(qstamp=Fraction(99), actual_length=Fraction(3)),
                ]
            )
        assert [measure.qstamp for measure in measure_map] == [
            Fraction(0),
            Fraction(3),
        ]


# endregion
