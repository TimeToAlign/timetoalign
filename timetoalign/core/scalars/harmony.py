"""Harmony scalars for the Time To Align! type hierarchy.

Provides frozen dataclass scalars at five levels of harmonic specificity,
using our internal model names (not DCML field names):

- ``HarmonyLabel`` -- root: label + standard (satisfies ``HarmonyLabelLike``)
- ``PitchBasedHarmony`` -- adds root/bass (satisfies ``PitchBasedHarmonyLike``)
- ``WesternTertianHarmony`` -- adds chord_type/inversion (satisfies ``WesternTertianHarmonyLike``)
- ``RomanNumeralHarmony`` -- adds numeral/localkey/globalkey (satisfies ``RomanNumeralHarmonyLike``)
- ``DcmlHarmony`` -- DCML codec specifics (satisfies ``DcmlHarmonyLike``)

Harmony scalars represent *harmonic content only* -- they do NOT carry
temporal fields (``start``, ``end``, ``duration``).  Temporal placement
belongs to the EventData row that contains the harmony scalar.

Internal model name mapping from DCML:
- DCML ``chord_type`` -> our ``chord_type`` (same)
- DCML ``figbass`` -> our ``inversion`` (figbass is export-only)
- DCML ``form`` -> our ``chord_type`` (already captured)
- DCML ``relativeroot`` -> our ``tonicized_key``
- DCML ``mc`` -> our ``id`` (on MeasureLike)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# region HarmonyLabel (root)


@dataclass(frozen=True, slots=True)
class HarmonyLabel:
    """Root harmony scalar.  Satisfies ``HarmonyLabelLike``.

    Minimal: label + standard.  Describes harmonic content without
    temporal placement (time belongs to the EventData row).

    Attributes:
        label: The full harmony label string (e.g. ``"V65/IV"``).
        standard: Codec identifier (e.g., ``"dcml"``, ``"chord_symbol"``).
    """

    label: str
    standard: str

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "HarmonyLabel"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "HarmonyField",
            "standard": self.standard,
        }

    def __repr__(self) -> str:
        return f"HarmonyLabel(label={self.label!r}, standard={self.standard!r})"


# Backward-compat alias
Harmony = HarmonyLabel

# endregion HarmonyLabel

# region PitchBasedHarmony


@dataclass(frozen=True, slots=True)
class PitchBasedHarmony:
    """Harmony with root and bass (OHR model).  Satisfies ``PitchBasedHarmonyLike``.

    Modelled after OHR: root is the reference component, bass is
    the reference OHR (may differ from root in inversions).

    Attributes:
        label: The full harmony label string.
        standard: Codec identifier.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
    """

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "PitchBasedHarmony"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "HarmonyField",
            "standard": self.standard,
        }

    def __repr__(self) -> str:
        return f"PitchBasedHarmony(label={self.label!r}, root={self.root})"


# endregion PitchBasedHarmony

# region WesternTertianHarmony


@dataclass(frozen=True, slots=True)
class WesternTertianHarmony:
    """Western tertian chord.  Satisfies ``WesternTertianHarmonyLike``.

    Attributes:
        label: The full harmony label string.
        standard: Codec identifier.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
        chord_type: Chord type (``"M"``, ``"m"``, ``"o"``, ``"+"``, ``"Mm7"``, etc.).
        inversion: Inversion number, or ``None``.
            Maps from DCML ``figbass`` on import; ``figbass`` is export-only.
    """

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "WesternTertianHarmony"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "WesternTertianHarmonyField",
            "standard": self.standard,
        }

    def __repr__(self) -> str:
        return (
            f"WesternTertianHarmony(label={self.label!r}, "
            f"chord_type={self.chord_type!r})"
        )


# endregion WesternTertianHarmony

# region RomanNumeralHarmony


@dataclass(frozen=True, slots=True)
class RomanNumeralHarmony:
    """Roman-numeral analysis.  Satisfies ``RomanNumeralHarmonyLike``.

    Attributes:
        label: The full harmony label string.
        standard: Codec identifier.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
        chord_type: Chord type.
        inversion: Inversion number, or ``None``.
        numeral: Roman numeral (``"I"``, ``"ii"``, ``"V"``, etc.).
        localkey: Local key at this position (e.g., ``"IV"``).
        globalkey: Global key of the piece (e.g., ``"C"``).
    """

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None
    numeral: str = ""
    localkey: str = ""
    globalkey: str = ""

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "RomanNumeralHarmony"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "RomanNumeralHarmonyField",
            "standard": self.standard,
        }

    def __repr__(self) -> str:
        return (
            f"RomanNumeralHarmony(label={self.label!r}, "
            f"numeral={self.numeral!r}, key={self.globalkey}:{self.localkey})"
        )


# endregion RomanNumeralHarmony

# region DcmlHarmony


@dataclass(frozen=True, slots=True)
class DcmlHarmony:
    """DCML harmony annotation.  Satisfies ``DcmlHarmonyLike``.

    DCML-specific fields beyond the roman-numeral base:
    ``tonicized_key`` (DCML ``relativeroot``) and ``pedal``.

    Attributes:
        label: The full DCML label string (e.g. ``"V65/IV"``).
        standard: Always ``"dcml"``.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
        chord_type: Chord type (our internal name).
        inversion: Inversion number (mapped from DCML ``figbass``), or ``None``.
        numeral: Roman numeral component.
        localkey: Local key at this position.
        globalkey: Global key of the piece.
        tonicized_key: Tonicized key (DCML ``relativeroot``), or ``None``.
        pedal: Pedal tone, or ``None``.
    """

    label: str
    standard: str = "dcml"
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None
    numeral: str = ""
    localkey: str = ""
    globalkey: str = ""
    tonicized_key: str | None = None
    pedal: str | None = None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "DcmlHarmony"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "DcmlHarmonyField",
            "standard": "dcml",
        }

    def to_dict(self) -> dict[str, object]:
        """Return a summary dict of all harmony properties.

        Root and bass are shown both as pitch class integers and as
        ``GenericPitch`` objects for readability.

        Returns:
            A dict with all harmony fields.
        """
        from .pitch import EnharmonicPitchClass

        root_gpc = (
            EnharmonicPitchClass(pitch_class=self.root)
            if self.root is not None
            else None
        )
        bass_gpc = (
            EnharmonicPitchClass(pitch_class=self.bass)
            if self.bass is not None
            else None
        )
        return {
            "label": self.label,
            "numeral": self.numeral,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
            "root": root_gpc,
            "bass": bass_gpc,
            "globalkey": self.globalkey,
            "localkey": self.localkey,
            "tonicized_key": self.tonicized_key,
        }

    @classmethod
    def from_label(
        cls,
        label: str,
        *,
        globalkey: str = "C",
        localkey: str = "I",
    ) -> DcmlHarmony:
        """Construct a fully populated ``DcmlHarmony`` from a DCML label string.

        Parses the label using the ``ms3`` DCML regex and derives
        ``numeral``, ``figbass``, ``chord_type``, ``inversion``,
        ``root``, ``bass``, and ``tonicized_key`` automatically.

        Args:
            label: A DCML harmony label (e.g. ``"V65/IV"``, ``"viio7"``, ``"I"``).
            globalkey: Global key of the piece (default ``"C"``).
            localkey: Local key at this position (default ``"I"``).

        Returns:
            A fully populated ``DcmlHarmony``.

        Raises:
            ValueError: If the label cannot be parsed by the DCML regex.

        Examples:
            >>> DcmlHarmony.from_label("V65/IV", globalkey="C")
            DcmlHarmony(label='V65/IV', key=C:I)
            >>> h = DcmlHarmony.from_label("I")
            >>> h.chord_type
            'M'
        """
        from ms3.expand_dcml import features2type
        from ms3.utils import fifths2pc, roman_numeral2fifths
        from ms3.utils.constants import DCML_REGEX

        from timetoalign.fields.schemas import figbass_to_inversion

        m = DCML_REGEX.match(label)
        if m is None:
            raise ValueError(f"Cannot parse DCML label: {label!r}")

        parts = {k: v for k, v in m.groupdict().items() if v is not None}
        numeral = parts.get("numeral", "")
        form = parts.get("form")
        figbass = parts.get("figbass")
        relativeroot = parts.get("relativeroot")
        pedal = parts.get("pedal")

        # Chord type from numeral + form + figbass
        chord_type = features2type(numeral, form, figbass) if numeral else ""

        # Inversion from figbass
        inv = figbass_to_inversion(figbass or "")
        inversion = int(inv) if inv is not None else None

        # Root pitch class: numeral offset relative to globalkey
        root: int | None = None
        bass: int | None = None
        if numeral:
            root_tpc = roman_numeral2fifths(numeral)
            root = fifths2pc(root_tpc)
            # Bass: for inverted chords, use chord2tpcs from ms3
            try:
                from ms3 import chord2tpcs

                chord_str = parts.get("chord", label)
                tpcs = chord2tpcs(chord_str)
                if tpcs:
                    bass = fifths2pc(tpcs[0])
            except Exception:
                bass = root

        return cls(
            label=label,
            globalkey=globalkey,
            localkey=localkey,
            numeral=numeral,
            chord_type=chord_type,
            inversion=inversion,
            root=root,
            bass=bass,
            tonicized_key=relativeroot,
            pedal=pedal,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DcmlHarmony | None:
        """Construct from a DCML storage row dict.

        Maps DCML storage field names to internal model names:
        - ``bass_note`` -> ``bass``
        - ``figbass`` -> ``inversion`` (via ``figbass_to_inversion()``)
        - ``chord_type`` -> ``chord_type`` (same)
        - ``relativeroot`` -> ``tonicized_key``

        Args:
            row: Dict with DCML storage field names (from PyArrow ``.as_py()``).

        Returns:
            A ``DcmlHarmony``, or ``None`` if ``label`` is null.
        """
        from timetoalign.fields.schemas import figbass_to_inversion

        label = row.get("label")
        if label is None:
            return None

        root_raw = row.get("root")
        root = int(root_raw) if root_raw is not None else None
        bass_raw = row.get("bass_note", row.get("bass"))
        bass = int(bass_raw) if bass_raw is not None else None
        figbass_raw = row.get("figbass", "")
        inversion_raw = row.get("inversion")
        if inversion_raw is not None:
            inversion = int(inversion_raw)
        else:
            inv = figbass_to_inversion(str(figbass_raw or ""))
            inversion = int(inv) if inv is not None else None

        globalkey = str(row.get("globalkey") or "")
        localkey = str(row.get("localkey") or "")

        return cls(
            label=str(label),
            globalkey=globalkey,
            localkey=localkey,
            numeral=str(row.get("numeral") or ""),
            chord_type=str(row.get("chord_type") or ""),
            inversion=inversion,
            root=root,
            bass=bass,
            tonicized_key=row.get("relativeroot") or row.get("tonicized_key"),
            pedal=row.get("pedal"),
        )

    def __repr__(self) -> str:
        return (
            f"DcmlHarmony(label={self.label!r}, key={self.globalkey}:{self.localkey})"
        )


# Backward-compat alias
DcmlLabel = DcmlHarmony

# endregion DcmlHarmony
