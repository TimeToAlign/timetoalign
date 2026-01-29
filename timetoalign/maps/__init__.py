"""Conversion maps for TimeToAlign!

This module provides coordinate conversion infrastructure for transforming
values between different units and timelines.

The key abstractions are:
- ConversionMap: Base protocol/ABC for all maps
- LinearMap: Affine transformation (y = ax + b)
- ScalarMap: Pure scaling (y = ax)
- ShiftMap: Offset transformation (y = x + b)
- TableMap: Lookup/interpolation-based mapping
- ChainMap: Composition of multiple maps
- PiecewiseMap: Region-based mapping with different maps for different intervals

Convenience classes for common conversions:
- TicksToQuarters, QuartersToTicks: MIDI tick <-> quarter note
- SamplesToSeconds, SecondsToSamples: Audio sample <-> seconds
"""

from __future__ import annotations

from .base import ConversionMap
from .composite import ChainMap, PiecewiseMap
from .convenience import (
    QuartersToTicks,
    SamplesToSeconds,
    SecondsToSamples,
    TicksToQuarters,
)
from .interpolation import InterpolationMap
from .linear import LinearMap, ScalarMap, ShiftMap
from .table import TableMap

__all__ = [
    # Base
    "ConversionMap",
    # Interpolation (internal engine)
    "InterpolationMap",
    # Linear maps
    "LinearMap",
    "ScalarMap",
    "ShiftMap",
    # Table maps
    "TableMap",
    # Composite maps
    "ChainMap",
    "PiecewiseMap",
    # Convenience classes
    "TicksToQuarters",
    "QuartersToTicks",
    "SamplesToSeconds",
    "SecondsToSamples",
]
