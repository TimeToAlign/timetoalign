from __future__ import annotations

from typing import TypeAlias, Union
from decimal import Decimal
from fractions import Fraction

# Basic numeric types for coordinates
Scalar: TypeAlias = Union[int, float, Decimal, Fraction, tuple]

# Type alias for event IDs
EventId: TypeAlias = str
