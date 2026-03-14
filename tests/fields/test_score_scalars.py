"""Tests for Circle 1 score scalars: MidiPitch, SpelledPitch, Note, Measure, Harmony."""

from __future__ import annotations

from fractions import Fraction

import pytest

from timetoalign.core.enums import TimeUnit
from timetoalign.core.protocols import (
    HarmonyLike,
    MeasureLike,
    NoteLike,
    PitchLike,
    SemanticTypeLike,
)
from timetoalign.core.scalars.harmony import Harmony
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
        """Construct MidiPitch with midi_number and pitch_class."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        assert p.midi_number == 60
        assert p.pitch_class == 0

    def test_construction_b3(self) -> None:
        """Construct MidiPitch for B3 (midi 59, pitch_class 11)."""
        p = MidiPitch(midi_number=59, pitch_class=11)
        assert p.midi_number == 59
        assert p.pitch_class == 11

    def test_pitchlike_conformance(self) -> None:
        """MidiPitch satisfies PitchLike protocol."""
        p = MidiPitch(midi_number=64, pitch_class=4)
        assert isinstance(p, PitchLike)

    def test_semantic_type_like_conformance(self) -> None:
        """MidiPitch satisfies SemanticTypeLike protocol."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        assert isinstance(p, SemanticTypeLike)

    def test_semantic_type(self) -> None:
        """MidiPitch.semantic_type == 'MidiPitch'."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        assert p.semantic_type == "MidiPitch"

    def test_metadata_dict(self) -> None:
        """metadata_dict returns correct keys/values."""
        p = MidiPitch(midi_number=59, pitch_class=11)
        md = p.metadata_dict()
        assert md["field_type"] == "PitchField"
        assert md["pitch_type"] == "midi"

    def test_frozen_immutable(self) -> None:
        """MidiPitch is frozen (immutable)."""
        p = MidiPitch(midi_number=60, pitch_class=0)
        with pytest.raises(AttributeError):
            p.midi_number = 61  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SpelledPitch
# ---------------------------------------------------------------------------


class TestSpelledPitch:
    """Tests for SpelledPitch scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct SpelledPitch for C4."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        assert p.step == "C"
        assert p.alter == 0
        assert p.octave == 4
        assert p.fifths == 0
        assert p.cents == 0.0

    def test_construction_gsharp(self) -> None:
        """Construct SpelledPitch for G#3."""
        p = SpelledPitch(step="G", alter=1, octave=3, fifths=8, cents=0.0)
        assert p.step == "G"
        assert p.alter == 1
        assert p.octave == 3

    def test_pitchlike_conformance(self) -> None:
        """SpelledPitch satisfies PitchLike protocol."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        assert isinstance(p, PitchLike)

    def test_midi_number_computation_c4(self) -> None:
        """SpelledPitch for C4 computes midi_number == 60."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        assert p.midi_number == 60

    def test_midi_number_computation_b3(self) -> None:
        """SpelledPitch for B3 computes midi_number == 59."""
        p = SpelledPitch(step="B", alter=0, octave=3, fifths=5, cents=0.0)
        assert p.midi_number == 59

    def test_midi_number_computation_gsharp3(self) -> None:
        """SpelledPitch for G#3 computes midi_number == 56."""
        p = SpelledPitch(step="G", alter=1, octave=3, fifths=8, cents=0.0)
        assert p.midi_number == 56

    def test_pitch_class_computation_c(self) -> None:
        """SpelledPitch for C4 has pitch_class == 0."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        assert p.pitch_class == 0

    def test_pitch_class_computation_b(self) -> None:
        """SpelledPitch for B3 has pitch_class == 11."""
        p = SpelledPitch(step="B", alter=0, octave=3, fifths=5, cents=0.0)
        assert p.pitch_class == 11

    def test_semantic_type(self) -> None:
        """SpelledPitch.semantic_type == 'SpelledPitch'."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        assert p.semantic_type == "SpelledPitch"

    def test_frozen_immutable(self) -> None:
        """SpelledPitch is frozen (immutable)."""
        p = SpelledPitch(step="C", alter=0, octave=4, fifths=0, cents=0.0)
        with pytest.raises(AttributeError):
            p.step = "D"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Note
# ---------------------------------------------------------------------------


class TestNote:
    """Tests for Note scalar construction and protocol conformance."""

    def test_construction_with_pitch(self) -> None:
        """Construct Note with onset, offset, duration, and a MidiPitch."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        pitch = MidiPitch(midi_number=59, pitch_class=11)
        note = Note(
            onset=onset,
            offset=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=0.5,
            pitch=pitch,
            voice=1,
            staff=1,
            velocity=None,
        )
        assert note.onset == onset
        assert note.pitch is not None
        assert note.pitch.midi_number == 59
        assert note.duration == 0.5
        assert note.voice == 1
        assert note.staff == 1

    def test_construction_rest_no_pitch(self) -> None:
        """Construct a rest (Note with pitch=None)."""
        onset = Coordinate(Fraction(1), TimeUnit.quarters)
        rest = Note(
            onset=onset,
            offset=Coordinate(Fraction(2), TimeUnit.quarters),
            duration=1.0,
            pitch=None,
            voice=1,
            staff=1,
            velocity=None,
        )
        assert rest.pitch is None
        assert rest.duration == 1.0

    def test_notelike_conformance(self) -> None:
        """Note satisfies NoteLike protocol."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            onset=onset,
            offset=Coordinate(Fraction(1, 8), TimeUnit.quarters),
            duration=0.125,
            pitch=MidiPitch(midi_number=60, pitch_class=0),
            voice=1,
            staff=1,
            velocity=80,
        )
        assert isinstance(note, NoteLike)

    def test_semantic_type(self) -> None:
        """Note.semantic_type == 'Note'."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            onset=onset,
            offset=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=0.5,
            pitch=MidiPitch(midi_number=60, pitch_class=0),
            voice=1,
            staff=1,
            velocity=None,
        )
        assert note.semantic_type == "Note"

    def test_frozen_immutable(self) -> None:
        """Note is frozen (immutable)."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        note = Note(
            onset=onset,
            offset=Coordinate(Fraction(1, 2), TimeUnit.quarters),
            duration=0.5,
            pitch=MidiPitch(midi_number=60, pitch_class=0),
            voice=1,
            staff=1,
            velocity=None,
        )
        with pytest.raises(AttributeError):
            note.duration = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Measure
