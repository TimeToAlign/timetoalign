"""Mixins for Timeline modalities (Continuous/Discrete).

These mixins enforce constraints on number types and provide
sensible defaults for each modality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from timetoalign.core import NumberType

if TYPE_CHECKING:
    pass


class ContinuousMixin:
    """Mixin for timelines with continuous coordinates (float, Fraction).

    Continuous timelines represent time as a continuum where any
    real-valued coordinate is valid. This is appropriate for:
    - Acoustic time (seconds with arbitrary precision)
    - Musical time (fractional beats, quarter notes)
    - Graphical coordinates (real-valued positions)

    Attributes:
        _allowed_number_types: Tuple of valid NumberTypes (float, fraction).
        _default_number_type: Default to float for performance.
    """

    _allowed_number_types: ClassVar[tuple[NumberType, ...]] = (
        NumberType.float,
        NumberType.fraction,
    )
    _default_number_type: ClassVar[NumberType] = NumberType.float


class DiscreteMixin:
    """Mixin for timelines with discrete coordinates (int only).

    Discrete timelines represent time as countable units where only
    integer coordinates are valid. This is appropriate for:
    - MIDI ticks (quantized logical time)
    - Audio samples (discrete physical time)
    - Pixels (discrete graphical positions)

    Attributes:
        _allowed_number_types: Tuple containing only int.
        _default_number_type: int.
    """

    _allowed_number_types: ClassVar[tuple[NumberType, ...]] = (NumberType.int,)
    _default_number_type: ClassVar[NumberType] = NumberType.int
