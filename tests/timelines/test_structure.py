"""Structure-level validation for the TimeSkeleton building blocks.

These tests pin the ground truths documented in ``tests/timelines/README.md``
under *Native Timeline Structure and Flow-Control Validation*, subsection
*Measure and hierarchy structure*, for the ``SectionHierarchy``, ``MetricHierarchy`` and
``Measure`` scalars: construction equivalences, name-blind hierarchy equality,
name-aware policy equality, and the derived ``count``/``qstamp`` arithmetic of a
``MeasureMap``. Every expected value is exact, never a range.
"""

from __future__ import annotations

import json
import warnings
from fractions import Fraction

import pydantic
import pytest

from timetoalign.core import (
    BeatPolicy,
    CadenzaMeasure,
    Duration,
    IrregularMeasure,
    Measure,
    MeasureConstituent,
    RegularMeasure,
    SplitIrregularMeasure,
    SplitRegularMeasure,
    TimeUnit,
)
from timetoalign.core.time import rational_to_wire
from timetoalign.timelines import MeasureMap, MetricHierarchy, SectionHierarchy

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
        assert from_map.measure_map is measure_map
        assert from_map == SectionHierarchy.from_measure_counts(TOTAL_MEASURES)

    def test_existing_map_is_partitioned_without_rebuilding(self) -> None:
        measure_map = MeasureMap(
            Measure(actual_length=Fraction(1, 3)) for _ in range(6)
        )
        hierarchy = SectionHierarchy.from_measure_map(measure_map, counts=[1, 2, 3])
        assert hierarchy.measure_map is measure_map
        assert [section.n_measures for section in hierarchy.sections] == [1, 2, 3]
        assert [
            tuple(measure.id for measure in section.measure_map)
            for section in hierarchy.sections
        ] == [("m1",), ("m2", "m3"), ("m4", "m5", "m6")]

    def test_existing_map_partition_must_cover_the_map_exactly(self) -> None:
        measure_map = MeasureMap(_abstract(6))
        with pytest.raises(
            ValueError,
            match=r"Section counts must sum to MeasureMap length 6, got \(2, 3\)",
        ):
            SectionHierarchy.from_measure_map(measure_map, counts=[2, 3])

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


class TestMeasureMapEqualityAndWire:
    """Map equality preserves concrete measure semantics and exact wire values."""

    def test_maps_built_twice_compare_equal(self) -> None:
        first = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        second = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        assert first == second

    def test_equal_fields_on_different_measure_classes_compare_unequal(self) -> None:
        regular = MeasureMap([RegularMeasure(actual_length=Fraction(1, 3))])
        irregular = MeasureMap([IrregularMeasure(actual_length=Fraction(1, 3))])
        assert regular != irregular

    def test_foreign_equality_operand_is_not_equal(self) -> None:
        assert MeasureMap([]) != ()

    def test_json_round_trip_is_exact_and_emits_no_warning(self) -> None:
        measure_map = MeasureMap(
            [
                RegularMeasure(actual_length=Fraction(1, 3)),
                IrregularMeasure(actual_length=Fraction(2, 3)),
            ]
        )
        payload = json.loads(json.dumps(measure_map.to_dict()))
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            restored = MeasureMap.from_dict(payload)
        assert emitted == []
        assert restored == measure_map
        assert restored.to_dict() == payload


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


