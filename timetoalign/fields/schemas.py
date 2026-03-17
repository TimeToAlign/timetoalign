"""Canonical schema definitions for Time To Align! semantic types.

**THIS IS THE SINGLE SOURCE OF TRUTH** for all pitch, harmony, and event
struct schemas.  Every Field class, Scalar class, and loader store MUST
reference this module rather than defining its own ``pa.struct()`` constants.

Each schema is a frozen dataclass that documents its sub-fields with
musicological rationale.  The ``schema`` class variable holds the frozen
PyArrow struct type.

Naming Convention
-----------------
The naming follows the ms3/DCML convention for pitch arrays:

- **GP** (Generic Pitch): pitch class as integer (0-11), no spelling.
  Stored as ``{pitch_class: int64}``.
- **EP** (Enharmonic Pitch): integer MIDI representation that collapses
  enharmonic distinctions (C♯4 == D♭4 == 61).  Stored as ``{ep: int64, epc: int64}``.
  Called "enharmonic" because it *equates* enharmonic equivalents.
- **SP** (Specific Pitch): spelled pitch with full enharmonic identity
  (C♯4 ≠ D♭4).  Stored as ``{gpc_int, gpc_str, acc, spc_int, spc_str, sp, cents}``.
  Called "specific" because it preserves the *specific* spelling.

This yields the following mapping (from most abstract to most specific):

+----------------------+---------------------------+-------------------+
| TTA Concept          | ms3/DCML Prefix           | Field Class       |
+======================+===========================+===================+
| GenericPitch         | GP (Generic Pitch)        | GenericPitchField |
+----------------------+---------------------------+-------------------+
| EnharmonicPitch      | EP (Enharmonic Pitch)     | EnharmonicPitchField |
| (= MidiPitch)        | (integer MIDI rep.)       | (alias: MidiPitchField) |
+----------------------+---------------------------+-------------------+
| SpecificPitch        | SP (Specific/Spelled      | SpecificPitchField |
| (= SpelledPitch)     |  Pitch)                   | (alias: SpelledPitchField) |
+----------------------+---------------------------+-------------------+
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar

import pyarrow as pa

# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED PITCH SCHEMA (PitchSpaceSchema)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PitchSpaceSchema:
    """Unified backing struct for all pitch and interval representations.

    All pitch types (sp, spc, ep, epc, gp, gpc) and interval types
    (si, sic, ei, eic, gi, gic) share this single struct. The
    ``space`` and ``type`` metadata on the ``pa.Field`` determine
    interpretation.

    Storage struct::

        {value: int64, octave: int64}

    - ``value``: the pitch/interval value in the relevant space
      (fifths position, MIDI number, semitones 0-11, diatonic step, etc.)
    - ``octave``: octave number for specific types (sp, ep, gp, si, ei, gi);
      null for class types (spc, epc, gpc, sic, eic, gic)

    Metadata (stored in ``pa.Field.metadata``)::

        {"space": "fifths"|"semitones"|"steps",
         "type": "spc"|"sp"|"epc"|"ep"|"gpc"|"gp"|"sic"|"si"|"eic"|"ei"|"gic"|"gi"}
    """

    value: str = "value"
    """The pitch/interval value in the relevant space."""

    octave: str = "octave"
    """Octave number (specific types) or null (class types)."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("value", pa.int64(), nullable=True),
            pa.field("octave", pa.int64(), nullable=True),
        ]
    )
    """PyArrow struct type for unified pitch/interval storage."""


# ═══════════════════════════════════════════════════════════════════════════
# DEPRECATED PITCH SCHEMAS (kept for backward compat during migration)
# ═══════════════════════════════════════════════════════════════════════════

# region Generic Pitch (GP)


@dataclass(frozen=True)
class GenericPitchSchema:
    """Schema for Generic Pitch (GP): pitch class only.

    .. deprecated::
        Use ``PitchSpaceSchema`` with ``type="epc"`` instead.
        This schema stores chromatic pitch class 0-11, which is EPC
        (semitones space), not true GPC (diatonic steps 0-6).

    Storage struct::

        {pitch_class: int64}
    """

    pitch_class: str = "pitch_class"
    """Pitch class (0-11, C=0).  The only sub-field.

    Musicological rationale: Pitch class is the fundamental equivalence
    class under octave equivalence in 12-TET.  All other pitch
    representations can be reduced to this.
    """

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("pitch_class", pa.int64(), nullable=True),
        ]
    )
    """PyArrow struct type for Generic Pitch (GP)."""


