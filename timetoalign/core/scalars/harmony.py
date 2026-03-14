"""Harmony scalars for the Time To Align! type hierarchy.

Provides frozen dataclass scalars at five levels of harmonic specificity,
using our internal model names (not DCML field names):

- ``HarmonyLabel`` -- root: label + standard + temporal (satisfies ``HarmonyLabelLike``)
- ``PitchBasedHarmony`` -- adds root/bass (satisfies ``PitchBasedHarmonyLike``)
- ``WesternTertianHarmony`` -- adds chord_type/inversion (satisfies ``WesternTertianHarmonyLike``)
- ``RomanNumeralHarmony`` -- adds numeral/localkey/globalkey (satisfies ``RomanNumeralHarmonyLike``)
- ``DcmlHarmony`` -- DCML codec specifics (satisfies ``DcmlHarmonyLike``)

Each scalar declares ``start``, ``end``, ``duration`` fields to satisfy
``IntervalEventLike`` (temporal fields use the canonical TTA model names).

Internal model name mapping from DCML:
- DCML ``chord_type`` -> our ``chord_type`` (same)
- DCML ``figbass`` -> our ``inversion`` (figbass is export-only)
- DCML ``form`` -> our ``chord_type`` (already captured)
- DCML ``relativeroot`` -> our ``tonicized_key``
- DCML ``mc`` -> our ``id`` (on MeasureLike)
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import Coordinate

# region HarmonyLabel (root)


@dataclass(frozen=True, slots=True)
class HarmonyLabel:
    """Root harmony scalar.  Satisfies ``HarmonyLabelLike``.

    Minimal: label + standard + temporal position.
    A harmony label ties a harmonic analysis to a temporal interval.

    Attributes:
        label: The full harmony label string (e.g. ``"V65/IV"``).
        standard: Codec identifier (e.g., ``"dcml"``, ``"chord_symbol"``).
        start: Temporal position as a ``Coordinate``.
        end: End position as a ``Coordinate``, or ``None``.
        duration: Duration as a ``Coordinate``, or ``None``.
    """

    label: str
    standard: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Coordinate | None = None

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
        start: Temporal position.
        end: End position, or ``None``.
        duration: Duration, or ``None``.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
    """

    label: str
    standard: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Coordinate | None = None
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
        start: Temporal position.
        end: End position, or ``None``.
        duration: Duration, or ``None``.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
        chord_type: Chord type (``"M"``, ``"m"``, ``"o"``, ``"+"``, ``"Mm7"``, etc.).
        inversion: Inversion number, or ``None``.
            Maps from DCML ``figbass`` on import; ``figbass`` is export-only.
    """

    label: str
    standard: str
    start: Coordinate
    end: Coordinate | None = None
    duration: Coordinate | None = None
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
        start: Temporal position.
        end: End position, or ``None``.
        duration: Duration, or ``None``.
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
    start: Coordinate
    end: Coordinate | None = None
    duration: Coordinate | None = None
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
        start: Temporal position, or ``None``.
        end: End position, or ``None``.
        duration: Duration, or ``None``.
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
    start: Coordinate | None = None
    end: Coordinate | None = None
    duration: Coordinate | None = None
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

    def __repr__(self) -> str:
        return (
            f"DcmlHarmony(label={self.label!r}, key={self.globalkey}:{self.localkey})"
        )


# Backward-compat alias
DcmlLabel = DcmlHarmony

# endregion DcmlHarmony
