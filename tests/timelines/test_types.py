"""Tests for the 6 Timeline subclasses.

This module tests:
- ContinuousLogicalTimeline, DiscreteLogicalTimeline
- ContinuousPhysicalTimeline, DiscretePhysicalTimeline
- ContinuousGraphicalTimeline, DiscreteGraphicalTimeline

Validity Rationale:
    The TTA model defines 6 timeline types across 3 domains and 2 modalities.
    Each type has:
    1. Restricted allowed units (domain-specific)
    2. Appropriate default unit and number_type
    3. Consistent behavior with base Timeline
    These tests verify type constraints are enforced correctly.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign.core import Domain, NumberType, TimeUnit
from timetoalign.timelines import (
    ContinuousGraphicalTimeline,
    ContinuousLogicalTimeline,
    ContinuousPhysicalTimeline,
    DiscreteGraphicalTimeline,
    DiscreteLogicalTimeline,
    DiscretePhysicalTimeline,
    GraphicalTimeline,
    LogicalTimeline,
    PhysicalTimeline,
    Timeline,
)

# region Parametrized Type Tests


class TestAllTimelineTypes:
    """Parametrized tests for all 6 timeline types."""

    @pytest.mark.parametrize(
        ("timeline_class", "legal_unit", "legal_length", "illegal_unit"),
        [
            (
                ContinuousLogicalTimeline,
                TimeUnit.quarters,
                Fraction(4, 1),
                TimeUnit.ticks,
            ),
            (DiscreteLogicalTimeline, TimeUnit.ticks, 480, TimeUnit.seconds),
            (ContinuousPhysicalTimeline, TimeUnit.seconds, 4.0, TimeUnit.samples),
            (DiscretePhysicalTimeline, TimeUnit.samples, 4, TimeUnit.seconds),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.centimeters,
                4.0,
                TimeUnit.pixels,
            ),
            (DiscreteGraphicalTimeline, TimeUnit.pixels, 4, TimeUnit.seconds),
        ],
    )
    def test_leaf_unit_contracts(
        self,
        timeline_class,
        legal_unit,
        legal_length,
        illegal_unit,
    ):
        """Each leaf type accepts its unit and rejects a forbidden one."""
        timeline = timeline_class(length=legal_length, unit=legal_unit)
        assert timeline.unit is legal_unit

        with pytest.raises(ValueError) as error:
            timeline_class(length=legal_length, unit=illegal_unit)

        assert type(error.value) is ValueError
        message = str(error.value)
        assert timeline_class.__name__ in message
        assert str(illegal_unit) in message
        assert "Allowed units:" in message

    @pytest.mark.parametrize(
        ("timeline_class", "unit", "number_type", "length"),
        [
            (ContinuousLogicalTimeline, TimeUnit.beats, NumberType.float, 4.0),
            (
                ContinuousLogicalTimeline,
                TimeUnit.beats,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (ContinuousLogicalTimeline, TimeUnit.quarters, NumberType.float, 4.0),
            (
                ContinuousLogicalTimeline,
                TimeUnit.quarters,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (
                ContinuousLogicalTimeline,
                TimeUnit.floating_measures,
                NumberType.float,
                4.0,
            ),
            (
                ContinuousLogicalTimeline,
                TimeUnit.floating_measures,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (ContinuousLogicalTimeline, TimeUnit.number, NumberType.float, 4.0),
            (
                ContinuousLogicalTimeline,
                TimeUnit.number,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (DiscreteLogicalTimeline, TimeUnit.ticks, NumberType.int, 4),
            (ContinuousPhysicalTimeline, TimeUnit.seconds, NumberType.float, 4.0),
            (
                ContinuousPhysicalTimeline,
                TimeUnit.seconds,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (
                ContinuousPhysicalTimeline,
                TimeUnit.milliseconds,
                NumberType.float,
                4.0,
            ),
            (
                ContinuousPhysicalTimeline,
                TimeUnit.milliseconds,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (ContinuousPhysicalTimeline, TimeUnit.minutes, NumberType.float, 4.0),
            (
                ContinuousPhysicalTimeline,
                TimeUnit.minutes,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (DiscretePhysicalTimeline, TimeUnit.samples, NumberType.int, 4),
            (DiscretePhysicalTimeline, TimeUnit.frames, NumberType.int, 4),
            (ContinuousGraphicalTimeline, TimeUnit.meters, NumberType.float, 4.0),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.meters,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.centimeters,
                NumberType.float,
                4.0,
            ),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.centimeters,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.millimeters,
                NumberType.float,
                4.0,
            ),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.millimeters,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (ContinuousGraphicalTimeline, TimeUnit.inches, NumberType.float, 4.0),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.inches,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (ContinuousGraphicalTimeline, TimeUnit.points, NumberType.float, 4.0),
            (
                ContinuousGraphicalTimeline,
                TimeUnit.points,
                NumberType.fraction,
                Fraction(4, 1),
            ),
            (DiscreteGraphicalTimeline, TimeUnit.pixels, NumberType.int, 4),
        ],
    )
    def test_leaf_legal_combinations_round_trip(
        self,
        timeline_class,
        unit,
        number_type,
        length,
    ):
        """Every legal leaf unit and number type survives a round trip."""
        original = timeline_class(
            length=length,
            unit=unit,
            number_type=number_type,
            uid="typed",
        )

        restored = Timeline.from_dict(original.to_dict())

        assert type(restored) is timeline_class
        assert restored.unit is unit
        assert restored.number_type is number_type
        assert restored.length.value == length

    def test_default_unit_is_valid(self, timeline_type_fixture):
        """Default unit is valid for the timeline type."""
        TimelineClass, default_unit, default_number_type, sample_length = (
            timeline_type_fixture
        )

        tl = TimelineClass(length=sample_length)
        assert tl.unit == default_unit

    @pytest.mark.parametrize(
        "timeline_class",
        [
            ContinuousLogicalTimeline,
            DiscreteLogicalTimeline,
            ContinuousPhysicalTimeline,
            DiscretePhysicalTimeline,
            ContinuousGraphicalTimeline,
            DiscreteGraphicalTimeline,
        ],
    )
    def test_base_from_dict_preserves_concrete_type(self, timeline_class):
        """The serialized class tag dispatches through the base registry."""
        original = timeline_class(length=8, uid="typed")
        restored = Timeline.from_dict(original.to_dict())
        assert type(restored) is timeline_class

    def test_default_number_type_is_valid(self, timeline_type_fixture):
        """Default number_type is valid for the timeline type."""
        TimelineClass, default_unit, default_number_type, sample_length = (
            timeline_type_fixture
        )

        tl = TimelineClass(length=sample_length)
        assert tl.number_type == default_number_type

    def test_timeline_has_correct_domain(self, timeline_type_fixture):
        """Timeline domain is derived from unit correctly."""
        TimelineClass, default_unit, default_number_type, sample_length = (
            timeline_type_fixture
        )

        tl = TimelineClass(length=sample_length)
        expected_domain = default_unit.domain
        assert tl.domain == expected_domain

    def test_timeline_can_hold_events(self, timeline_type_fixture):
        """All timeline types can hold events."""
        TimelineClass, default_unit, default_number_type, sample_length = (
            timeline_type_fixture
        )

        tl = TimelineClass(length=sample_length)

        # Create events with appropriate coordinate type
        if default_number_type == NumberType.int:
            coords = [0, int(sample_length) // 4, int(sample_length) // 2]
        elif default_number_type == NumberType.fraction:
            coords = [Fraction(0), sample_length / 4, sample_length / 2]
        else:
            coords = [0.0, float(sample_length) / 4, float(sample_length) / 2]

        events = [
            {
                "id": f"e_{i}",
                "temporal_type": "instant",
                "event_type": "Test",
                "instant": c,
            }
            for i, c in enumerate(coords)
        ]

        tl.add_events(events)
        assert tl.n_events == 3


# endregion


# region Logical Timeline Tests


class TestLogicalTimeline:
    """Tests for logical (musical) timelines."""

    def test_logical_timeline_allowed_units(self):
        """LogicalTimeline accepts musical units only."""
        # Should work
        LogicalTimeline(length=4.0, unit=TimeUnit.quarters)
        LogicalTimeline(length=4.0, unit=TimeUnit.beats)
        LogicalTimeline(length=4.0, unit=TimeUnit.floating_measures)
        LogicalTimeline(length=480, unit=TimeUnit.ticks)

        # Should fail
        with pytest.raises(ValueError, match="does not allow unit"):
            LogicalTimeline(length=10.0, unit=TimeUnit.seconds)

    def test_continuous_logical_default_fraction(self):
        """ContinuousLogicalTimeline defaults to Fraction coordinates."""
        tl = ContinuousLogicalTimeline(length=Fraction(4, 1))
        assert tl.number_type == NumberType.fraction
        assert tl.unit == TimeUnit.quarters

    def test_continuous_logical_accepts_float(self):
        """ContinuousLogicalTimeline also accepts float number_type."""
        tl = ContinuousLogicalTimeline(length=4.0, number_type=NumberType.float)
        assert tl.number_type == NumberType.float

    def test_continuous_logical_rejects_int(self):
        """ContinuousLogicalTimeline rejects int number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            ContinuousLogicalTimeline(length=4, number_type=NumberType.int)

    def test_continuous_logical_rejects_ticks(self):
        """ContinuousLogicalTimeline rejects ticks unit."""
        with pytest.raises(ValueError, match="does not allow unit"):
            ContinuousLogicalTimeline(length=480, unit=TimeUnit.ticks)

    def test_discrete_logical_default_int(self):
        """DiscreteLogicalTimeline defaults to int coordinates."""
        tl = DiscreteLogicalTimeline(length=1920)
        assert tl.number_type == NumberType.int
        assert tl.unit == TimeUnit.ticks

    def test_discrete_logical_rejects_float(self):
        """DiscreteLogicalTimeline rejects float number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            DiscreteLogicalTimeline(length=1920, number_type=NumberType.float)

    def test_discrete_logical_rejects_quarters(self):
        """DiscreteLogicalTimeline rejects continuous units."""
        with pytest.raises(ValueError, match="does not allow unit"):
            DiscreteLogicalTimeline(length=4, unit=TimeUnit.quarters)


# endregion


# region Physical Timeline Tests


class TestPhysicalTimeline:
    """Tests for physical (acoustic) timelines."""

    def test_physical_timeline_allowed_units(self):
        """PhysicalTimeline accepts physical units only."""
        # Should work
        PhysicalTimeline(length=10.0, unit=TimeUnit.seconds)
        PhysicalTimeline(length=1000.0, unit=TimeUnit.milliseconds)
        PhysicalTimeline(length=5.0, unit=TimeUnit.minutes)
        PhysicalTimeline(length=44100, unit=TimeUnit.samples)

        # Should fail
        with pytest.raises(ValueError, match="does not allow unit"):
            PhysicalTimeline(length=4.0, unit=TimeUnit.quarters)

    def test_continuous_physical_default_float(self):
        """ContinuousPhysicalTimeline defaults to float coordinates."""
        tl = ContinuousPhysicalTimeline(length=10.0)
        assert tl.number_type == NumberType.float
        assert tl.unit == TimeUnit.seconds

    def test_continuous_physical_accepts_fraction(self):
        """ContinuousPhysicalTimeline also accepts Fraction."""
        tl = ContinuousPhysicalTimeline(
            length=Fraction(10, 1), number_type=NumberType.fraction
        )
        assert tl.number_type == NumberType.fraction

    def test_continuous_physical_rejects_int(self):
        """ContinuousPhysicalTimeline rejects int number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            ContinuousPhysicalTimeline(length=10, number_type=NumberType.int)

    def test_continuous_physical_rejects_samples(self):
        """ContinuousPhysicalTimeline rejects discrete units."""
        with pytest.raises(ValueError, match="does not allow unit"):
            ContinuousPhysicalTimeline(length=44100, unit=TimeUnit.samples)

    def test_discrete_physical_default_int(self):
        """DiscretePhysicalTimeline defaults to int coordinates."""
        tl = DiscretePhysicalTimeline(length=44100)
        assert tl.number_type == NumberType.int
        assert tl.unit == TimeUnit.samples

    def test_discrete_physical_rejects_float(self):
        """DiscretePhysicalTimeline rejects float number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            DiscretePhysicalTimeline(length=44100, number_type=NumberType.float)

    def test_discrete_physical_rejects_seconds(self):
        """DiscretePhysicalTimeline rejects continuous units."""
        with pytest.raises(ValueError, match="does not allow unit"):
            DiscretePhysicalTimeline(length=10, unit=TimeUnit.seconds)


# endregion


# region Graphical Timeline Tests


class TestGraphicalTimeline:
    """Tests for graphical (visual) timelines."""

    def test_graphical_timeline_allowed_units(self):
        """GraphicalTimeline accepts graphical units only."""
        # Should work
        GraphicalTimeline(length=1920, unit=TimeUnit.pixels)
        GraphicalTimeline(length=21.0, unit=TimeUnit.centimeters)
        GraphicalTimeline(length=0.21, unit=TimeUnit.meters)
        GraphicalTimeline(length=8.5, unit=TimeUnit.inches)

        # Should fail
        with pytest.raises(ValueError, match="does not allow unit"):
            GraphicalTimeline(length=10.0, unit=TimeUnit.seconds)

    def test_continuous_graphical_default_float(self):
        """ContinuousGraphicalTimeline defaults to float coordinates."""
        tl = ContinuousGraphicalTimeline(length=100.0)
        assert tl.number_type == NumberType.float
        assert tl.unit == TimeUnit.centimeters

    def test_continuous_graphical_accepts_fraction(self):
        """ContinuousGraphicalTimeline also accepts Fraction."""
        tl = ContinuousGraphicalTimeline(
            length=Fraction(100, 1), number_type=NumberType.fraction
        )
        assert tl.number_type == NumberType.fraction

    def test_continuous_graphical_rejects_int(self):
        """ContinuousGraphicalTimeline rejects int number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            ContinuousGraphicalTimeline(length=100, number_type=NumberType.int)

    def test_continuous_graphical_rejects_pixels(self):
        """Pixels belong exclusively to discrete graphical timelines."""
        with pytest.raises(ValueError, match="does not allow unit"):
            ContinuousGraphicalTimeline(length=1206.4, unit=TimeUnit.pixels)

    def test_continuous_graphical_rejects_non_graphical_units(self):
        """The domain still holds: seconds are not a graphical unit."""
        with pytest.raises(ValueError, match="does not allow unit"):
            ContinuousGraphicalTimeline(length=10.0, unit=TimeUnit.seconds)

    def test_discrete_graphical_default_int(self):
        """DiscreteGraphicalTimeline defaults to int coordinates."""
        tl = DiscreteGraphicalTimeline(length=1920)
        assert tl.number_type == NumberType.int
        assert tl.unit == TimeUnit.pixels

    def test_discrete_graphical_rejects_float(self):
        """DiscreteGraphicalTimeline rejects float number_type."""
        with pytest.raises(ValueError, match="does not allow number_type"):
            DiscreteGraphicalTimeline(length=1920, number_type=NumberType.float)

    def test_discrete_graphical_rejects_centimeters(self):
        """DiscreteGraphicalTimeline rejects continuous units."""
        with pytest.raises(ValueError, match="does not allow unit"):
            DiscreteGraphicalTimeline(length=100, unit=TimeUnit.centimeters)


