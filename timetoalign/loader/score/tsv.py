"""TSVLoader: Load scores from TSV using ms3."""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Any

from timetoalign.core import NumberType, TimeUnit
from timetoalign.loader.schema import fraction_to_struct

from .bundle import ScoreBundle
from .stores import (
    AnnotationEventStore,
    ControlEventStore,
    MeasureEventStore,
    NoteEventStore,
)

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)


class TSVLoader:
    """Load symbolic scores from DCML-style TSV files.

    Wraps ms3.load_tsv to load standard tabular data.
    Returns a ScoreBundle with category-specific stores.

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

    def load(self, source: Path) -> ScoreBundle:
        """Load TSV file(s) and return ScoreBundle.

        Args:
            source: Path to TSV file or directory.

        Returns:
            ScoreBundle with populated stores.
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
        else:
            # Default to notes if has pitch columns
            if "midi" in df.columns or "tpc" in df.columns:
                return self._load_notes(df, source)
            return ScoreBundle.empty()

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

    def _load_notes(self, df: pd.DataFrame, source: Path) -> ScoreBundle:
        """Load notes TSV into NoteEventStore."""
        import pandas as pd

        if df.empty:
            return ScoreBundle.empty()

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
                    # Temporal
                    "quarterbeats": (
                        fraction_to_struct(qb)
                        if qb is not None
                        else {"num": 0, "den": 1}
                    ),
                    "quarterbeats_float": qb_float,
                    "duration_qb": (
                        fraction_to_struct(dur_qb) if dur_qb is not None else None
                    ),
                    "duration_qb_float": dur_qb_float,
                    "mc": mc,
                    "mn": mn,
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

        notes_store = NoteEventStore.from_dicts(
            note_rows,
            unit=TimeUnit.quarters,
            number_type=NumberType.fraction,
            has_rests=has_rests,
        )

        return ScoreBundle(
            notes=notes_store,
            measures=MeasureEventStore.empty(),
            controls=ControlEventStore.empty(),
            annotations=AnnotationEventStore.empty(),
            metadata={
                "format": "tsv",
                "parser": "ms3",
                "source": str(source),
                "has_rests": has_rests,
            },
        )

    def _load_measures(self, df: pd.DataFrame, source: Path) -> ScoreBundle:
        """Load measures TSV into MeasureEventStore."""
        # Placeholder - can be implemented similarly
        return ScoreBundle.empty()
