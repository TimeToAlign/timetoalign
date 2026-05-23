"""CsvLoader, TsvLoader, Ms3Loader, LabLoader: Concrete tabular loaders.

These loaders provide ready-to-use configurations for common tabular formats.
For custom column mappings, subclass TabularLoader directly.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pyarrow as pa

from timetoalign.core import NumberType, TimeUnit
from timetoalign.core.events import (
    _BASE_FIFTHS,
    _STEP_TO_SEMITONE,
    SpecificPitchField,
    _parse_pitch_label,
)

from .base import TabularLoader

module_logger = logging.getLogger(__name__)


# region CsvLoader


class CsvLoader(TabularLoader):
    """Loader for CSV (comma-separated values) files.

    CsvLoader provides a general-purpose CSV loader with sensible defaults.
    Customize by subclassing or by passing configuration to __init__.

    Default Configuration:
        - Delimiter: comma (,)
        - Start column: "start"
        - End column: "end" (if present)
        - ID column: "id" (if present, else auto-generated)
        - Coordinate unit: seconds
        - Coordinate type: float

    Examples:
        >>> loader = CsvLoader()
        >>> loader.load("events.csv")
        >>> print(loader.events.count)

        >>> # Custom configuration via subclass
        >>> class MyLoader(CsvLoader):
        ...     start_column = "onset_time"
        ...     end_column = "offset_time"
        ...     column_specs = {"pitch": int, "velocity": int}
    """

    # CSV uses comma delimiter
    delimiter: ClassVar[str] = ","

    # Default column names for generic CSV
    id_column: ClassVar[str | None] = "id"
    name_column: ClassVar[str | None] = "name"
    start_column: ClassVar[str] = "start"
    end_column: ClassVar[str | None] = "end"
    event_type_column: ClassVar[str | None] = "event_type"
    default_event_type: ClassVar[str] = "Event"

    # Default coordinate configuration
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    coordinate_type: ClassVar[NumberType] = NumberType.float


# endregion


# region TsvLoader


class TsvLoader(TabularLoader):
    """Loader for TSV (tab-separated values) files.

    TsvLoader is pre-configured for tab-delimited files, common in
    music annotation datasets.

    Default Configuration:
        - Delimiter: tab (\\t)
        - Start column: "start"
        - End column: "end" (if present)
        - ID column: "id" (if present, else auto-generated)
        - Coordinate unit: seconds
        - Coordinate type: float

    Examples:
        >>> loader = TsvLoader()
        >>> loader.load("annotations.tsv")

        >>> # For ms3-style TSV files, use Ms3Loader instead
        >>> from timetoalign.loader.score import Ms3Loader
    """

    # TSV uses tab delimiter
    delimiter: ClassVar[str] = "\t"

    # Default column names (same as CSV)
    id_column: ClassVar[str | None] = "id"
    name_column: ClassVar[str | None] = "name"
    start_column: ClassVar[str] = "start"
    end_column: ClassVar[str | None] = "end"
    event_type_column: ClassVar[str | None] = "event_type"
    default_event_type: ClassVar[str] = "Event"

    # Default coordinate configuration
    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    coordinate_type: ClassVar[NumberType] = NumberType.float


# endregion


# region Ms3Loader


class Ms3Loader(TabularLoader):
    """Loader for ms3 (MuseScore3) TSV annotation files.

    Ms3Loader handles the TSV format produced by the ms3 parser library.
    These files contain detailed note/chord/measure annotations from MuseScore files.

    File Format (notes.tsv):
        mc  mn  quarterbeats  quarterbeats_all_endings  duration_qb  ...
        1   0   0             0                         1.0          ...
        1   0   1/2           1/2                       0.5          ...

    Field mapping:
        - start: "quarterbeats" (fraction format: "0", "1/2", "3/4")
        - duration: "duration" (fraction strings like "1/4")
        - name: "name" (note name like "A4", "C#5")
        - event_type: Defaults to "Note"

    Pitch handling:
        Creates an SP (specific pitch) field from the "name" column,
        validated against "tpc" (fifths) and "midi" (MIDI number).
        Redundant pitch columns (midi, octave, tpc) are not included
        as extra columns since they are derivable from SP.

    Extra columns captured:
        - staff: Staff number
        - voice: Voice number
        - chord_id: Chord identifier
        - mc: Measure count
        - mn: Measure number

    Examples:
        >>> loader = Ms3Loader()
        >>> loader.load("beethoven.notes.tsv")
        >>> print(f"Loaded {len(loader.events)} notes")
    """

    # TSV format with tab delimiter
    delimiter: ClassVar[str] = "\t"

    # ms3 column mapping
    id_column: ClassVar[str | None] = None  # Auto-generate
    name_column: ClassVar[str | None] = "name"
    # Use quarterbeats_all_endings as primary (includes notes in volta brackets),
    # fall back to quarterbeats if not present
    start_column: ClassVar[str] = "quarterbeats_all_endings"
    _fallback_start_column: ClassVar[str | None] = "quarterbeats"  # type: ignore[assignment]
    end_column: ClassVar[str | None] = None  # Use duration instead
    # Use "duration" column (fraction strings like "1/4") instead of "duration_qb" (floats)
    # This preserves exact rational values for musical durations
    duration_column: ClassVar[str | None] = "duration"
    event_type_column: ClassVar[str | None] = None
    default_event_type: ClassVar[str] = "Note"

    # Coordinate configuration: quarter beats as fractions
    _default_unit: ClassVar[TimeUnit] = TimeUnit.quarters
    coordinate_type: ClassVar[NumberType] = NumberType.fraction

    # Step 1 — column_specs.  Pitch handling is delegated to
    # _post_process_columns (SP construction from name + tpc/midi
    # validation).
    column_specs: ClassVar[dict[str, Any]] = {
        "staff": int,
        "voice": int,
        "chord_id": int,
        "mc": int,  # Measure count
        "mn": int,  # Measure number
    }

    # ms3-aware fraction columns: columns known to carry fraction strings.
    # The CoordinateParser handles fraction strings ("3/4") natively, so
    # no pre-conversion is needed. This list is informational and can be
    # used by subclasses for dtype inference if needed.
    _FRACTION_FIELDS: ClassVar[tuple[str, ...]] = (
        "quarterbeats",
        "quarterbeats_all_endings",
        "duration_qb",
        "mc_onset",
        "mn_onset",
        "duration",
        "nominal_duration",
        "scalar",
        "act_dur",
    )

    def _post_process_columns(self, df: pd.DataFrame, columns: dict[str, Any]) -> None:
        """Create SP pitch field from name column, validate against tpc/midi."""
        name_arr = columns.get("name")
        if name_arr is None:
            return

        # Check if this looks like a notes file (has pitch-related columns)
        has_pitch_columns = "name" in df.columns and (
            "midi" in df.columns or "tpc" in df.columns
        )
        if not has_pitch_columns:
            return

        # Parse pitch labels from the "name" column → SP (step, alter, octave)
        n = len(name_arr)
        steps: list[str] = []
        alters = np.zeros(n, dtype=np.int64)
        octaves = np.zeros(n, dtype=np.int64)
        fifths_values = np.zeros(n, dtype=np.int64)
        null_mask = np.zeros(n, dtype=bool)

        for i in range(n):
            label = name_arr[i]
            if label is None or (isinstance(label, str) and label == "nan"):
                null_mask[i] = True
                steps.append("C")
                continue
            try:
                step, alter, octave = _parse_pitch_label(str(label))
                steps.append(step)
                alters[i] = alter
                octaves[i] = octave if octave is not None else 4
                fifths_values[i] = _BASE_FIFTHS.get(step, 0) + 7 * alter
            except (ValueError, KeyError):
                null_mask[i] = True
                steps.append("C")

        # Build the pydantic-derived SpecificPitch struct array:
        # {step, alter, octave, cents}
        sp_struct_type = SpecificPitchField.pa_schema
        step_pa = pa.array(steps, type=pa.string())
        alter_pa = pa.array(alters.tolist(), type=pa.int64())
        octave_pa = pa.array(octaves.tolist(), type=pa.int64())
        cents_pa = pa.array([0.0] * n, type=pa.float64())

        if null_mask.any():
            pitch_arr = pa.StructArray.from_arrays(
                [step_pa, alter_pa, octave_pa, cents_pa],
                fields=list(sp_struct_type),
                mask=pa.array(null_mask.tolist()),
            )
        else:
            pitch_arr = pa.StructArray.from_arrays(
                [step_pa, alter_pa, octave_pa, cents_pa],
                fields=list(sp_struct_type),
            )

        columns["pitch"] = pitch_arr

        # Decorate the column with paired-class metadata.
        pf = SpecificPitchField.from_field(
            (pitch_arr, pa.field("pitch", sp_struct_type))
        )
        # SemanticField.to_field() (inherited from DataField) returns the
        # bare pa.Field; inject the b"timetoalign" metadata explicitly so
        # discovery still works.
        from timetoalign.core.fields import (
            TIMETOALIGN_METADATA_KEY,
            metadata_blob_from_dict,
        )

        meta = metadata_blob_from_dict({"field_type": "SpecificPitchField"})
        decorated = pf.field.with_metadata({TIMETOALIGN_METADATA_KEY: meta})
        self._extra_schema_fields.append(decorated)

        # Validate against tpc and midi from the original DataFrame
        self._validate_pitch_against_tpc(df, fifths_values, null_mask)
        self._validate_pitch_against_midi(df, name_arr, null_mask)

    def _validate_pitch_against_tpc(
        self,
        df: pd.DataFrame,
        fifths_values: np.ndarray,
        null_mask: np.ndarray,
    ) -> None:
        """Validate SP fifths position against ms3's tpc column."""
        if "tpc" not in df.columns:
            return
        tpc_col = df["tpc"]
        mismatches = 0
        for i in range(len(fifths_values)):
            if null_mask[i] or pd.isna(tpc_col.iloc[i]):
                continue
            expected_fifths = fifths_values[i]
            actual_tpc = int(tpc_col.iloc[i])
            if expected_fifths != actual_tpc:
                mismatches += 1
                if mismatches <= 3:
                    self._logger.warning(
                        f"Pitch validation: row {i} tpc={actual_tpc} vs "
                        f"computed fifths={expected_fifths}"
                    )
        if mismatches > 3:
            self._logger.warning(f"Pitch validation: {mismatches} total tpc mismatches")

    def _validate_pitch_against_midi(
        self,
        df: pd.DataFrame,
        name_arr: np.ndarray,
        null_mask: np.ndarray,
    ) -> None:
        """Validate SP against ms3's midi column."""
        if "midi" not in df.columns:
            return
        midi_col = df["midi"]
        mismatches = 0
        for i in range(len(name_arr)):
            if null_mask[i] or pd.isna(midi_col.iloc[i]):
                continue
            label = str(name_arr[i])
            try:
                step, alter, octave = _parse_pitch_label(label)
                if octave is None:
                    continue
                expected_midi = (
                    (octave + 1) * 12 + _STEP_TO_SEMITONE.get(step, 0) + alter
                )
                actual_midi = int(midi_col.iloc[i])
                if expected_midi != actual_midi:
                    mismatches += 1
                    if mismatches <= 3:
                        self._logger.warning(
                            f"Pitch validation: row {i} midi={actual_midi} vs "
                            f"computed={expected_midi} for '{label}'"
                        )
            except (ValueError, KeyError):
                continue
        if mismatches > 3:
            self._logger.warning(
                f"Pitch validation: {mismatches} total midi mismatches"
            )