# endregion


# region Domain Property Tests


class TestDomainProperties:
    """Test domain-related properties."""

    def test_logical_timeline_domain_is_logical(self):
        """Logical timelines have Domain.logical."""
        tl = ContinuousLogicalTimeline(length=Fraction(4, 1))
        assert tl.domain == Domain.logical

    def test_physical_timeline_domain_is_physical(self):
        """Physical timelines have Domain.physical."""
        tl = ContinuousPhysicalTimeline(length=10.0)
        assert tl.domain == Domain.physical

    def test_graphical_timeline_domain_is_graphical(self):
        """Graphical timelines have Domain.graphical."""
        tl = ContinuousGraphicalTimeline(length=100.0)
        assert tl.domain == Domain.graphical


# endregion


# region Inheritance Tests


class TestInheritance:
    """Test class hierarchy relationships."""

    def test_continuous_logical_is_logical(self):
        """ContinuousLogicalTimeline is a LogicalTimeline."""
        tl = ContinuousLogicalTimeline(length=Fraction(4, 1))
        assert isinstance(tl, LogicalTimeline)
        assert isinstance(tl, Timeline)

    def test_discrete_logical_is_logical(self):
        """DiscreteLogicalTimeline is a LogicalTimeline."""
        tl = DiscreteLogicalTimeline(length=1920)
        assert isinstance(tl, LogicalTimeline)
        assert isinstance(tl, Timeline)

    def test_continuous_physical_is_physical(self):
        """ContinuousPhysicalTimeline is a PhysicalTimeline."""
        tl = ContinuousPhysicalTimeline(length=10.0)
        assert isinstance(tl, PhysicalTimeline)
        assert isinstance(tl, Timeline)

    def test_discrete_physical_is_physical(self):
        """DiscretePhysicalTimeline is a PhysicalTimeline."""
        tl = DiscretePhysicalTimeline(length=44100)
        assert isinstance(tl, PhysicalTimeline)
        assert isinstance(tl, Timeline)

    def test_continuous_graphical_is_graphical(self):
        """ContinuousGraphicalTimeline is a GraphicalTimeline."""
        tl = ContinuousGraphicalTimeline(length=100.0)
        assert isinstance(tl, GraphicalTimeline)
        assert isinstance(tl, Timeline)

    def test_discrete_graphical_is_graphical(self):
        """DiscreteGraphicalTimeline is a GraphicalTimeline."""
        tl = DiscreteGraphicalTimeline(length=1920)
        assert isinstance(tl, GraphicalTimeline)
        assert isinstance(tl, Timeline)


