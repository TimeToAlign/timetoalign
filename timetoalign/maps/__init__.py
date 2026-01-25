"""Conversion maps for TimeToAlign!

This module provides coordinate conversion infrastructure for transforming
values between different units and timelines.

The key abstractions are:
- ConversionMap: Base protocol/ABC for all maps
- LinearMap: Affine transformation (y = ax + b)
- ShiftMap: Offset transformation (y = x + b)
- TableMap: Lookup/interpolation-based mapping
- ChainMap: Composition of multiple maps
- PiecewiseMap: Region-based mapping with different maps for different intervals
"""

from __future__ import annotations

from .base import ConversionMap
from .composite import ChainMap, PiecewiseMap
from .linear import LinearMap, ScalarMap, ShiftMap
from .table import TableMap

__all__ = [
    # Base
    "ConversionMap",
    # Linear maps
    "LinearMap",
    "ScalarMap",
    "ShiftMap",
    # Table maps
    "TableMap",
    # Composite maps
    "ChainMap",
    "PiecewiseMap",
]
