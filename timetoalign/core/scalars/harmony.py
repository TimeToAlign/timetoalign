"""Harmony scalars for the Time To Align! type hierarchy.

Provides pydantic v2 frozen ``BaseModel`` scalars at five levels of
harmonic specificity, using TTA's internal model names:

- ``HarmonyLabel`` -- label + standard (satisfies ``HarmonyLabelLike``)
- ``PitchBasedHarmony`` -- adds root/bass (``PitchBasedHarmonyLike``)
- ``WesternTertianHarmony`` -- adds chord_type/inversion
- ``RomanNumeralHarmony`` -- adds numeral/localkey/globalkey
- ``DcmlHarmony`` -- DCML codec specifics (``DcmlHarmonyLike``)

Harmony scalars represent *harmonic content only* -- they do NOT carry
temporal fields (``start``, ``end``, ``duration``).  Temporal placement
belongs to the EventData row that contains the harmony scalar.

Each scalar is a ``BaseModel`` with ``model_config = ConfigDict(frozen=True)``.
WP2 migrates this file in bulk away from the previous frozen dataclasses.
Storage shapes are unchanged from the inventory in
``tta-architecture/references/type_inventory.md``.

Internal model name mapping from DCML:
- DCML ``chord_type`` -> our ``chord_type`` (same)
- DCML ``figbass`` -> our ``inversion`` (figbass is export-only)
- DCML ``form`` -> our ``chord_type`` (already captured)
- DCML ``relativeroot`` -> our ``tonicized_key``
- DCML ``mc`` -> our ``id`` (on MeasureLike)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# region HarmonyLabel (root)


class HarmonyLabel(BaseModel):
    """Root harmony scalar.  Satisfies ``HarmonyLabelLike``.

    Pydantic v2 ``BaseModel``, frozen.  Minimal: label + standard.

    Attributes:
        label: The full harmony label string (e.g. ``"V65/IV"``).
        standard: Codec identifier (e.g. ``"dcml"``, ``"chord_symbol"``).
    """

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str

    @property
    def semantic_type(self) -> str:
        return "HarmonyLabel"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "HarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        """Return a dict mirroring the storage struct."""
        return {"label": self.label, "standard": self.standard}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> HarmonyLabel | None:
        """Construct from a ``{label, standard}`` struct row."""
        label = row.get("label")
        if label is None:
            return None
        return cls(label=str(label), standard=str(row.get("standard") or ""))

    def __repr__(self) -> str:
        return f"HarmonyLabel(label={self.label!r}, standard={self.standard!r})"


# endregion HarmonyLabel

# region PitchBasedHarmony


class PitchBasedHarmony(BaseModel):
    """Harmony with root and bass (OHR model).  Satisfies ``PitchBasedHarmonyLike``.

    Pydantic v2 ``BaseModel``, frozen.

    Attributes:
        label: The full harmony label string.
        standard: Codec identifier.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None

    @property
    def semantic_type(self) -> str:
        return "PitchBasedHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "HarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PitchBasedHarmony | None:
        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
        )

    def __repr__(self) -> str:
        return f"PitchBasedHarmony(label={self.label!r}, root={self.root})"


# endregion PitchBasedHarmony

# region WesternTertianHarmony


