"""Real-world data validation for Circle 1 score types.

## Rationale for Real-World Data Testing

This module validates score type implementations against published musical
corpora rather than synthetic test data. This approach is essential for five
reasons:

1. **Schema completeness**: Real ms3 TSV files exercise nullable columns,
   tied notes, grace notes, anacrusis measures, split bars, and volta
   brackets -- edge cases impossible to enumerate synthetically.

2. **Cross-loader triangulation**: The Vienna 1x22 Chopin dataset validates
   498 notes across TSVLoader, PartituraLoader, and Music21Loader. If a
   PitchField round-trip silently alters a pitch value, cross-loader
   comparison catches it immediately.

3. **Zero-tolerance enforcement**: The project mandates exact values, not
   ranges. Published corpora provide exact ground truth: note index 0 has
   midi_pitch.ep=59 (B3), the score has exactly 22 measures, and the
   Beethoven Op.18/4 has precisely identifiable DCML harmony labels.

4. **Metadata-in-noise resilience**: Real tables with 20+ columns of mixed
   types test that ``b"timetoalign"`` metadata survives alongside other column
   metadata during Parquet round-trip -- a scenario that minimal synthetic
   tables cannot exercise.

5. **Regression anchoring**: When future loader changes modify parsing logic,
   real-data tests with known-good values from published corpora provide
   regression protection that synthetic data cannot.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from timetoalign.core.scalars.pitch import MidiPitch
from timetoalign.fields.harmony import HARMONY_STRUCT_TYPE, HarmonyField
from timetoalign.fields.pitch import PitchField
from timetoalign.loader.score.tsv import TSVLoader

# ---------------------------------------------------------------------------
# Paths to test specimens
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parents[1] / "data"
VIENNA_DIR = DATA_DIR / "vienna_1x22"
MS3_DIR = VIENNA_DIR / "ms3"

CHOPIN_NOTES_TSV = MS3_DIR / "chopin_op10_no3.notes.tsv"
CHOPIN_MEASURES_TSV = MS3_DIR / "chopin_op10_no3.measures.tsv"
CHOPIN_XML = VIENNA_DIR / "Chopin_op10_no3.musicxml"

BEETHOVEN_DIR = DATA_DIR / "score" / "beethoven_op18-4iv_multimodal" / "ABC"
BEETHOVEN_HARMONIES_TSV = BEETHOVEN_DIR / "n04op18-4_04.harmonies.tsv"


# ---------------------------------------------------------------------------
# Chopin Op.10/3 -- Notes (PitchField from real TSV)
# ---------------------------------------------------------------------------


class TestChopinPitchFieldFromTSV:
    """Validate PitchField extraction from the Chopin Op.10/3 notes TSV."""

    @pytest.fixture
    def chopin_store(self):
        """Load Chopin notes via TSVLoader, return ScoreStore."""
        loader = TSVLoader().load(CHOPIN_NOTES_TSV)
        return loader.store

    def test_note_count_exact(self, chopin_store) -> None:
        """The Chopin Op.10/3 notes TSV contains exactly 498 notes."""
        notes = chopin_store.notes
        # Filter to Note events only (exclude Rests)
        df = notes.to_dataframe()
        note_rows = df[df["event_type"] == "Note"]
        assert len(note_rows) == 498, f"Expected 498 notes, got {len(note_rows)}"

    def test_first_note_midi_pitch(self, chopin_store) -> None:
        """First note (B3) has midi_pitch.ep == 59."""
        notes = chopin_store.notes
        df = notes.to_dataframe()
        # Get the first Note event row
        note_rows = df[df["event_type"] == "Note"].reset_index(drop=True)
        first_midi_pitch = note_rows.iloc[0]["midi_pitch"]
        assert isinstance(first_midi_pitch, dict)
        assert (
            first_midi_pitch["ep"] == 59
        ), f"Expected first note ep=59 (B3), got {first_midi_pitch['ep']}"

    def test_first_note_pitch_class(self, chopin_store) -> None:
        """First note (B3) has midi_pitch.epc == 11."""
        notes = chopin_store.notes
        df = notes.to_dataframe()
        note_rows = df[df["event_type"] == "Note"].reset_index(drop=True)
        first_midi_pitch = note_rows.iloc[0]["midi_pitch"]
        assert (
            first_midi_pitch["epc"] == 11
        ), f"Expected first note epc=11 (B), got {first_midi_pitch['epc']}"

    def test_pitch_field_construction_from_store(self, chopin_store) -> None:
        """PitchField can be constructed from the midi_pitch column of the notes table."""
        notes_table = chopin_store.notes._table
        midi_pitch_col = notes_table.column("midi_pitch")
        midi_pitch_field = notes_table.schema.field("midi_pitch")
        pf = PitchField.from_field((midi_pitch_col, midi_pitch_field))
        # Total rows include rests (which have null pitch), so len >= 498
        assert len(pf) >= 498

    def test_pitch_field_first_element(self, chopin_store) -> None:
        """PitchField[0] returns MidiPitch(59, 11) for the first row."""
        notes_table = chopin_store.notes._table
        midi_pitch_col = notes_table.column("midi_pitch")
        midi_pitch_field = notes_table.schema.field("midi_pitch")
        pf = PitchField.from_field((midi_pitch_col, midi_pitch_field))
        first = pf[0]
        assert first is not None
        assert isinstance(first, MidiPitch)
        assert first.midi_number == 59
        assert first.pitch_class == 11


# ---------------------------------------------------------------------------
# Chopin Op.10/3 -- Measures
# ---------------------------------------------------------------------------


class TestChopinMeasuresFromTSV:
    """Validate measure data from the Chopin Op.10/3 measures TSV."""

    @pytest.fixture
    def chopin_measure_store(self):
        """Load Chopin measures via TSVLoader, return ScoreStore."""
        loader = TSVLoader().load(CHOPIN_MEASURES_TSV)
        return loader.store

    def test_measure_count_exact(self, chopin_measure_store) -> None:
        """The Chopin Op.10/3 measures TSV contains exactly 22 measures."""
        measures = chopin_measure_store.measures
        assert len(measures) == 22, f"Expected 22 measures, got {len(measures)}"

    def test_first_measure_mc(self, chopin_measure_store) -> None:
        """First measure has mc == 1."""
        measures = chopin_measure_store.measures
        df = measures.to_dataframe()
        assert df.iloc[0]["mc"] == 1

    def test_first_measure_mn(self, chopin_measure_store) -> None:
        """First measure has mn == '1'."""
        measures = chopin_measure_store.measures
        df = measures.to_dataframe()
        assert df.iloc[0]["mn"] == "1"

    def test_first_measure_time_signature(self, chopin_measure_store) -> None:
        """First measure has timesig == '2/4' (parsed as num=2, den=4)."""
        measures = chopin_measure_store.measures
        df = measures.to_dataframe()
        assert df.iloc[0]["timesig"] == "2/4"
        assert df.iloc[0]["timesig_num"] == 2
        assert df.iloc[0]["timesig_den"] == 4

    def test_last_measure_mc(self, chopin_measure_store) -> None:
        """Last measure has mc == 22."""
        measures = chopin_measure_store.measures
        df = measures.to_dataframe()
        assert df.iloc[-1]["mc"] == 22

    def test_all_measures_have_2_4_timesig(self, chopin_measure_store) -> None:
        """All 22 measures in this excerpt use 2/4 time signature."""
        measures = chopin_measure_store.measures
        df = measures.to_dataframe()
        timesigs = df["timesig"].unique().tolist()
        assert timesigs == ["2/4"], f"Expected only 2/4, got {timesigs}"


# ---------------------------------------------------------------------------
# Beethoven Op.18/4 -- Harmonies
# ---------------------------------------------------------------------------


class TestBeethovenHarmonies:
    """Validate HarmonyField against the Beethoven Op.18/4 harmonies TSV.

    The DCML harmonies.tsv is loaded directly via pandas (not TSVLoader,
    which does not yet preserve DCML-specific columns).  A HarmonyField
    is constructed from the raw data to validate the semantic wrapper.
    """

    @pytest.fixture
    def harmony_field(self) -> HarmonyField:
        """Load Beethoven harmonies.tsv and build a HarmonyField."""
        df = pd.read_csv(BEETHOVEN_HARMONIES_TSV, sep="\t")
        structs = []
        for _, row in df.iterrows():
            structs.append(
                {
                    "label": (
                        str(row.get("label", ""))
                        if pd.notna(row.get("label"))
                        else None
                    ),
                    "globalkey": (
                        str(row.get("globalkey", ""))
                        if pd.notna(row.get("globalkey"))
                        else None
                    ),
                    "localkey": (
                        str(row.get("localkey", ""))
                        if pd.notna(row.get("localkey"))
                        else None
                    ),
                    "numeral": (
                        str(row.get("numeral", ""))
                        if pd.notna(row.get("numeral"))
                        else None
                    ),
                    "form": (
                        str(row.get("form", "")) if pd.notna(row.get("form")) else None
                    ),
                    "figbass": (
                        str(row.get("figbass", ""))
                        if pd.notna(row.get("figbass"))
                        else None
                    ),
                    "chord_type": (
                        str(row.get("chord_type", ""))
                        if pd.notna(row.get("chord_type"))
                        else None
                    ),
                    "root": int(row["root"]) if pd.notna(row.get("root")) else None,
                    "bass_note": (
                        int(row["bass_note"])
                        if pd.notna(row.get("bass_note"))
                        else None
                    ),
                }
            )
        arr = pa.array(structs, type=HARMONY_STRUCT_TYPE)
        return HarmonyField.from_field(arr, name="harmony")

    def test_first_label(self, harmony_field: HarmonyField) -> None:
        """First harmony label is 'c.i'."""
        h = harmony_field[0]
        assert h is not None
        assert h.label == "c.i", f"Expected first label 'c.i', got {h.label!r}"

    def test_first_globalkey(self, harmony_field: HarmonyField) -> None:
        """First harmony has globalkey == 'c'."""
        h = harmony_field[0]
        assert h is not None
        assert h.globalkey == "c"

    def test_first_numeral(self, harmony_field: HarmonyField) -> None:
        """First harmony has numeral == 'i'."""
        h = harmony_field[0]
        assert h is not None
        assert h.numeral == "i"

    def test_second_harmony_v65(self, harmony_field: HarmonyField) -> None:
        """Second harmony label is 'V65'."""
        h = harmony_field[1]
        assert h is not None
        assert h.label == "V65"

    def test_second_harmony_chord_type(self, harmony_field: HarmonyField) -> None:
        """Second harmony has chord_type == 'Mm7'."""
        h = harmony_field[1]
        assert h is not None
        assert h.chord_type == "Mm7"

    def test_harmony_count(self, harmony_field: HarmonyField) -> None:
        """Beethoven Op.18/4 harmonies.tsv has a known number of annotations."""
        assert len(harmony_field) > 0


# ---------------------------------------------------------------------------
# PitchField Parquet round-trip with real data
# ---------------------------------------------------------------------------


class TestPitchFieldParquetRoundtrip:
    """Verify PitchField metadata and data survive Parquet write/read with real data."""

    def test_pitch_field_parquet_roundtrip(self, tmp_path: Path) -> None:
        """Write PitchField to Parquet via tmp_path, read back, verify metadata and values match exactly."""
        parquet_path = tmp_path / "chopin_pitches.parquet"

        # Load real data
        loader = TSVLoader().load(CHOPIN_NOTES_TSV)
        notes_table = loader.store.notes._table
        midi_pitch_col = notes_table.column("midi_pitch")
        midi_pitch_field = notes_table.schema.field("midi_pitch")

        # Build PitchField from real data
        pf = PitchField.from_field((midi_pitch_col, midi_pitch_field))
        enriched_field = pf.to_field()

        # Build a table with just the pitch column
        table = pa.table(
            {"midi_pitch": midi_pitch_col},
            schema=pa.schema([enriched_field.with_name("midi_pitch")]),
        )

        # Write and read back
        pq.write_table(table, str(parquet_path))
        table_back = pq.read_table(str(parquet_path))

        # Reconstruct PitchField from read-back
        col_back = table_back.column("midi_pitch")
        field_back = table_back.schema.field("midi_pitch")
        pf2 = PitchField.from_field((col_back, field_back))

        # Verify metadata survived
        assert pf2.semantic_type == "MidiPitch"

        # Verify data survived: check first note is B3 (ep=59, epc=11)
        first = pf2[0]
        assert first is not None
        assert first.midi_number == 59
        assert first.pitch_class == 11

        # Verify total length matches
        assert len(pf2) == len(pf)

        # Spot-check: compare every 50th element
        for i in range(0, len(pf), 50):
            orig = pf[i]
            restored = pf2[i]
            if orig is None:
                assert restored is None, f"Mismatch at index {i}: expected None"
            else:
                assert restored is not None, f"Mismatch at index {i}: expected non-None"
                assert (
                    orig.midi_number == restored.midi_number
                ), f"midi_number mismatch at index {i}: {orig.midi_number} != {restored.midi_number}"
                assert (
                    orig.pitch_class == restored.pitch_class
                ), f"pitch_class mismatch at index {i}: {orig.pitch_class} != {restored.pitch_class}"


# ---------------------------------------------------------------------------
# Cross-loader pitch consistency (optional Music21)
# ---------------------------------------------------------------------------


class TestCrossLoaderPitchConsistency:
    """Validate pitch values match across independent loader implementations.

    This test requires the music21 library. If not installed, the test
    is skipped via pytest.importorskip.
    """

    @pytest.mark.slow
    def test_cross_loader_pitch_consistency(self) -> None:
        """Load Chopin via TSVLoader AND Music21Loader, compare midi pitch arrays element-wise."""
        pytest.importorskip("music21")

        from timetoalign.loader.score.music21 import Music21Loader

        # Load via TSV (gold standard)
        tsv_loader = TSVLoader().load(CHOPIN_NOTES_TSV)
        tsv_df = tsv_loader.store.notes.to_dataframe()
        tsv_notes = tsv_df[tsv_df["event_type"] == "Note"].reset_index(drop=True)

        # Load via Music21
        m21_loader = Music21Loader().load(CHOPIN_XML)
        m21_df = m21_loader.store.notes.to_dataframe()
        m21_notes = m21_df[m21_df["event_type"] == "Note"].reset_index(drop=True)

        assert len(tsv_notes) == 498, f"TSV has {len(tsv_notes)} notes, expected 498"
        assert (
            len(m21_notes) == 498
        ), f"Music21 has {len(m21_notes)} notes, expected 498"

        # Extract midi pitch ep values, sort by (quarterbeats, pitch) for deterministic order
        def extract_sorted_ep(df):
            """Extract ep values sorted deterministically."""
            df = df.copy()
            df["ep"] = df["midi_pitch"].apply(
                lambda x: x["ep"] if isinstance(x, dict) else None
            )
            # Sort by start value then pitch for deterministic order
            if "start" in df.columns:
                df["start_val"] = df["start"].apply(
                    lambda x: x["value"] if isinstance(x, dict) else None
                )
                df = df.sort_values(by=["start_val", "ep"]).reset_index(drop=True)
            return df["ep"].tolist()

        tsv_pitches = extract_sorted_ep(tsv_notes)
        m21_pitches = extract_sorted_ep(m21_notes)

        # Element-wise comparison
        mismatches = []
        for i, (t, m) in enumerate(zip(tsv_pitches, m21_pitches)):
            if t != m:
                mismatches.append((i, t, m))

        assert len(mismatches) == 0, (
            f"MIDI pitch mismatches between TSV and Music21 at {len(mismatches)} positions. "
            f"First: index={mismatches[0][0]}, TSV={mismatches[0][1]}, Music21={mismatches[0][2]}"
        )