# endregion


# region Cross-Domain Compatibility Tests


class TestDiscreteAndContinuousPredicates:
    """Test is_discrete and is_continuous convenience properties."""

    def test_continuous_logical_is_continuous(self):
        """ContinuousLogicalTimeline reports is_continuous=True."""
        tl = ContinuousLogicalTimeline(length=Fraction(4, 1))
        assert tl.is_continuous is True
        assert tl.is_discrete is False

    def test_discrete_logical_is_discrete(self):
        """DiscreteLogicalTimeline reports is_discrete=True."""
        tl = DiscreteLogicalTimeline(length=1920)
        assert tl.is_discrete is True
        assert tl.is_continuous is False

    def test_continuous_physical_is_continuous(self):
        """ContinuousPhysicalTimeline reports is_continuous=True."""
        tl = ContinuousPhysicalTimeline(length=10.0)
        assert tl.is_continuous is True
        assert tl.is_discrete is False

    def test_discrete_physical_is_discrete(self):
        """DiscretePhysicalTimeline reports is_discrete=True."""
        tl = DiscretePhysicalTimeline(length=44100)
        assert tl.is_discrete is True
        assert tl.is_continuous is False

    def test_continuous_graphical_is_continuous(self):
        """ContinuousGraphicalTimeline reports is_continuous=True."""
        tl = ContinuousGraphicalTimeline(length=100.0)
        assert tl.is_continuous is True
        assert tl.is_discrete is False

    def test_discrete_graphical_is_discrete(self):
        """DiscreteGraphicalTimeline reports is_discrete=True."""
        tl = DiscreteGraphicalTimeline(length=1920)
        assert tl.is_discrete is True
        assert tl.is_continuous is False

    def test_base_timeline_seconds_is_continuous(self):
        """Base Timeline with seconds unit is continuous."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds)
        assert tl.is_continuous is True
        assert tl.is_discrete is False

    def test_base_timeline_ticks_is_discrete(self):
        """Base Timeline with ticks unit is discrete."""
        tl = Timeline(length=480, unit=TimeUnit.ticks)
        assert tl.is_discrete is True
        assert tl.is_continuous is False

    def test_predicates_are_complementary(self, timeline_type_fixture):
        """is_discrete and is_continuous are always complementary."""
        TimelineClass, default_unit, default_number_type, sample_length = (
            timeline_type_fixture
        )
        tl = TimelineClass(length=sample_length)
        assert tl.is_discrete != tl.is_continuous


# endregion


# region To Typed Tests


class TestToTyped:
    """Test the to_typed() method for upgrading base Timeline to subtypes."""

    def test_base_timeline_seconds_becomes_continuous_physical(self):
        """Base Timeline with seconds upgrades to ContinuousPhysicalTimeline."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds)
        typed = tl.to_typed()
        assert type(typed) is ContinuousPhysicalTimeline
        assert typed.length.value == 10.0
        assert typed.unit == TimeUnit.seconds

    def test_base_timeline_ticks_becomes_discrete_logical(self):
        """Base Timeline with ticks upgrades to DiscreteLogicalTimeline."""
        tl = Timeline(length=1920, unit=TimeUnit.ticks, number_type=NumberType.int)
        typed = tl.to_typed()
        assert type(typed) is DiscreteLogicalTimeline
        assert typed.length.value == 1920

    def test_base_timeline_pixels_becomes_discrete_graphical(self):
        """Base Timeline with pixels upgrades to DiscreteGraphicalTimeline."""
        tl = Timeline(length=1920, unit=TimeUnit.pixels, number_type=NumberType.int)
        typed = tl.to_typed()
        assert type(typed) is DiscreteGraphicalTimeline

    def test_base_timeline_quarters_becomes_continuous_logical(self):
        """Base Timeline with quarters upgrades to ContinuousLogicalTimeline."""
        tl = Timeline(length=4.0, unit=TimeUnit.quarters)
        typed = tl.to_typed()
        assert type(typed) is ContinuousLogicalTimeline

    def test_base_timeline_samples_becomes_discrete_physical(self):
        """Base Timeline with samples upgrades to DiscretePhysicalTimeline."""
        tl = Timeline(length=44100, unit=TimeUnit.samples, number_type=NumberType.int)
        typed = tl.to_typed()
        assert type(typed) is DiscretePhysicalTimeline

    def test_base_timeline_centimeters_becomes_continuous_graphical(self):
        """Base Timeline with centimeters upgrades to ContinuousGraphicalTimeline."""
        tl = Timeline(length=100.0, unit=TimeUnit.centimeters)
        typed = tl.to_typed()
        assert type(typed) is ContinuousGraphicalTimeline

    def test_already_typed_returns_self(self):
        """to_typed on already-typed timeline returns self."""
        tl = ContinuousPhysicalTimeline(length=10.0)
        typed = tl.to_typed()
        assert typed is tl

    def test_to_typed_preserves_id(self):
        """to_typed preserves the timeline's unique ID."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds, uid="my_id")
        typed = tl.to_typed()
        assert typed.id == "my_id"

    def test_to_typed_preserves_name(self):
        """to_typed preserves the timeline's name."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds, name="audio_track")
        typed = tl.to_typed()
        assert typed.name == "audio_track"

    def test_to_typed_preserves_meta(self):
        """to_typed preserves metadata."""
        tl = Timeline(
            length=10.0,
            unit=TimeUnit.seconds,
            meta={"source": "test.wav"},
        )
        typed = tl.to_typed()
        assert typed.meta == {"source": "test.wav"}

    def test_to_typed_preserves_events(self):
        """to_typed preserves events."""
        tl = Timeline(length=10.0, unit=TimeUnit.seconds)
        tl.add_events(
            [
                {
                    "id": "e1",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 1.0,
                },
                {
                    "id": "e2",
                    "temporal_type": "instant",
                    "event_type": "Beat",
                    "instant": 2.0,
                },
            ]
        )
        typed = tl.to_typed()
        assert typed.n_events == 2

    def test_to_typed_preserves_regions(self):
        """to_typed preserves regions."""
        tl = Timeline(length=100.0, unit=TimeUnit.seconds)
        tl.add_region("Chorus", start=30.0, end=60.0)
        typed = tl.to_typed()
        assert "Chorus" in typed
        region = typed.get_region("Chorus")
        assert region.start.value == 30.0
        assert region.end.value == 60.0


# endregion


# region Cross-Domain Compatibility Tests


class TestCrossDomainCompatibility:
    """Test that cross-domain nesting is prevented."""

    def test_logical_cannot_contain_physical(self):
        """Logical timeline rejects physical children."""
        logical = ContinuousLogicalTimeline(length=Fraction(8, 1))
        physical = ContinuousPhysicalTimeline(length=5.0)

        with pytest.raises(ValueError, match="does not match"):
            logical.add_child(physical, offset=Fraction(0))

    def test_physical_cannot_contain_graphical(self):
        """Physical timeline rejects graphical children."""
        physical = ContinuousPhysicalTimeline(length=20.0)
        graphical = ContinuousGraphicalTimeline(length=100.0)

        with pytest.raises(ValueError, match="does not match"):
            physical.add_child(graphical, offset=0.0)

    def test_graphical_cannot_contain_logical(self):
        """Graphical timeline rejects logical children."""
        graphical = ContinuousGraphicalTimeline(length=200.0)
        logical = ContinuousLogicalTimeline(length=Fraction(4, 1))

        with pytest.raises(ValueError, match="does not match"):
            graphical.add_child(logical, offset=0.0)


# endregion