class WesternTertianHarmony(BaseModel):
    """Western tertian chord.  Satisfies ``WesternTertianHarmonyLike``.

    Pydantic v2 ``BaseModel``, frozen.

    Attributes:
        label: The full harmony label string.
        standard: Codec identifier.
        root: Root pitch class (0-11), or ``None``.
        bass: Bass note pitch class (0-11), or ``None``.
        chord_type: Chord type (``"M"``, ``"m"``, ``"o"``, …).
        inversion: Inversion number, or ``None``.  Maps from DCML
            ``figbass`` on import.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    standard: str
    root: int | None = None
    bass: int | None = None
    chord_type: str = ""
    inversion: int | None = None

    @property
    def semantic_type(self) -> str:
        return "WesternTertianHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "WesternTertianHarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> WesternTertianHarmony | None:
        from timetoalign.fields.schemas import figbass_to_inversion

        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        inversion_raw = row.get("inversion")
        if inversion_raw is None and "figbass" in row:
            inv = figbass_to_inversion(str(row.get("figbass") or ""))
            inversion_raw = int(inv) if inv is not None else None
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
            chord_type=str(row.get("chord_type") or ""),
            inversion=int(inversion_raw) if inversion_raw is not None else None,
        )

    def __repr__(self) -> str:
        return (
            f"WesternTertianHarmony(label={self.label!r}, "
            f"chord_type={self.chord_type!r})"
        )


# endregion WesternTertianHarmony

# region RomanNumeralHarmony


class RomanNumeralHarmony(BaseModel):
    """Roman-numeral analysis.  Satisfies ``RomanNumeralHarmonyLike``.

    Pydantic v2 ``BaseModel``, frozen.

    Attributes:
        label, standard, root, bass, chord_type, inversion: see
            ``WesternTertianHarmony``.
        numeral: Roman numeral (``"I"``, ``"ii"``, ``"V"``, …).
        localkey: Local key at this position (e.g. ``"IV"``).
        globalkey: Global key of the piece (e.g. ``"C"``).
    """

    model_config = ConfigDict(frozen=True)

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
        return "RomanNumeralHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "RomanNumeralHarmonyField",
            "standard": self.standard,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "standard": self.standard,
            "root": self.root,
            "bass": self.bass,
            "chord_type": self.chord_type,
            "inversion": self.inversion,
            "numeral": self.numeral,
            "localkey": self.localkey,
            "globalkey": self.globalkey,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RomanNumeralHarmony | None:
        from timetoalign.fields.schemas import figbass_to_inversion

        label = row.get("label")
        if label is None:
            return None
        root_raw = row.get("root")
        bass_raw = row.get("bass", row.get("bass_note"))
        inversion_raw = row.get("inversion")
        if inversion_raw is None and "figbass" in row:
            inv = figbass_to_inversion(str(row.get("figbass") or ""))
            inversion_raw = int(inv) if inv is not None else None
        return cls(
            label=str(label),
            standard=str(row.get("standard") or ""),
            root=int(root_raw) if root_raw is not None else None,
            bass=int(bass_raw) if bass_raw is not None else None,
            chord_type=str(row.get("chord_type") or ""),
            inversion=int(inversion_raw) if inversion_raw is not None else None,
            numeral=str(row.get("numeral") or ""),
            localkey=str(row.get("localkey") or ""),
            globalkey=str(row.get("globalkey") or ""),
        )

    def __repr__(self) -> str:
        return (
            f"RomanNumeralHarmony(label={self.label!r}, "
            f"numeral={self.numeral!r}, key={self.globalkey}:{self.localkey})"
        )


# endregion RomanNumeralHarmony

# region DcmlHarmony


class DcmlHarmony(BaseModel):
    """DCML harmony annotation.  Satisfies ``DcmlHarmonyLike``.

    Pydantic v2 ``BaseModel``, frozen.  ``standard`` is a ``Literal["dcml"]``
    pinned at the class level.

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

    model_config = ConfigDict(frozen=True)

    label: str
    standard: Literal["dcml"] = "dcml"
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
        return "DcmlHarmony"

    def metadata_dict(self) -> dict[str, str]:
        return {
            "field_type": "DcmlHarmonyField",
            "standard": "dcml",
        }

    def to_dict(self) -> dict[str, object]:
        """Return a summary dict of all harmony properties.

        Root and bass are shown both as pitch class integers and as
        ``EnharmonicPitchClass`` objects for readability.
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
        """Construct a fully populated ``DcmlHarmony`` from a DCML label string."""
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

        chord_type = features2type(numeral, form, figbass) if numeral else ""
        inv = figbass_to_inversion(figbass or "")
        inversion = int(inv) if inv is not None else None

        root: int | None = None
        bass: int | None = None
        if numeral:
            root_tpc = roman_numeral2fifths(numeral)
            root = fifths2pc(root_tpc)
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
        - ``relativeroot`` -> ``tonicized_key``
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


# endregion DcmlHarmony
