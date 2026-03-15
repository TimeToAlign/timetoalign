"""Tests for Circle 1 score scalars: MidiPitch, SpelledPitch, Note, Measure, DcmlHarmony."""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign.core.enums import TimeUnit
from timetoalign.core.protocols import (
    DcmlHarmonyLike,
    HarmonyLike,
    MeasureLike,
    NoteLike,
    PitchLike,
    SemanticTypeLike,
    SpecificPitchClassLike,
)
from timetoalign.core.scalars.harmony import DcmlHarmony
from timetoalign.core.scalars.measure import Measure
from timetoalign.core.scalars.note import Note
from timetoalign.core.scalars.pitch import MidiPitch, SpelledPitch
from timetoalign.core.types import Coordinate

# ---------------------------------------------------------------------------
# MidiPitch
# ---------------------------------------------------------------------------


class TestMidiPitch:
    """Tests for MidiPitch scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct MidiPitch with midi_number only (pitch_class auto-derived)."""
        p = MidiPitch(midi_number=60)
        assert p.midi_number == 60
        assert p.pitch_class == 0

    def test_construction_b3(self) -> None:
        """Construct MidiPitch for B3 (midi 59, pitch_class auto-derived to 11)."""
        p = MidiPitch(midi_number=59)
        assert p.midi_number == 59
        assert p.pitch_class == 11

    def test_pitchlike_conformance(self) -> None:
        """MidiPitch satisfies PitchLike protocol."""
        p = MidiPitch(midi_number=64)
        assert isinstance(p, PitchLike)

    def test_specific_pitch_class_like_conformance(self) -> None:
        """MidiPitch satisfies SpecificPitchClassLike protocol."""
        p = MidiPitch(midi_number=64)
        assert isinstance(p, SpecificPitchClassLike)

    def test_semantic_type_like_conformance(self) -> None:
        """MidiPitch satisfies SemanticTypeLike protocol."""
        p = MidiPitch(midi_number=60)
        assert isinstance(p, SemanticTypeLike)

    def test_semantic_type(self) -> None:
        """MidiPitch.semantic_type == 'MidiPitch'."""
        p = MidiPitch(midi_number=60)
        assert p.semantic_type == "MidiPitch"

    def test_metadata_dict(self) -> None:
        """metadata_dict returns correct keys/values."""
        p = MidiPitch(midi_number=59)
        md = p.metadata_dict()
        assert md["field_type"] == "EnharmonicPitchField"
        assert md["pitch_type"] == "midi"

    def test_frozen_immutable(self) -> None:
        """MidiPitch is frozen (immutable)."""
        p = MidiPitch(midi_number=60)
        with pytest.raises(AttributeError):
            p.midi_number = 61  # type: ignore[misc]

    def test_octave_property(self) -> None:
        """MidiPitch.octave computes correctly."""
        p = MidiPitch(midi_number=60)
        assert p.octave == 4  # C4 = 60


# ---------------------------------------------------------------------------
# SpelledPitch
# ---------------------------------------------------------------------------


class TestSpelledPitch:
    """Tests for SpelledPitch scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct SpelledPitch for C4 (fifths auto-derived)."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        assert p.step == "C"
        assert p.alter == 0
        assert p.octave == 4
        assert p.fifths == 0  # auto-derived: C=0
        assert p.cents == 0.0  # default

    def test_construction_gsharp(self) -> None:
        """Construct SpelledPitch for G#3 (fifths auto-derived)."""
        p = SpelledPitch(step="G", alter=1, octave=3)
        assert p.step == "G"
        assert p.alter == 1
        assert p.octave == 3
        assert p.fifths == 8  # auto-derived: G=1 + 7*1=8

    def test_pitchlike_conformance(self) -> None:
        """SpelledPitch satisfies PitchLike protocol."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        assert isinstance(p, PitchLike)

    def test_midi_number_computation_c4(self) -> None:
        """SpelledPitch for C4 computes midi_number == 60."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        assert p.midi_number == 60

    def test_midi_number_computation_b3(self) -> None:
        """SpelledPitch for B3 computes midi_number == 59."""
        p = SpelledPitch(step="B", alter=0, octave=3)
        assert p.midi_number == 59

    def test_midi_number_computation_gsharp3(self) -> None:
        """SpelledPitch for G#3 computes midi_number == 56."""
        p = SpelledPitch(step="G", alter=1, octave=3)
        assert p.midi_number == 56

    def test_pitch_class_computation_c(self) -> None:
        """SpelledPitch for C4 has pitch_class == 0."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        assert p.pitch_class == 0

    def test_pitch_class_computation_b(self) -> None:
        """SpelledPitch for B3 has pitch_class == 11."""
        p = SpelledPitch(step="B", alter=0, octave=3)
        assert p.pitch_class == 11

    def test_semantic_type(self) -> None:
        """SpelledPitch.semantic_type == 'SpelledPitch'."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        assert p.semantic_type == "SpelledPitch"

    def test_frozen_immutable(self) -> None:
        """SpelledPitch is frozen (immutable)."""
        p = SpelledPitch(step="C", alter=0, octave=4)
        with pytest.raises(AttributeError):
            p.step = "D"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Note