# ---------------------------------------------------------------------------


class TestMeasure:
    """Tests for Measure scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct Measure with mc, mn, onset, duration, timesig, keysig."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=1,
            mn="1",
            onset=onset,
            duration=2.0,
            time_signature=(2, 4),
            key_signature="E",
        )
        assert m.mc == 1
        assert m.mn == "1"
        assert m.onset == onset
        assert m.duration == 2.0
        assert m.time_signature == (2, 4)
        assert m.key_signature == "E"

    def test_construction_anacrusis(self) -> None:
        """Construct Measure for an anacrusis bar (mc=1, mn='0')."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=1,
            mn="0",
            onset=onset,
            duration=0.5,
            time_signature=(2, 4),
            key_signature="E",
        )
        assert m.mc == 1
        assert m.mn == "0"

    def test_measurelike_conformance(self) -> None:
        """Measure satisfies MeasureLike protocol."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=1,
            mn="1",
            onset=onset,
            duration=2.0,
            time_signature=(2, 4),
            key_signature="E",
        )
        assert isinstance(m, MeasureLike)

    def test_time_signature_tuple(self) -> None:
        """time_signature returns exact (num, den) tuple."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=3,
            mn="3",
            onset=onset,
            duration=2.0,
            time_signature=(6, 8),
            key_signature="c",
        )
        assert m.time_signature == (6, 8)
        assert isinstance(m.time_signature, tuple)

    def test_semantic_type(self) -> None:
        """Measure.semantic_type == 'Measure'."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=1,
            mn="1",
            onset=onset,
            duration=2.0,
            time_signature=(4, 4),
            key_signature="C",
        )
        assert m.semantic_type == "Measure"

    def test_frozen_immutable(self) -> None:
        """Measure is frozen (immutable)."""
        onset = Coordinate(Fraction(0), TimeUnit.quarters)
        m = Measure(
            mc=1,
            mn="1",
            onset=onset,
            duration=2.0,
            time_signature=(2, 4),
            key_signature="E",
        )
        with pytest.raises(AttributeError):
            m.mc = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Harmony
# ---------------------------------------------------------------------------


class TestHarmony:
    """Tests for Harmony scalar construction and protocol conformance."""

    def test_construction_basic(self) -> None:
        """Construct Harmony with DCML-standard fields."""
        h = Harmony(
            label="c.i",
            globalkey="c",
            localkey="i",
            numeral="i",
            form="",
            figbass="",
            chord_type="m",
            root=0,
            bass_note=0,
        )
        assert h.label == "c.i"
        assert h.globalkey == "c"
        assert h.localkey == "i"
        assert h.numeral == "i"
        assert h.chord_type == "m"
        assert h.root == 0
        assert h.bass_note == 0

    def test_construction_dominant_seventh(self) -> None:
        """Construct Harmony for V65."""
        h = Harmony(
            label="V65",
            globalkey="c",
            localkey="i",
            numeral="V",
            form="",
            figbass="65",
            chord_type="Mm7",
            root=1,
            bass_note=5,
        )
        assert h.label == "V65"
        assert h.numeral == "V"
        assert h.figbass == "65"
        assert h.chord_type == "Mm7"

    def test_harmonylike_conformance(self) -> None:
        """Harmony satisfies HarmonyLike protocol."""
        h = Harmony(
            label="i",
            globalkey="c",
            localkey="i",
            numeral="i",
            form="",
            figbass="",
            chord_type="m",
            root=0,
            bass_note=0,
        )
        assert isinstance(h, HarmonyLike)

    def test_semantic_type(self) -> None:
        """Harmony.semantic_type == 'Harmony'."""
        h = Harmony(
            label="V",
            globalkey="c",
            localkey="i",
            numeral="V",
            form="",
            figbass="",
            chord_type="M",
            root=1,
            bass_note=1,
        )
        assert h.semantic_type == "Harmony"

    def test_metadata_dict(self) -> None:
        """metadata_dict returns correct structure."""
        h = Harmony(
            label="c.i",
            globalkey="c",
            localkey="i",
            numeral="i",
            form="",
            figbass="",
            chord_type="m",
            root=0,
            bass_note=0,
        )
        md = h.metadata_dict()
        assert md["field_type"] == "HarmonyField"
        assert md["standard"] == "dcml"

    def test_frozen_immutable(self) -> None:
        """Harmony is frozen (immutable)."""
        h = Harmony(
            label="V",
            globalkey="c",
            localkey="i",
            numeral="V",
            form="",
            figbass="",
            chord_type="M",
            root=1,
            bass_note=1,
        )
        with pytest.raises(AttributeError):
            h.label = "i"  # type: ignore[misc]
