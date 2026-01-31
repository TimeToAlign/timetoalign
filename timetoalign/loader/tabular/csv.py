"""CsvLoader and TsvLoader: Concrete implementations for CSV/TSV files.

These loaders provide ready-to-use configurations for common tabular formats.
For custom column mappings, subclass TabularLoader directly.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from timetoalign.core import NumberType, TimeUnit

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
        ...     extra_columns = {"pitch": "note_number"}
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

    Column Mapping:
        - start: "quarterbeats" (fraction format: "0", "1/2", "3/4")
        - duration: "duration_qb" (float in quarter beats)
        - name: "name" (note name like "A4", "C#5")
        - event_type: Defaults to "Note"

    Extra columns captured:
        - midi: MIDI note number
        - octave: Note octave
        - tpc: Tonal pitch class
        - staff: Staff number
        - voice: Voice number
        - chord_id: Chord identifier

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

    # Extra columns from ms3 format
    extra_columns: ClassVar[list] = [
        "midi",
        "octave",
        "tpc",
        "staff",
        "voice",
        "chord_id",
        "mc",  # Measure count
        "mn",  # Measure number
    ]


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
    start_column: ClassVar[str] = "0"  # Column index as string when no header
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

    # Override column names to match the names we assigned
    start_column: ClassVar[str] = "start"
    end_column: ClassVar[str | None] = "end"


# endregion