# ---------------------------------------------------------------------------


class TestNote:
    """Tests for Note scalar construction and protocol conformance."""

    def test_construction_with_pitch(self) -> None:
        """Construct Note with start, end, duration, and a MidiPitch."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        pitch = MidiPitch(midi_number=59)
        note = Note(
            start=start,
            end=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            pitch=pitch,
            voice=1,
            staff=1,
            velocity=None,
        )
        assert note.start == start
        assert note.pitch is not None
        assert note.pitch.midi_number == 59
        assert note.duration is not None
        assert note.voice == 1
        assert note.staff == 1

    def test_construction_rest_no_pitch(self) -> None:
        """Construct a rest (Note with pitch=None)."""
        start = Coordinate(Fraction(1), TimeUnit.quarters)
        rest = Note(
            start=start,
            end=Coordinate(Fraction(2), TimeUnit.quarters),
            duration=Coordinate(Fraction(1), TimeUnit.quarters),
            pitch=None,
            voice=1,
            staff=1,
            velocity=None,
        )
        assert rest.pitch is None
        assert rest.duration is not None

    def test_notelike_conformance(self) -> None:
        """Note satisfies NoteLike protocol."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            start=start,
            end=Coordinate(Fraction(1, 8), TimeUnit.quarters),
            duration=Coordinate(Fraction(1, 8), TimeUnit.quarters),
            pitch=MidiPitch(midi_number=60),
            voice=1,
            staff=1,
            velocity=80,
        )
        assert isinstance(note, NoteLike)

    def test_semantic_type(self) -> None:
        """Note.semantic_type == 'Note'."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            start=start,
            end=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            pitch=MidiPitch(midi_number=60),
            voice=1,
            staff=1,
            velocity=None,
        )
        assert note.semantic_type == "Note"

    def test_frozen_immutable(self) -> None:
        """Note is frozen (immutable)."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            start=start,
            end=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            pitch=MidiPitch(midi_number=60),
            voice=1,
            staff=1,
            velocity=None,
        )
        with pytest.raises(AttributeError):
            note.duration = Coordinate(1.0, TimeUnit.quarters)  # type: ignore[misc]

    def test_instrument_field(self) -> None:
        """Note supports optional instrument field."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            start=start,
            end=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            pitch=MidiPitch(midi_number=60),
            voice=1,
            staff=1,
            velocity=80,
            instrument="violin",
        )
        assert note.instrument == "violin"

    def test_instrument_default_none(self) -> None:
        """Note.instrument defaults to None."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            start=start,
            end=None,
            duration=None,
            pitch=None,
            voice=None,
            staff=None,
            velocity=None,
        )
        assert note.instrument is None


# ---------------------------------------------------------------------------
# Measure
# ---------------------------------------------------------------------------


