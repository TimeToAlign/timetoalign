"""SoloLoader: Loader for `.solo` performance-precision specimen files.

A ``.solo`` file is a header-less tab-separated table emitted by
performance-analysis tools.  Each row records one note-on or note-off
event in a polyphonic performance, with six columns:

==  ==============================================================
0   ``position`` — ``"<measure_number>+<numerator>/<denominator>"``;
    integer measure number followed by a literal ``+`` and a
    fractional offset within the measure (in quarters).
1   ``duration`` — quarter-note duration as a fraction
    (``"3/4"``, ``"0/1"`` for note-off).
2   ``channel`` — MIDI channel (integer).
3   ``pitch`` — MIDI pitch (integer 0–127).
4   ``velocity`` — MIDI velocity (integer 0–127; 0 marks a
    note-off in this format).
5   ``note_id`` — opaque alphanumeric note identifier
    (``"n1b8xktz"``).
==  ==============================================================

Example::

    1+3/8\\t1/2\\t90\\t63\\t80\\tnwp1wrk

``SoloLoader`` demonstrates the ``column_specs`` (Step 1) +
``field_specs`` (Step 2) pipeline end-to-end:

* Step 1 splits the composite ``position`` column into a
  ``measure_number`` + ``mn_onset`` struct via
  :class:`CompositeFieldParser`; the ``duration`` column is parsed by
  a :class:`DenominateNumberField` blueprint bound to
  ``TimeUnit.quarters``.
* Step 2 promotes the integer ``pitch`` column to an
  :class:`EnharmonicPitchField` and the string ``note_id`` column to a
  paired :class:`IdField`, using the blueprint-mode
  ``source_fields=<name>`` shorthand.
"""

from __future__ import annotations

from typing import Any, ClassVar

from timetoalign.core import (
    DenominateNumberField,
    EnharmonicPitchField,
    IdField,
    IntField,
    MeasureNumberField,
    RedundantNumberField,
    StringField,
    TimeUnit,
)

from .csv import CsvLoader
from .field_parsers import CompositeFieldParser

# region SoloLoader


class SoloLoader(CsvLoader):
    """Loader for ``.solo`` performance-precision specimen files.

    The loader operates header-less on a tab-separated source and
    routes the canonical start coordinate through the synthesised
    ``measure_number`` + ``mn_onset`` pair produced by Step 1; the
    canonical ``duration`` column is also produced by Step 1 (as a
    :class:`DenominateNumberField` bound to ``TimeUnit.quarters``).

    The loader does NOT (currently) reconcile measure-number into a
    flat-quarter coordinate — measures are second-order time units
    and resolution against a :class:`MetricMap` is out of scope.  The
    ``start`` coordinate is therefore left null; callers that need
    flat-quarter onsets should consume ``mn_onset`` directly and
    consult their measure map.
    """

    # Header-less, tab-delimited.
    delimiter: ClassVar[str] = "\t"
    header_row: ClassVar[int] = -1  # sentinel for "no header"

    # No canonical start/end/duration: the start coordinate is
    # second-order (measure_number + onset within measure).  We route
    # the canonical start through the synthesised "mn_onset" raw
    # column produced by column_specs, leaving measure resolution to
    # downstream consumers.
    id_column: ClassVar[str | None] = None  # auto-generated
    name_column: ClassVar[str | None] = None
    start_column: ClassVar[str] = "mn_onset"
    end_column: ClassVar[str | None] = None
    duration_column: ClassVar[str | None] = "duration"
    event_type_column: ClassVar[str | None] = None
    default_event_type: ClassVar[str] = "Note"

    # Quarter notes as fractions.
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters

    column_specs: ClassVar[list[Any]] = [
        # col 0: measure_number + fractional onset within the measure.
        CompositeFieldParser(
            separator="+",
            parts=[
                MeasureNumberField,  # SemanticField class — default name 'measure_number'
                RedundantNumberField(name="mn_onset"),  # raw rational struct
            ],
            name="position",
        ),
        # col 1: duration as a fraction of a quarter note (semantic).
        DenominateNumberField(name="duration", unit=TimeUnit.quarters),
        # cols 2–5: simple typed columns.
        IntField(name="channel"),
        IntField(name="pitch"),
        IntField(name="velocity"),
        StringField(name="note_id"),
    ]

    field_specs: ClassVar[list[Any]] = [
        # Promote raw pitch int → MIDI-style EnharmonicPitchField.
        EnharmonicPitchField(source_fields="pitch"),
        # Promote raw note_id string → paired IdField.
        IdField(source_fields="note_id"),
    ]

    def _read_dataframe(self, source):  # type: ignore[override]
        """Read a header-less ``.solo`` file.

        The source is tab-separated with no header line; we read with
        ``header=None`` and assign positional column names that match
        the ``column_specs`` declaration order.

        Args:
            source: Path to the ``.solo`` file.

        Returns:
            DataFrame with named columns matching the column_specs.
        """
        import pandas as pd

        # Positional names matched to column_specs declaration order.
        names = ["position", "duration", "channel", "pitch", "velocity", "note_id"]
        return pd.read_csv(
            source,
            sep=self.delimiter,
            header=None,
            names=names,
            encoding=self.encoding,
            dtype=str,
        )


# endregion