# endregion Generic Pitch

# region Enharmonic Pitch (EP = MIDI pitch)


@dataclass(frozen=True)
class EnharmonicPitchSchema:
    """Schema for Enharmonic Pitch (EP): MIDI-style integer representation.

    .. deprecated::
        Use ``PitchSpaceSchema`` with ``type="ep"`` instead.

    Storage struct::

        {ep: int64, epc: int64}
    """

    ep: str = "ep"
    """MIDI note number (0-127).  C4 = 60.

    Encodes pitch class + octave as a single integer.
    Named ``ep`` (Enharmonic Pitch) following the ms3/DCML convention.
    """

    epc: str = "epc"
    """Enharmonic Pitch Class (0-11, C=0).

    Redundant with ``ep % 12`` but stored explicitly for efficient
    columnar filtering without compute.
    """

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("ep", pa.int64(), nullable=True),
            pa.field("epc", pa.int64(), nullable=True),
        ]
    )
    """PyArrow struct type for Enharmonic Pitch (EP / MIDI pitch)."""


# endregion Enharmonic Pitch

# region Specific Pitch (SP = Spelled Pitch)


@dataclass(frozen=True)
class SpecificPitchSchema:
    """Schema for Specific Pitch (SP): spelled pitch with full identity.

    .. deprecated::
        Use ``PitchSpaceSchema`` with ``type="sp"`` instead.

    Storage struct::

        {gpc_int: int64, gpc_str: string, acc: int64,
         spc_int: int64, spc_str: string, sp: string, cents: float64}
    """

    gpc_int: str = "gpc_int"
    """Generic pitch class as integer (steps above C, 0-6).

    0=C, 1=D, 2=E, 3=F, 4=G, 5=A, 6=B.
    Named ``gpc_int`` (Generic Pitch Class, integer) per ms3 convention.
    """

    gpc_str: str = "gpc_str"
    """Generic pitch class as letter string ("C", "D", ..., "B").

    Redundant with ``gpc_int`` but avoids lookup for display.
    """

    acc: str = "acc"
    """Accidental as integer semitones (-2=𝄫, -1=♭, 0=♮, +1=♯, +2=𝄪).

    Named ``acc`` (accidental) per ms3 convention.  Maps to our
    semantic name ``alter``.
    """

    spc_int: str = "spc_int"
    """Spelled pitch class as position on the line of fifths.

    ..., -2=B♭, -1=F, 0=C, 1=G, 2=D, 3=A, 4=E, 5=B, 6=F♯, ...
    Essential for correct interval computation in tonal music.
    Named ``spc_int`` (Spelled Pitch Class, integer) per ms3 convention.
    Maps to our semantic name ``fifths``.
    """

    spc_str: str = "spc_str"
    """Spelled pitch class as string (e.g., "C", "F♯", "B♭").

    Redundant with ``spc_int`` but avoids reverse lookup for display.
    """

    sp: str = "sp"
    """Full spelled pitch string including octave (e.g., "C♯4", "D♭3").

    Encodes step + accidental + octave in human-readable form.
    Octave can be extracted as the trailing integer.
    """

    cents: str = "cents"
    """Cents offset from 12-TET equal temperament (default 0.0).

    Non-zero for microtonal data, historically informed tuning,
    or performance recordings with precise intonation.
    """

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("gpc_int", pa.int64(), nullable=True, metadata={"unit": "steps"}),
            pa.field("gpc_str", pa.string(), nullable=True),
            pa.field("acc", pa.int64(), nullable=True, metadata={"unit": "alter"}),
            pa.field("spc_int", pa.int64(), nullable=True, metadata={"unit": "fifths"}),
            pa.field("spc_str", pa.string(), nullable=True),
            pa.field("sp", pa.string(), nullable=True),
            pa.field("cents", pa.float64(), nullable=False, metadata={"unit": "cents"}),
        ]
    )
    """PyArrow struct type for Specific Pitch (SP / Spelled Pitch)."""


# endregion Specific Pitch

# region Spelled Pitch Class (SPC — octave-free spelled pitch)


