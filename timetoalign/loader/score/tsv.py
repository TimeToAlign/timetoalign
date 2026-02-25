"""TSVLoader: Load scores from TSV using ms3."""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Any

from typing_extensions import Self

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import coordinate_to_struct, fraction_to_struct

from .base import ScoreLoader
from .bundle import ScoreStore
from .stores import (
    AnnotationEventData,
    ControlEventData,
    MeasureData,
    NoteEventData,
)

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)


class TSVLoader(ScoreLoader):
    """Load symbolic scores from DCML-style TSV files.

    Wraps ms3.load_tsv to load standard tabular data.
    Returns a ScoreStore with category-specific data.

    Unlike single-file loaders (PartituraLoader, Music21Loader), TSV corpora
    store each facet (notes, measures, chords, harmonies) in a separate file.
    By default the loader loads exactly the files it is given. Pass
    ``auto_discover=True`` to have it locate companion facet files
    automatically.

    Auto-discovery uses two strategies:

    1. **Flat siblings** (ms3 convention): for ``name.notes.tsv``, look for
       ``name.measures.tsv``, ``name.chords.tsv``, ``name.harmonies.tsv``
       in the same directory.
    2. **Facet directories** (DCML corpus convention): if the file sits in a
       directory whose name matches a facet (e.g., ``notes/``), look for
       sibling directories named after the other facets and find a file
       with the same stem there.

    TSV columns (notes.tsv gold standard):
    - mc, mn: Measure count/number
    - quarterbeats: Continuous logical time (Fraction string)
    - duration_qb: Duration in quarter beats (float)
    - mc_onset, mn_onset: Measure-relative offsets (Fraction string)
    - timesig: Time signature context
    - staff, voice: Part context
    - duration, nominal_duration, scalar: Symbolic duration
    - tpc, midi, name, octave: Pitch info
    - tied, gracenote, chord_id: Note attributes
    """

    # Known DCML/ms3 facet names (used for discovery).
    _FACETS: tuple[str, ...] = ("notes", "measures", "chords", "harmonies")

    def __init__(self, *args, auto_discover: bool = False, **kwargs) -> None:
        """Initialize the TSVLoader.

        Args:
            *args: Passed to ``ScoreLoader.__init__``.
            auto_discover: If True, automatically locate companion facet
                files (measures, chords, harmonies, etc.) for every source
                file passed to `load`. Defaults to False.
            **kwargs: Passed to ``ScoreLoader.__init__``.
        """
        super().__init__(*args, **kwargs)
        self._auto_discover = auto_discover

    @classmethod
    def from_file(cls, *paths: Path | str, auto_discover: bool = False) -> "TSVLoader":
        """Create a loader and load TSV files in one step.

        Convenience constructor for loading one or more TSV files.

        Args:
            *paths: Paths to TSV files (notes, measures, harmonies, chords).
            auto_discover: If True, automatically locate companion facet
                files for each source.

        Returns:
            A new TSVLoader instance with the files already loaded.

        Examples:
            >>> loader = TSVLoader.from_file("score.notes.tsv", "score.measures.tsv")
            >>> loader.store.summary()

            >>> # Auto-discover all facet files from a single notes file:
            >>> loader = TSVLoader.from_file("score.notes.tsv", auto_discover=True)
        """
        loader = cls(auto_discover=auto_discover)
        loader.load(*paths)
        return loader

    # region Auto-discovery

    @staticmethod
    def _parse_facet(path: Path) -> str | None:
        """Extract the facet name from a TSV filename.

        Recognises two naming conventions:
        - ms3 flat: ``name.notes.tsv`` -> ``"notes"``
        - plain:    ``notes.tsv``      -> ``"notes"``

        Args:
            path: Path to a TSV file.

        Returns:
            The facet name if recognised, else None.
        """
        parts = path.name.lower().rsplit(".", maxsplit=2)
        # "name.notes.tsv" -> ["name", "notes", "tsv"]
        if len(parts) == 3 and parts[2] == "tsv" and parts[1] in TSVLoader._FACETS:
            return parts[1]
        # "notes.tsv" -> ["notes", "tsv"]
        if len(parts) == 2 and parts[1] == "tsv" and parts[0] in TSVLoader._FACETS:
            return parts[0]
        return None

    @staticmethod
    def _discover_companions(source: Path) -> list[Path]:
        """Locate companion facet files for *source*.

        Uses two strategies in order:

        1. **Flat siblings** — for ``name.<facet>.tsv``, glob
           ``name.*.<other_facet>.tsv`` in the same directory.
        2. **Facet directories** — if the parent directory name equals the
           current facet (e.g. ``notes/``), look for sibling directories
           named after the remaining facets and find a file whose stem
           matches.

        Files with an ``_unfolded`` suffix are matched only to other
        ``_unfolded`` files and vice-versa, to avoid mixing folded and
        unfolded variants.

        Args:
            source: Resolved path to a TSV file.

        Returns:
            Companion paths (may be empty). Never includes *source* itself.
        """
        source = source.resolve()
        facet = TSVLoader._parse_facet(source)
        if facet is None:
            return []

        companions: list[Path] = []
        other_facets = [f for f in TSVLoader._FACETS if f != facet]
        name_lower = source.name.lower()

        # Strategy 1: flat siblings (name.facet.tsv convention)
        # Extract the piece stem: everything before ".<facet>.tsv"
        dot_facet = f".{facet}."
        idx = name_lower.find(dot_facet)
        if idx >= 0:
            piece_stem = source.name[:idx]  # preserve original case
            for other in other_facets:
                candidate = source.parent / f"{piece_stem}.{other}.tsv"
                if candidate.resolve() != source and candidate.is_file():
                    companions.append(candidate.resolve())
            if companions:
                return companions

        # Strategy 2: facet directories
        parent_name = source.parent.name.lower()
        if parent_name == facet:
            grandparent = source.parent.parent
            # Derive the expected filename in sibling facet directories.
            # Replace the facet directory name in the stem if present,
            # otherwise keep the original name.
            file_stem = source.name
            for other in other_facets:
                sibling_dir = grandparent / other
                if sibling_dir.is_dir():
                    candidate = sibling_dir / file_stem
                    if candidate.is_file():
                        companions.append(candidate.resolve())

        return companions

    def load(self, *sources: Path | str) -> Self:
        """Load one or more TSV source files.

        When ``auto_discover`` is enabled, each source file is expanded to
        include its companion facet files (measures, chords, harmonies,
        etc.) before loading. Files that have already been loaded (or that
        appear more than once in the expanded set) are silently skipped.

        Args:
            *sources: Paths to TSV files.

        Returns:
            Self, for method chaining.
        """
        if not self._auto_discover:
            return super().load(*sources)

        # Expand sources with discovered companions, preserving order and
        # deduplicating by resolved path.
        seen: set[Path] = {p.resolve() for p in self._sources}
        expanded: list[Path] = []
        for source in sources:
            path = Path(source).resolve()
            if path in seen:
                continue
            seen.add(path)
            expanded.append(path)
            for companion in self._discover_companions(path):
                if companion not in seen:
                    seen.add(companion)
                    expanded.append(companion)
                    logger.debug("Auto-discovered companion: %s", companion)

        return super().load(*expanded)

    # endregion

    def _load_source(self, source: Path) -> ScoreStore:
        """Load TSV file(s) and return ScoreStore.

        Args:
            source: Path to TSV file or directory.

        Returns:
            ScoreStore with populated data.
        """
        try:
            import ms3
        except ImportError:
            raise ImportError("TSVLoader requires 'ms3'. Install with pip install ms3")

        df = ms3.load_tsv(str(source))
        fname = source.name.lower()

        # Determine category from filename
        if "measures" in fname:
            return self._load_measures(df, source)
        elif "notes" in fname:
            return self._load_notes(df, source)
        elif "harmonies" in fname:
            return self._load_annotations(df, source, subtype="Harmony")
        elif "chords" in fname:
            return self._load_controls(df, source, subtype="Chord")
        else:
            # Default to notes if has pitch columns
            if "midi" in df.columns or "tpc" in df.columns:
                return self._load_notes(df, source)
            return ScoreStore.empty()

    def _parse_fraction(self, val: Any) -> Fraction | None:
        """Parse fraction from TSV value (string like '3/4' or float)."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        if isinstance(val, Fraction):
            return val
        if isinstance(val, str):
            if "/" in val:
                parts = val.split("/")
                return Fraction(int(parts[0]), int(parts[1]))
            try:
                return Fraction(val).limit_denominator(10000)
            except ValueError:
                return None
        if isinstance(val, (int, float)):
            return Fraction(val).limit_denominator(10000)
        return None

    def _load_notes(self, df: pd.DataFrame, source: Path) -> ScoreStore:
        """Load notes TSV into NoteEventData."""
        import pandas as pd

        if df.empty:
            return ScoreStore.empty()

        note_rows = []
        has_rests = False

        for _, row in df.iterrows():
            # Temporal - Primary
            qb = self._parse_fraction(row.get("quarterbeats", 0))
            qb_float = float(qb) if qb else 0.0

            dur_qb = self._parse_fraction(row.get("duration_qb", 0))
            dur_qb_float = float(dur_qb) if dur_qb else 0.0

            # Temporal - Measure context
            mc = int(row["mc"]) if pd.notna(row.get("mc")) else None
            mn = str(row.get("mn", "")) if pd.notna(row.get("mn")) else None
            mc_onset = self._parse_fraction(row.get("mc_onset"))
            mn_onset = self._parse_fraction(row.get("mn_onset"))
            timesig = (
                str(row.get("timesig", "")) if pd.notna(row.get("timesig")) else None
            )

            # Temporal - Symbolic duration
            duration = self._parse_fraction(row.get("duration"))
            nominal_duration = self._parse_fraction(row.get("nominal_duration"))
            scalar = self._parse_fraction(row.get("scalar"))

            # Pitch - MIDI
            midi_pitch = None
            if pd.notna(row.get("midi")):
                ep = int(row["midi"])
                midi_pitch = {"ep": ep, "epc": ep % 12}

            # Pitch - Spelled
            spelled_pitch = None
            if pd.notna(row.get("name")):
                name = str(row["name"])
                step = name[0] if name else "C"
                alter = 0
                if len(name) > 1:
                    alter = (
                        name[1:].count("#") - name[1:].count("b") - name[1:].count("-")
                    )

                octave = int(row["octave"]) if pd.notna(row.get("octave")) else 4

                gpc_map = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
                gpc_int = gpc_map.get(step, 0)

                acc_str = ""
                if alter > 0:
                    acc_str = "♯" * alter
                elif alter < 0:
                    acc_str = "♭" * abs(alter)

                base_fifths = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
                spc_int = (
                    int(row["tpc"])
                    if pd.notna(row.get("tpc"))
                    else base_fifths.get(step, 0) + (7 * alter)
                )

                spelled_pitch = {
                    "gpc_int": gpc_int,
                    "gpc_str": step,
                    "acc": alter,
                    "spc_int": spc_int,
                    "spc_str": f"{step}{acc_str}",
                    "sp": f"{step}{acc_str}{octave}",
                    "cents": 0.0,
                }

            octave_val = int(row["octave"]) if pd.notna(row.get("octave")) else None
            tpc_val = int(row["tpc"]) if pd.notna(row.get("tpc")) else None

            # Attributes
            velocity = (
                int(row.get("velocity", 64)) if pd.notna(row.get("velocity")) else 64
            )
            tied = int(row["tied"]) if pd.notna(row.get("tied")) else 0
            gracenote = (
                str(row["gracenote"]) if pd.notna(row.get("gracenote")) else None
            )
            chord_id = int(row["chord_id"]) if pd.notna(row.get("chord_id")) else None

            voice = int(row["voice"]) if pd.notna(row.get("voice")) else None
            staff = int(row["staff"]) if pd.notna(row.get("staff")) else None
            part_id = str(row.get("part", "P1"))

            # Check if rest (no pitch)
            if midi_pitch is None:
                has_rests = True

            note_rows.append(
                {
                    "id": f"note_{qb_float}_{row.name}",
                    "name": str(row.get("name", "")),
                    "temporal_type": "interval" if dur_qb_float > 0 else "instant",
                    "event_type": "Note" if midi_pitch else "Rest",
                    # Temporal - core coordinates use coordinate_to_struct
                    # (value/numerator/denominator format for EventData)
                    "quarterbeats": (
                        coordinate_to_struct(qb)
                        if qb is not None
                        else coordinate_to_struct(0)
                    ),
                    "quarterbeats_float": qb_float,
                    "duration_qb": (
                        coordinate_to_struct(dur_qb) if dur_qb is not None else None
                    ),
                    "duration_qb_float": dur_qb_float,
                    "mc": mc,
                    "mn": mn,
                    # Extra fraction fields use fraction_to_struct (num/den format)
                    "mc_onset": (
                        fraction_to_struct(mc_onset) if mc_onset is not None else None
                    ),
                    "mn_onset": (
                        fraction_to_struct(mn_onset) if mn_onset is not None else None
                    ),
                    "timesig": timesig,
                    "duration": (
                        fraction_to_struct(duration) if duration is not None else None
                    ),
                    "nominal_duration": (
                        fraction_to_struct(nominal_duration)
                        if nominal_duration is not None
                        else None
                    ),
                    "scalar": (
                        fraction_to_struct(scalar) if scalar is not None else None
                    ),
                    # Pitch
                    "midi_pitch": midi_pitch,
                    "spelled_pitch": spelled_pitch,
                    "tpc": tpc_val,
                    "octave": octave_val,
                    # Attributes
                    "velocity": velocity,
                    "tied": tied,
                    "gracenote": gracenote,
                    "chord_id": chord_id,
                    "voice": voice,
                    "staff": staff,
                    "part_id": part_id,
                }
            )

        notes_data = NoteEventData.from_dicts(
            note_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            has_rests=has_rests,
        )

        return ScoreStore(
            notes=notes_data,
            measures=MeasureData.empty(),
            controls=ControlEventData.empty(),
            annotations=AnnotationEventData.empty(),
            metadata={
                "format": "tsv",
                "parser": "ms3",
                "source": str(source),
                "has_rests": has_rests,
            },
        )

    def _load_measures(self, df: pd.DataFrame, source: Path) -> ScoreStore:
        """Load measures TSV into MeasureData.

        Parses ms3/DCML measures.tsv format with columns:
        - mc, mn: Measure count/number
        - quarterbeats: Start position in quarter notes
        - quarterbeats_all_endings: Alternative qstamp including all endings
        - duration_qb: Duration in quarter beats
        - keysig: Key signature (fifths value or string)
        - timesig: Time signature string
        - act_dur: Actual duration as fraction string
        - mc_offset: Offset for split bars
        - volta: Ending number (1, 2, ...)
        - numbering_offset: MN offset
        - dont_count: Skip in MN counting
        - barline: Barline type
        - breaks: Section boundary marker
        - repeats: "start", "end", "firstMeasure"
        - next: Comma-separated list of possible next MCs

        Args:
            df: pandas DataFrame from ms3.load_tsv.
            source: Path to source file.

        Returns:
            ScoreStore with populated MeasureData.
        """
        import pandas as pd

        if df.empty:
            return ScoreStore.empty()

        measure_rows = []

        for idx, row in df.iterrows():
            # ===== Core Identity =====
            mc = int(row["mc"]) if pd.notna(row.get("mc")) else idx + 1
            mn = str(row.get("mn", mc)) if pd.notna(row.get("mn")) else str(mc)

            # Parse MN as integer (strip suffix if present)
            try:
                mn_int = int("".join(c for c in mn if c.isdigit() or c == "-"))
            except ValueError:
                mn_int = mc

            # ===== Temporal =====
            qb = self._parse_fraction(row.get("quarterbeats", 0))
            qb_float = float(qb) if qb else 0.0

            dur_qb = self._parse_fraction(row.get("duration_qb", 0))
            dur_qb_float = float(dur_qb) if dur_qb else 0.0

            # act_dur is often a fraction string like "1/2" for half a bar
            act_dur = row.get("act_dur")
            if pd.notna(act_dur):
                act_dur_frac = self._parse_fraction(act_dur)
                actual_length = float(act_dur_frac * 4) if act_dur_frac else None
            else:
                actual_length = dur_qb_float

            # mc_offset for split bars
            mc_offset = (
                str(row.get("mc_offset"))
                if pd.notna(row.get("mc_offset"))
                and row.get("mc_offset") not in (0, "0")
                else None
            )

            # quarterbeats_all_endings
            qb_all = (
                str(row.get("quarterbeats_all_endings"))
                if pd.notna(row.get("quarterbeats_all_endings"))
                else None
            )

            # ===== Signatures =====
            timesig = (
                str(row.get("timesig", "")) if pd.notna(row.get("timesig")) else None
            )

            # Parse timesig components
            timesig_num = None
            timesig_den = None
            nominal_length = None
            if timesig and "/" in timesig:
                try:
                    parts = timesig.split("/")
                    timesig_num = int(parts[0])
                    timesig_den = int(parts[1])
                    # nominal_length in quarters = (num / den) * 4
                    nominal_length = (timesig_num / timesig_den) * 4
                except (ValueError, IndexError):
                    pass

            # keysig: can be int (fifths) or string
            keysig = row.get("keysig")
            keysig_fifths = None
            if pd.notna(keysig):
                try:
                    keysig_fifths = int(keysig)
                    keysig = None  # Will use fifths value
                except (ValueError, TypeError):
                    keysig = str(keysig)

            # ===== Flow Control =====
            # repeats column: "start", "end", "firstMeasure"
            repeats_val = (
                str(row.get("repeats", "")) if pd.notna(row.get("repeats")) else None
            )

            start_repeat = repeats_val in ("start",) if repeats_val else False
            end_repeat = repeats_val in ("end",) if repeats_val else False

            # volta (ending number)
            volta = int(row["volta"]) if pd.notna(row.get("volta")) else None

            # breaks (section boundary)
            breaks_val = (
                str(row.get("breaks", "")) if pd.notna(row.get("breaks")) else None
            )

            # dont_count
            dont_count = (
                bool(row.get("dont_count")) if pd.notna(row.get("dont_count")) else None
            )

            # numbering_offset
            numbering_offset = (
                int(row["numbering_offset"])
                if pd.notna(row.get("numbering_offset"))
                else None
            )

            # barline
            barline = (
                str(row.get("barline", "")) if pd.notna(row.get("barline")) else None
            )

            # next: comma-separated list of possible next MCs
            next_val = row.get("next")
            if pd.notna(next_val):
                next_str = str(next_val).strip()
            else:
                next_str = None

            # ===== Build row =====
            measure_rows.append(
                {
                    # Identity
                    "id": f"measure_{mc}",
                    "name": f"M{mn}",
                    "temporal_type": "interval",
                    "event_type": "Measure",
                    # Core fields
                    "mc": mc,
                    "mn": mn,
                    "mn_int": mn_int,
                    # Temporal
                    "start": qb_float,
                    "duration": dur_qb_float,
                    "end": qb_float + dur_qb_float,
                    "duration_float": dur_qb_float,
                    "nominal_length": nominal_length,
                    "actual_length": actual_length,
                    "mc_offset": mc_offset,
                    "quarterbeats_all_endings": qb_all,
                    # Signatures
                    "timesig": timesig,
                    "timesig_num": timesig_num,
                    "timesig_den": timesig_den,
                    "keysig": keysig,
                    "keysig_fifths": keysig_fifths,
                    # Flow control
                    "start_repeat": start_repeat,
                    "end_repeat": end_repeat,
                    "next": next_str,
                    "volta": volta,
                    "repeats": repeats_val,
                    "breaks": breaks_val,
                    "dont_count": dont_count,
                    "numbering_offset": numbering_offset,
                    # Context
                    "barline": barline,
                }
            )

        measures_data = MeasureData.from_dicts(
            measure_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        return ScoreStore(
            notes=NoteEventData.empty(),
            measures=measures_data,
            controls=ControlEventData.empty(),
            annotations=AnnotationEventData.empty(),
            metadata={
                "format": "tsv",
                "parser": "ms3",
                "source": str(source),
                "n_measures": len(measure_rows),
                "flow_control": measures_data.get_flow_control_summary(),
            },
        )

    def _load_annotations(
        self, df: "pd.DataFrame", source: Path, subtype: str
    ) -> ScoreStore:
        """Load annotations from TSV (harmonies).

        Parses ms3/DCML harmonies.tsv format with columns:
        - mc, mn: Measure context
        - quarterbeats: Position in quarter notes
        - label: The annotation text (Roman numeral harmony label)
        - numeral, form, figbass, relativeroot, etc.: Parsed components

        Args:
            df: pandas DataFrame from ms3.load_tsv.
            source: Path to source file.
            subtype: The annotation subtype ("Harmony").

        Returns:
            ScoreStore with populated AnnotationEventData.
        """
        import pandas as pd

        if df.empty:
            return ScoreStore.empty()

        annotation_rows = []

        for idx, row in df.iterrows():
            # Temporal
            qb = self._parse_fraction(row.get("quarterbeats", 0))
            qb_float = float(qb) if qb else 0.0

            # Duration (if available)
            dur_qb = self._parse_fraction(row.get("duration_qb"))
            dur_qb_float = float(dur_qb) if dur_qb else None

            # Measure context
            mc = int(row["mc"]) if pd.notna(row.get("mc")) else None
            mn = str(row.get("mn", "")) if pd.notna(row.get("mn")) else None
            mc_onset = self._parse_fraction(row.get("mc_onset"))
            mn_onset = self._parse_fraction(row.get("mn_onset"))

            # Label - try various column names used in DCML
            label = None
            for label_col in ["label", "chord", "numeral", "globalkey_is_minor"]:
                if pd.notna(row.get(label_col)):
                    label = str(row[label_col])
                    break

            if label is None:
                # Construct label from components if available
                parts = []
                for col in ["numeral", "form", "figbass", "relativeroot"]:
                    if pd.notna(row.get(col)) and row.get(col):
                        parts.append(str(row[col]))
                label = "".join(parts) if parts else f"{subtype}_{idx}"

            # Staff context
            staff = int(row["staff"]) if pd.notna(row.get("staff")) else None

            annotation_rows.append(
                {
                    "id": f"ann_{subtype.lower()}_{qb_float}_{idx}",
                    "name": label,
                    "temporal_type": "interval" if dur_qb_float else "instant",
                    "event_type": "Annotation",
                    "subtype": subtype,
                    "text": label,
                    # Temporal
                    "quarterbeats": (
                        coordinate_to_struct(qb)
                        if qb is not None
                        else coordinate_to_struct(0)
                    ),
                    "quarterbeats_float": qb_float,
                    "duration_qb": (
                        coordinate_to_struct(dur_qb) if dur_qb is not None else None
                    ),
                    "duration_float": dur_qb_float,
                    # Measure context
                    "mc": mc,
                    "mn": mn,
                    "mc_onset": (
                        fraction_to_struct(mc_onset) if mc_onset is not None else None
                    ),
                    "mn_onset": (
                        fraction_to_struct(mn_onset) if mn_onset is not None else None
                    ),
                    # Context
                    "staff": staff,
                }
            )

        annotations_data = AnnotationEventData.from_dicts(
            annotation_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        return ScoreStore(
            notes=NoteEventData.empty(),
            measures=MeasureData.empty(),
            controls=ControlEventData.empty(),
            annotations=annotations_data,
            metadata={
                "format": "tsv",
                "parser": "ms3",
                "source": str(source),
                "annotation_type": subtype,
                "n_annotations": len(annotation_rows),
            },
        )

    def _load_controls(
        self, df: "pd.DataFrame", source: Path, subtype: str
    ) -> ScoreStore:
        """Load control events from TSV (chords).

        Parses ms3/DCML chords.tsv format with columns:
        - mc, mn: Measure context
        - quarterbeats: Position in quarter notes
        - chord: The chord symbol text
        - pedal, numeral, form, figbass, etc.: Parsed components

        Args:
            df: pandas DataFrame from ms3.load_tsv.
            source: Path to source file.
            subtype: The control subtype ("Chord").

        Returns:
            ScoreStore with populated ControlEventData.
        """
        import pandas as pd

        if df.empty:
            return ScoreStore.empty()

        control_rows = []

        for idx, row in df.iterrows():
            # Temporal
            qb = self._parse_fraction(row.get("quarterbeats", 0))
            qb_float = float(qb) if qb else 0.0

            # Duration (if available)
            dur_qb = self._parse_fraction(row.get("duration_qb"))
            dur_qb_float = float(dur_qb) if dur_qb else None

            # Measure context
            mc = int(row["mc"]) if pd.notna(row.get("mc")) else None
            mn = str(row.get("mn", "")) if pd.notna(row.get("mn")) else None
            mc_onset = self._parse_fraction(row.get("mc_onset"))
            mn_onset = self._parse_fraction(row.get("mn_onset"))

            # Label - try various column names used in DCML
            label = None
            for label_col in ["chord", "label", "numeral"]:
                if pd.notna(row.get(label_col)):
                    label = str(row[label_col])
                    break

            if label is None:
                # Construct label from components if available
                parts = []
                for col in ["numeral", "form", "figbass", "relativeroot"]:
                    if pd.notna(row.get(col)) and row.get(col):
                        parts.append(str(row[col]))
                label = "".join(parts) if parts else f"{subtype}_{idx}"

            # Staff/voice context
            staff = int(row["staff"]) if pd.notna(row.get("staff")) else None
            voice = int(row["voice"]) if pd.notna(row.get("voice")) else None

            control_rows.append(
                {
                    "id": f"ctrl_{subtype.lower()}_{qb_float}_{idx}",
                    "name": label,
                    "temporal_type": "interval" if dur_qb_float else "instant",
                    "event_type": "Control",
                    "subtype": subtype,
                    "text": label,
                    "value": None,  # Chord symbols don't have numeric values
                    # Temporal
                    "quarterbeats": (
                        coordinate_to_struct(qb)
                        if qb is not None
                        else coordinate_to_struct(0)
                    ),
                    "quarterbeats_float": qb_float,
                    "duration_qb": (
                        coordinate_to_struct(dur_qb) if dur_qb is not None else None
                    ),
                    "duration_float": dur_qb_float,
                    # Measure context
                    "mc": mc,
                    "mn": mn,
                    "mc_onset": (
                        fraction_to_struct(mc_onset) if mc_onset is not None else None
                    ),
                    "mn_onset": (
                        fraction_to_struct(mn_onset) if mn_onset is not None else None
                    ),
                    # Context
                    "staff": staff,
                    "voice": voice,
                }
            )

        controls_data = ControlEventData.from_dicts(
            control_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
        )

        return ScoreStore(
            notes=NoteEventData.empty(),
            measures=MeasureData.empty(),
            controls=controls_data,
            annotations=AnnotationEventData.empty(),
            metadata={
                "format": "tsv",
                "parser": "ms3",
                "source": str(source),
                "control_type": subtype,
                "n_controls": len(control_rows),
            },
        )
