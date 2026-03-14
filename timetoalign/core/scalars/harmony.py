"""Harmony scalar for DCML harmony annotations.

``Harmony`` is a frozen dataclass that represents a single harmony
annotation following the DCML standard.  It satisfies ``HarmonyLike``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Harmony:
    """A single DCML harmony annotation.  Satisfies ``HarmonyLike``.

    Attributes:
        label: The full harmony label string (e.g. ``"V65/IV"``).
        globalkey: The global key of the piece (e.g. ``"C"``).
        localkey: The local key at this position (e.g. ``"IV"``).
        numeral: The Roman numeral component (e.g. ``"V"``).
        form: The chord form (e.g. ``"M"``, ``"m"``).
        figbass: The figured bass component (e.g. ``"65"``).
        chord_type: The chord type (e.g. ``"M"``, ``"m"``, ``"o"``, ``"+"``).
        root: Root pitch class (0-11), or ``None``.
        bass_note: Bass note pitch class (0-11), or ``None``.
    """

    label: str
    globalkey: str
    localkey: str
    numeral: str
    form: str
    figbass: str
    chord_type: str
    root: int | None
    bass_note: int | None

    @property
    def semantic_type(self) -> str:
        """The canonical SemanticType name."""
        return "Harmony"

    def metadata_dict(self) -> dict[str, str]:
        """Return metadata dict matching the Parquet storage contract."""
        return {
            "field_type": "HarmonyField",
            "standard": "dcml",
        }

    def __repr__(self) -> str:
        return f"Harmony(label={self.label!r}, key={self.globalkey}:{self.localkey})"