class TestMeasure:
    """Tests for Measure scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct Measure with mc, mn, start, duration, timesig, keysig."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=1,
            mn="1",
            start=start,
            duration=Coordinate(Fraction(2), TimeUnit.quarters),
            time_signature=(2, 4),
            key_signature="E",
        )
        assert m.id == 1
        assert m.mn == "1"
        assert m.start == start
        assert m.duration is not None
        assert m.time_signature == (2, 4)
        assert m.key_signature == "E"

    def test_construction_anacrusis(self) -> None:
        """Construct Measure for an anacrusis bar (id=1, mn='0')."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=1,
            mn="0",
            start=start,
            duration=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            time_signature=(2, 4),
            key_signature="E",
        )
        assert m.id == 1
        assert m.mn == "0"

    def test_measurelike_conformance(self) -> None:
        """Measure satisfies MeasureLike protocol."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=1,
            mn="1",
            start=start,
            duration=Coordinate(Fraction(2), TimeUnit.quarters),
            time_signature=(2, 4),
            key_signature="E",
        )
        assert isinstance(m, MeasureLike)

    def test_time_signature_tuple(self) -> None:
        """time_signature returns exact (num, den) tuple."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=3,
            mn="3",
            start=start,
            duration=Coordinate(Fraction(2), TimeUnit.quarters),
            time_signature=(6, 8),
            key_signature="c",
        )
        assert m.time_signature == (6, 8)
        assert isinstance(m.time_signature, tuple)

    def test_semantic_type(self) -> None:
        """Measure.semantic_type == 'Measure'."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=1,
            mn="1",
            start=start,
            duration=Coordinate(Fraction(2), TimeUnit.quarters),
            time_signature=(4, 4),
            key_signature="C",
        )
        assert m.semantic_type == "Measure"

    def test_frozen_immutable(self) -> None:
        """Measure is frozen (immutable)."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            id=1,
            mn="1",
            start=start,
            duration=Coordinate(Fraction(2), TimeUnit.quarters),
            time_signature=(2, 4),
            key_signature="E",
        )
        with pytest.raises(AttributeError):
            m.id = 2  # type: ignore[misc]

    def test_flow_control_defaults(self) -> None:
        """Flow control fields default to False/None."""
        start = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(id=1, mn="1", start=start, time_signature=(4, 4))
        assert m.start_repeat is False
        assert m.end_repeat is False
        assert m.next_ids is None
        assert m.volta is None


# ---------------------------------------------------------------------------
# DcmlHarmony (was Harmony)
# ---------------------------------------------------------------------------


class TestDcmlHarmony:
    """Tests for DcmlHarmony scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct DcmlHarmony with DCML-standard fields."""
        h = DcmlHarmony(
            label="c.i",
            globalkey="c",
            localkey="i",
            numeral="i",
            chord_type="m",
            root=0,
            bass=0,
        )
        assert h.label == "c.i"
        assert h.globalkey == "c"
        assert h.localkey == "i"
        assert h.numeral == "i"
        assert h.chord_type == "m"
        assert h.root == 0
        assert h.bass == 0

    def test_construction_dominant_seventh(self) -> None:
        """Construct DcmlHarmony for V65."""
        h = DcmlHarmony(
            label="V65",
            globalkey="c",
            localkey="i",
            numeral="V",
            chord_type="Mm7",
            inversion=1,
            root=1,
            bass=5,
        )
        assert h.label == "V65"
        assert h.numeral == "V"
        assert h.inversion == 1
        assert h.chord_type == "Mm7"

    def test_harmonylike_conformance(self) -> None:
        """DcmlHarmony satisfies HarmonyLike protocol."""
        h = DcmlHarmony(
            label="i",
            globalkey="c",
            localkey="i",
            numeral="i",
            chord_type="m",
            root=0,
            bass=0,
        )
        assert isinstance(h, HarmonyLike)

    def test_dcmllabellike_conformance(self) -> None:
        """DcmlHarmony satisfies DcmlHarmonyLike protocol."""
        h = DcmlHarmony(
            label="i",
            globalkey="c",
            localkey="i",
            numeral="i",
            chord_type="m",
            root=0,
            bass=0,
        )
        assert isinstance(h, DcmlHarmonyLike)

    def test_semantic_type(self) -> None:
        """DcmlHarmony.semantic_type == 'DcmlHarmony'."""
        h = DcmlHarmony(label="V")
        assert h.semantic_type == "DcmlHarmony"

    def test_metadata_dict(self) -> None:
        """metadata_dict returns correct structure."""
        h = DcmlHarmony(label="c.i")
        md = h.metadata_dict()
        assert md["field_type"] == "DcmlHarmonyField"
        assert md["standard"] == "dcml"

    def test_frozen_immutable(self) -> None:
        """DcmlHarmony is frozen (immutable)."""
        h = DcmlHarmony(label="V")
        with pytest.raises(AttributeError):
            h.label = "i"  # type: ignore[misc]
