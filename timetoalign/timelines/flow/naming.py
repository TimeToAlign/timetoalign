"""Generate display names for flow sections."""

from __future__ import annotations

import string
from typing import Sequence

# Atomic-section labels run through the Latin alphabet (A–Z, then a–z) and
# continue into Greek — uppercase first (Α–Ω), then lowercase (α–ω) — so that
# scores with many sections stay legible instead of spilling into punctuation
# and control characters. The reserved code point U+03A2 and the final-sigma
# form U+03C2 are skipped to keep each Greek run to its 24 canonical letters.
_GREEK_UPPER = [chr(c) for c in range(0x391, 0x3AA) if c != 0x3A2]
_GREEK_LOWER = [chr(c) for c in range(0x3B1, 0x3CA) if c != 0x3C2]
_SECTION_ALPHABET = (
    list(string.ascii_uppercase)
    + list(string.ascii_lowercase)
    + _GREEK_UPPER
    + _GREEK_LOWER
)


class SegmentNameGenerator:
    """Assign display labels to a run of atomic sections.

    The generator turns a sequence of per-section volta flags into a list
    of labels, one per section. Two policies are configurable:

    Alphabet:
        Base sections walk *alphabet* (default ``_SECTION_ALPHABET`` —
        Latin upper, Latin lower, Greek upper, Greek lower). Once the
        alphabet is exhausted it repeats with a numeric suffix (``A2``,
        ``B2``, …) so labels stay unique and printable for arbitrarily
        long scores. A caller may pass any sequence of symbols.

    Volta suffix:
        When *volta_suffix* is ``True`` (the default), a section that
        opens a volta bracket inherits the preceding non-volta section's
        label plus a positional numeric suffix (``1``, ``2``, …). A
        section **B** followed by two alternative endings is therefore
        labelled ``B``, ``B1``, ``B2`` rather than consuming the next
        three letters. The suffix is positional — the first volta after a
        base is ``1``, the second ``2`` — and is independent of the
        volta's own ending number. A non-volta section resets the
        counter, so two independent volta groups read ``B, B1, B2`` then
        ``C, C1, C2`` (never ``C3, C4``). A leading volta with no
        preceding base falls back to a base letter.

        When *volta_suffix* is ``False`` every section consumes the next
        base label in sequence (``B, C, D``), the historical behaviour.

    Examples:
        >>> SegmentNameGenerator().generate([False, True, True])
        ['A', 'A1', 'A2']
        >>> SegmentNameGenerator(volta_suffix=False).generate([False, True, True])
        ['A', 'B', 'C']
    """

    def __init__(
        self,
        alphabet: Sequence[str] | None = None,
        volta_suffix: bool = True,
    ) -> None:
        """Initialize the generator.

        Args:
            alphabet: Symbols for base section labels. ``None`` selects the
                default ``_SECTION_ALPHABET``.
            volta_suffix: When ``True``, volta sections inherit the
                preceding base label with a positional numeric suffix.
                When ``False``, every section consumes the next base label.
        """
        self._alphabet: Sequence[str] = (
            _SECTION_ALPHABET if alphabet is None else alphabet
        )
        self._volta_suffix = volta_suffix

    def _base_label(self, index: int) -> str:
        """Return the base label for the section at *index* (0-based).

        Labels walk the instance alphabet. Beyond its length the alphabet
        repeats with a numeric suffix (``A2``, ``B2``, …) so labels stay
        unique for arbitrarily long scores.
        """
        n = len(self._alphabet)
        if index < n:
            return self._alphabet[index]
        return f"{self._alphabet[index % n]}{index // n + 1}"

    def generate(self, volta_flags: Sequence[bool]) -> list[str]:
        """Return one label per section, honouring the volta-suffix policy.

        Args:
            volta_flags: ``volta_flags[i]`` is ``True`` when atomic section
                ``i`` opens a volta bracket.

        Returns:
            A list of labels the same length as *volta_flags*.
        """
        labels: list[str] = []
        base_i = 0
        volta_n = 0
        last_base: str | None = None
        for is_volta in volta_flags:
            if self._volta_suffix and is_volta and last_base is not None:
                volta_n += 1
                labels.append(f"{last_base}{volta_n}")
            else:
                label = self._base_label(base_i)
                labels.append(label)
                last_base = label
                base_i += 1
                volta_n = 0
        return labels