@dataclass(frozen=True)
class SpelledPitchClassSchema:
    """Schema for Spelled Pitch Class (SPC): spelled pitch without octave.

    .. deprecated::
        Use ``PitchSpaceSchema`` with ``type="spc"`` instead.

    Storage struct::

        {gpc_str: string, acc: int64, spc_int: int64}
    """

    gpc_str: str = "gpc_str"
    """Generic pitch class as letter string."""

    acc: str = "acc"
    """Accidental as integer semitones."""

    spc_int: str = "spc_int"
    """Spelled pitch class on the line of fifths."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("gpc_str", pa.string(), nullable=True),
            pa.field("acc", pa.int64(), nullable=True, metadata={"unit": "alter"}),
            pa.field("spc_int", pa.int64(), nullable=True, metadata={"unit": "fifths"}),
        ]
    )
    """PyArrow struct type for Spelled Pitch Class (SPC)."""


# endregion Spelled Pitch Class


# ═══════════════════════════════════════════════════════════════════════════
# INVERSION ENUM
# ═══════════════════════════════════════════════════════════════════════════


class Inversion(IntEnum):
    """Chord inversion as an enum.

    Values correspond to the standard inversion numbers.
    The DCML ``figbass`` string maps to these values.
    """

    ROOT = 0
    """Root position."""

    FIRST = 1
    """First inversion (6, 65)."""

    SECOND = 2
    """Second inversion (64, 43)."""

    THIRD = 3
    """Third inversion (2, 42) -- seventh chords only."""


# DCML figbass -> Inversion enum mapping
FIGBASS_TO_INVERSION: dict[str, Inversion] = {
    "": Inversion.ROOT,
    "7": Inversion.ROOT,
    "6": Inversion.FIRST,
    "64": Inversion.SECOND,
    "2": Inversion.THIRD,
    "65": Inversion.FIRST,
    "43": Inversion.SECOND,
    "42": Inversion.THIRD,
}


def figbass_to_inversion(figbass: str) -> Inversion | None:
    """Convert a DCML ``figbass`` string to an ``Inversion`` enum member.

    Args:
        figbass: The DCML figured bass string (e.g., ``"65"``, ``""``).

    Returns:
        The corresponding ``Inversion`` enum member, or ``None`` if
        the string is not a recognised figured bass.
    """
    if not figbass:
        return Inversion.ROOT
    return FIGBASS_TO_INVERSION.get(figbass)


# ═══════════════════════════════════════════════════════════════════════════
# HARMONY SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

# region Base Harmony (label + standard)


@dataclass(frozen=True)
class HarmonyBaseSchema:
    """Minimal harmony schema: label and codec standard.

    Every harmony annotation, regardless of tradition or codec, has
    at least a label string and a standard identifier.

    Storage struct::

        {label: string, standard: string}
    """

    label: str = "label"
    """The full harmony label string (e.g., ``"V65/IV"``, ``"Cmaj7"``)."""

    standard: str = "standard"
    """Codec identifier (e.g., ``"dcml"``, ``"chord_symbol"``, ``"rn"``)."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
        ]
    )
    """PyArrow struct type for base harmony (label + standard)."""


# endregion Base Harmony

# region Western Tertian Harmony