class TestBeatPolicyAndMetricHierarchyWire:
    """Metric wire forms preserve authored units, names, and policy registries."""

    @pytest.mark.parametrize(
        "policy",
        [
            BeatPolicy(
                grouping=(1, 2),
                beat_size=Duration(Fraction(1, 3), TimeUnit.whole_note),
                bpm=90,
                name="whole-note spelling",
            ),
            BeatPolicy(
                grouping=(2, 1),
                beat_size=Duration(Fraction(1, 3), TimeUnit.quarters),
                bpm=91.5,
                name="quarters spelling",
            ),
            BeatPolicy(
                grouping=(3, 2),
                division=Fraction(1, 3),
                name="division spelling",
            ),
        ],
        ids=("whole-note", "quarters", "division"),
    )
    def test_policy_json_round_trip_preserves_full_scalar(
        self, policy: BeatPolicy
    ) -> None:
        payload = json.loads(json.dumps(policy.to_dict()))
        restored = BeatPolicy.from_dict(payload)
        assert restored == policy
        assert restored.to_dict() == payload

    def test_metric_hierarchy_round_trip_preserves_named_policies(self) -> None:
        slow = BeatPolicy(grouping=(1, 1, 1), division=Fraction(1), name="slow")
        fast = BeatPolicy(
            grouping=(3, 3), division=Fraction(1, 2), bpm=120, name="fast"
        )
        hierarchy = MetricHierarchy(
            sections=((slow,), (slow, fast)), policies={"slow": slow, "fast": fast}
        )
        payload = json.loads(json.dumps(hierarchy.to_dict()))
        restored = MetricHierarchy.from_dict(payload)
        assert restored == hierarchy
        assert restored.to_dict() == payload
        restored.create_sections(["fast", ["slow", "fast"]])
        assert restored.sections == ((fast,), (slow, fast))


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


class TestMeasureWire:
    """Every concrete measure class survives JSON with exact fractions."""

    @pytest.mark.parametrize(
        "measure_class",
        [
            RegularMeasure,
            IrregularMeasure,
            SplitRegularMeasure,
            SplitIrregularMeasure,
            MeasureConstituent,
            CadenzaMeasure,
        ],
    )
    def test_concrete_class_and_all_fields_round_trip(
        self, measure_class: type[Measure]
    ) -> None:
        kwargs = {
            "id": "m7",
            "count": 7,
            "qstamp": Fraction(2, 3),
            "number": 5,
            "name": "5a",
            "time_signature": "7/9",
            "nominal_length": Fraction(7, 3),
            "actual_length": Fraction(5, 3),
            "start_repeat": True,
            "end_repeat": True,
            "next": ("m8", "m11"),
            "volta": 2,
        }
        if measure_class is MeasureConstituent:
            kwargs["offset_within_measure"] = Fraction(1, 3)
        measure = measure_class(**kwargs)
        payload = json.loads(json.dumps(measure.to_dict()))
        restored = Measure.from_dict(payload)
        assert type(restored) is measure_class
        assert restored == measure
        assert restored.qstamp == Fraction(2, 3)
        assert restored.nominal_length == Fraction(7, 3)
        assert restored.actual_length == Fraction(5, 3)
        if isinstance(restored, MeasureConstituent):
            assert restored.offset_within_measure == Fraction(1, 3)
        assert restored.to_dict() == payload

    def test_unknown_class_tag_names_known_classes(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"Unknown or missing Measure class 'UnknownMeasure'.*RegularMeasure",
        ):
            Measure.from_dict({"class": "UnknownMeasure"})

    def test_missing_class_tag_names_known_classes(self) -> None:
        payload = RegularMeasure(id="m1").to_dict()
        del payload["class"]
        with pytest.raises(
            ValueError,
            match=r"Unknown or missing Measure class None.*RegularMeasure",
        ):
            Measure.from_dict(payload)

    def test_undeclared_payload_key_is_rejected_by_name(self) -> None:
        payload = RegularMeasure(id="m1").to_dict()
        payload["offset_within_measure"] = rational_to_wire(Fraction(1, 3))
        with pytest.raises(
            ValueError,
            match=(
                "Measure class 'RegularMeasure' does not declare the keys: "
                "offset_within_measure"
            ),
        ):
            Measure.from_dict(payload)

    def test_subclass_rejects_a_different_tag(self) -> None:
        with pytest.raises(
            ValueError,
            match="does not match receiving subclass 'RegularMeasure'",
        ):
            RegularMeasure.from_dict(IrregularMeasure().to_dict())


# endregion