# endregion


# region LabLoader


class LabLoader(TabularLoader):
    """Loader for Audacity/Praat label files (.lab, .txt).

    Lab files are tab-separated with columns: start, end, label.
    Common in speech/music annotation workflows.

    File Format:
        start_time\\tend_time\\tlabel
        0.0\\t1.5\\tverse
        1.5\\t3.0\\tchorus

    Examples:
        >>> loader = LabLoader()
        >>> loader.load("regions.lab")
    """

    delimiter: ClassVar[str] = "\t"
    header_row: ClassVar[int] = -1  # No header row

    # Lab files have fixed columns: start, end, label
    id_column: ClassVar[str | None] = None  # Auto-generate
    name_column: ClassVar[str | None] = None
    start_column: ClassVar[str] = "0"  # Field index as string when no header
    end_column: ClassVar[str | None] = "1"
    event_type_column: ClassVar[str | None] = None
    default_event_type: ClassVar[str] = "Region"

    _default_unit: ClassVar[TimeUnit] = TimeUnit.seconds
    coordinate_type: ClassVar[NumberType] = NumberType.float

    def _read_dataframe(self, source):
        """Read lab file without header."""
        import pandas as pd

        df = pd.read_csv(
            source,
            sep=self.delimiter,
            header=None,
            names=["start", "end", "label"],
            encoding=self.encoding,
        )
        return df

    # Override field names to match the names we assigned
    start_column: ClassVar[str] = "start"
    end_column: ClassVar[str | None] = "end"


# endregion