@dataclass(frozen=True)
class WesternTertianSchema:
    """Schema for Western tertian harmony: root, bass, chord type, inversion.

    Extends the base harmony schema with pitch-based and tertian-specific
    fields.  This is the minimal schema for any Western tonal chord
    analysis.

    Storage struct::

        {label, standard, root: int64, bass: int64,
         chord_type: string, inversion: int64}

    Musicological rationale:
    - ``root`` and ``bass`` as pitch classes (0-11) are sufficient for
      any root-bass analysis.  Full pitch objects can be derived when
      octave context is available.
    - ``chord_type`` uses the ms3/DCML vocabulary (``"M"``, ``"m"``,
      ``"o"``, ``"+"``, ``"Mm7"``, etc.).
    - ``inversion`` as integer (0=root, 1=first, ...) is our internal
      model.  The DCML ``figbass`` encoding is converted on import and
      reconstructed on export.
    """

    label: str = "label"
    standard: str = "standard"
    root: str = "root"
    """Root pitch class (0-11, C=0)."""
    bass: str = "bass"
    """Bass note pitch class (0-11, C=0).  May differ from root in inversions."""
    chord_type: str = "chord_type"
    """Chord type (``"M"``, ``"m"``, ``"o"``, ``"+"``, ``"Mm7"``, etc.)."""
    inversion: str = "inversion"
    """Inversion number (0=root, 1=first, 2=second, 3=third)."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass", pa.int64(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("inversion", pa.int64(), nullable=True),
        ]
    )
    """PyArrow struct type for Western tertian harmony."""


# endregion Western Tertian Harmony

# region Roman Numeral Harmony


@dataclass(frozen=True)
class RomanNumeralSchema:
    """Schema for Roman numeral harmony: adds numeral, localkey, globalkey.

    Extends the Western tertian schema with key-context information.
    The ``key_context`` field is a shorthand reference combining
    globalkey and localkey (e.g., ``"C:IV"``).

    Storage struct::

        {label, standard, root, bass, chord_type, inversion,
         numeral: string, localkey: string, globalkey: string,
         key_context: string}
    """

    label: str = "label"
    standard: str = "standard"
    root: str = "root"
    bass: str = "bass"
    chord_type: str = "chord_type"
    inversion: str = "inversion"
    numeral: str = "numeral"
    """Roman numeral (``"I"``, ``"ii"``, ``"V"``, etc.)."""
    localkey: str = "localkey"
    """Local key at this position (e.g., ``"IV"``).  A reference
    collection expressed as shorthand."""
    globalkey: str = "globalkey"
    """Global key of the piece (e.g., ``"C"``)."""
    key_context: str = "key_context"
    """Shorthand combining globalkey:localkey (e.g., ``"C:IV"``).
    Kept in addition to separate globalkey/localkey for convenience."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("standard", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass", pa.int64(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("inversion", pa.int64(), nullable=True),
            pa.field("numeral", pa.string(), nullable=True),
            pa.field("localkey", pa.string(), nullable=True),
            pa.field("globalkey", pa.string(), nullable=True),
            pa.field("key_context", pa.string(), nullable=True),
        ]
    )
    """PyArrow struct type for Roman numeral harmony."""


# endregion Roman Numeral Harmony

# region DCML Harmony (DCML-specific storage)


@dataclass(frozen=True)
class DcmlStorageSchema:
    """Storage schema for DCML harmony labels (the raw DCML TSV columns).

    This is the **input/storage** schema -- the DCML-specific column names
    as they appear in TSV files.

    Storage struct::

        {label, globalkey, localkey, numeral, form, figbass,
         chord_type, root: int64, bass_note: int64}

    Import mapping to our internal model:
    - ``figbass`` -> ``inversion`` (via ``figbass_to_inversion()``)
    - ``bass_note`` -> ``bass``
    - ``chord_type`` -> ``chord_type`` (same name)
    - ``form`` is DCML-specific, not mapped to internal
    """

    label: str = "label"
    globalkey: str = "globalkey"
    localkey: str = "localkey"
    numeral: str = "numeral"
    form: str = "form"
    """Chord form in DCML syntax.  DCML-specific; not in our internal model."""
    figbass: str = "figbass"
    """Figured bass string (``""``, ``"6"``, ``"64"``, ``"65"``, etc.).
    Converted to ``Inversion`` enum on import; reconstructed on export."""
    chord_type: str = "chord_type"
    """Chord type in DCML vocabulary."""
    root: str = "root"
    """Root pitch class (0-11)."""
    bass_note: str = "bass_note"
    """Bass note pitch class (0-11).  Maps to our ``bass`` on import."""

    schema: ClassVar[pa.StructType] = pa.struct(
        [
            pa.field("label", pa.string(), nullable=True),
            pa.field("globalkey", pa.string(), nullable=True),
            pa.field("localkey", pa.string(), nullable=True),
            pa.field("numeral", pa.string(), nullable=True),
            pa.field("form", pa.string(), nullable=True),
            pa.field("figbass", pa.string(), nullable=True),
            pa.field("chord_type", pa.string(), nullable=True),
            pa.field("root", pa.int64(), nullable=True),
            pa.field("bass_note", pa.int64(), nullable=True),
        ]
    )
    """PyArrow struct type for DCML storage (raw TSV columns)."""


# endregion DCML Harmony
