"""Regression tests for ``EventData.get_field(<SemanticField subclass>)``.

These tests pin the class-based discovery contract surfaced in the
``type_hierarchy_landing`` work package (INC-3):

- ``events.get_field(PitchField)`` MUST succeed on raw TSV-loader output
  even when the loader did not (yet) inject ``b"timetoalign"`` JSON
  metadata onto the pitch column.  Discovery falls through to a
  structural match (the column is a ``midi_pitch`` / ``specific_pitch``
  struct) and constructs the field via ``PitchField.from_field()``.
- ``events.get_field(PitchField)`` MUST raise ``KeyError`` when no
  matching column exists, preserving the existing contract for
  ``_get_field_by_class``.

See ``tests/loader/README.md`` for the wider taxonomy of loader tests
and the test-data provisioning rules.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from timetoalign.core import TimeUnit
from timetoalign.fields.pitch import PitchField
from timetoalign.loader import EventData
from timetoalign.loader.score.tsv import TSVLoader
from timetoalign.testdata import ensure_data


def test_get_field_by_class_returns_first_match() -> None:
    """``events.get_field(PitchField)`` discovers the first pitch column.

    The Chopin Op. 10 No. 3 notes TSV produces a NoteEventData table whose
    ``midi_pitch`` (struct ``{ep, epc}``) and ``specific_pitch``
    (struct ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``)
    columns carry no ``b"timetoalign"`` metadata.  Class-based discovery
    must still find them — first match wins, matching column order in
    the table schema.
    """
    vienna = ensure_data("vienna_1x22")
    loader = TSVLoader().load(vienna / "ms3" / "chopin_op10_no3.notes.tsv")
    events = loader.get_events()

    pf = events.get_field(PitchField)
    assert isinstance(pf, PitchField)
    # Per loader.score.tsv column order, midi_pitch precedes specific_pitch.
    assert pf.name == "midi_pitch"
    # Subscripting must succeed on a non-blueprint field.
    scalar = pf[3]
    assert scalar is not None


def test_get_field_by_class_finds_specific_and_midi_pitch() -> None:
    """``get_fields(PitchField)`` returns both raw struct columns.

    Discovery is by struct shape, so both the ``midi_pitch`` and
    ``specific_pitch`` columns are recognised as ``PitchField``-shaped.
    """
    vienna = ensure_data("vienna_1x22")
    loader = TSVLoader().load(vienna / "ms3" / "chopin_op10_no3.notes.tsv")
    events = loader.get_events()

    fields = events.get_fields(PitchField)
    names = [f.name for f in fields]
    assert names == ["midi_pitch", "specific_pitch"]


def test_get_field_by_class_raises_when_no_match() -> None:
    """``events.get_field(PitchField)`` raises ``KeyError`` when no column matches.

    An ``EventData`` built from rows lacking any pitch column must not
    accidentally match a generic struct (e.g. the ``start`` /
    ``end`` / ``duration`` coordinate structs); the strict shape detector
    rules them out.
    """
    rows = [
        {
            "id": "beat_1",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": 0,
        },
        {
            "id": "beat_2",
            "temporal_type": "instant",
            "event_type": "Beat",
            "instant": 480,
        },
    ]
    events = EventData.from_dicts(rows, TimeUnit.ticks)

    with pytest.raises(KeyError, match="PitchField"):
        events.get_field(PitchField)


def test_matches_pa_field_rejects_coordinate_structs() -> None:
    """``PitchField.matches_pa_field`` must NOT claim coordinate structs.

    The strict shape detector underlying the third-line discovery
    strategy must distinguish a pitch struct from a generic
    ``{value, numerator, denominator}`` Coordinate struct or a
    ``{num, den}`` Fraction struct.  This guard prevents
    ``get_field(PitchField)`` from returning a spurious match on the
    ``start`` / ``end`` / ``duration`` columns that exist on every
    ``EventData`` table.
    """
    coord_type = pa.struct(
        [
            pa.field("value", pa.float64()),
            pa.field("numerator", pa.int64()),
            pa.field("denominator", pa.int64()),
        ]
    )
    coord_field = pa.field("start", coord_type)
    assert PitchField.matches_pa_field(coord_field) is False

    frac_type = pa.struct([pa.field("num", pa.int64()), pa.field("den", pa.int64())])
    frac_field = pa.field("mc_onset", frac_type)
    assert PitchField.matches_pa_field(frac_field) is False
