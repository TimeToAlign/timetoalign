"""Interval-to-constant and quarters-to-measures conversion maps.

This module provides:
- IntervalToConstantMap: Generic step-function map (interval -> constant value)
- QuartersToMeasureNumber: Map quarters -> MN labels (no interpolation, NOT a coordinate map)
- QuartersToFloatingMeasures: Map quarters -> measure coordinates (with interpolation)

These maps enable score timelines to express coordinates in both quarter-beat
and measure terms, supporting cross-domain alignment and human-readable output.
"""

from __future__ import annotations

import re
import warnings
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Generic, Sequence, TypeVar

import numpy as np
from numpy.typing import NDArray

from timetoalign.core.enums import ExtrapolationPolicy, InterpolationKind, TimeUnit
from timetoalign.core.time import (
    CoordinateValue,
    rational_to_wire,
    wire_to_rational,
)
from timetoalign.maps.base import ConversionMap
from timetoalign.maps.table import TableMap

if TYPE_CHECKING:
    from typing_extensions import Self

    from timetoalign.loader.score.stores.measures import MeasureData
    from timetoalign.maps.meter import MetricMap


# Type variable for IntervalToConstantMap output type
T = TypeVar("T")


# region IntervalToConstantMap


class IntervalToConstantMap(ConversionMap[T], Generic[T]):
    """Interval-to-constant map: each interval [x_i, x_{i+1}) maps to value_i.

    Unlike TableMap, IntervalToConstantMap does not interpolate. A coordinate x
    returns the value associated with the interval that contains x.

    Values can be any type (string, int, float, etc.). This is NOT a coordinate
    conversion map when values are non-numeric (e.g., string labels).

    This is useful for:
    - Measure number lookup (quarters -> MN label)
    - Region/section lookup (coordinate -> section name)
    - Any step-function relationship

    Attributes:
        boundaries: Sorted x-coordinates defining interval starts.
        values: Value for each interval (len = len(boundaries)).

    Examples:
        >>> # Map quarters to section names
        >>> section_map = IntervalToConstantMap(
        ...     boundaries=[0, 16, 32, 48],
        ...     values=["Intro", "Verse", "Chorus", "Outro"],
        ...     source_unit="quarters",
        ... )
        >>> section_map(20)
        'Verse'
        >>> section_map(40)
        'Chorus'
    """

    def __init__(
        self,
        *,
        boundaries: Sequence[CoordinateValue],
        values: Sequence[T],
        source_unit: TimeUnit | str | None = None,
        target_unit: TimeUnit | str | None = None,
        uid: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize an IntervalToConstantMap.

        Args:
            boundaries: Interval start positions. Must be strictly increasing.
            values: Value for each interval. Must have same length as boundaries.
            source_unit: The unit of input coordinates (optional).
            target_unit: The unit of output values (optional). Use None for
                non-coordinate outputs like string labels.
            uid: Optional explicit ID.
            name: Human-readable name for this map.

        Raises:
            ValueError: If boundaries and values have different lengths.
            ValueError: If boundaries are not strictly increasing.
            ValueError: If fewer than 1 boundary is provided.
        """
        super().__init__(
            source_unit=source_unit,
            target_unit=target_unit,
            uid=uid,
            name=name,
        )

        if len(boundaries) != len(values):
            raise ValueError(
                f"boundaries and values must have same length, "
                f"got {len(boundaries)} and {len(values)}"
            )
        if len(boundaries) < 1:
            raise ValueError("IntervalToConstantMap requires at least 1 boundary")

        # Convert to numpy array for fast lookup
        self._boundaries = np.array([float(v) for v in boundaries], dtype=np.float64)
        self._values = list(values)

        # Store original values for serialization (may have Fractions)
        self._boundaries_original = list(boundaries)

        # Validate monotonicity
        if len(self._boundaries) > 1:
            diffs = np.diff(self._boundaries)
            if not np.all(diffs > 0):
                raise ValueError("boundaries must be strictly monotonically increasing")

    @property
    def boundaries(self) -> NDArray[np.floating[Any]]:
        """The interval start positions."""
        return self._boundaries

    @property
    def values(self) -> list[T]:
        """The values for each interval."""
        return self._values

    @property
    def is_invertible(self) -> bool:
        """IntervalToConstantMap is NOT invertible (many-to-one)."""
        return False

    def _convert_scalar(self, value: CoordinateValue, **kwargs: Any) -> T:
        """Find the value for a given coordinate.

        Uses binary search for O(log n) lookup.
        """
        x = float(value)

        # Find rightmost boundary <= x
        idx = int(np.searchsorted(self._boundaries, x, side="right")) - 1

        # Clamp to valid range
        idx = max(0, min(idx, len(self._values) - 1))

        return self._values[idx]

    def _convert_array(self, values: NDArray[Any], **kwargs: Any) -> NDArray[Any]:
        """Vectorized lookup.

        Note: Returns object array if values are non-numeric (e.g., strings).
        """
        x = values.astype(np.float64)

        # Binary search for each value
        indices = np.searchsorted(self._boundaries, x, side="right") - 1
        indices = np.clip(indices, 0, len(self._values) - 1)

        # Convert to numpy array (object dtype for strings)
        return np.array([self._values[i] for i in indices])

    def inverse(self) -> Self:
        """IntervalToConstantMap is not invertible.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "IntervalToConstantMap is not invertible: many coordinates map to same value"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d["boundaries"] = [rational_to_wire(v) for v in self._boundaries_original]
        d["values"] = list(self._values)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntervalToConstantMap[Any]:
        """Deserialize from dictionary."""
        return cls(
            boundaries=[wire_to_rational(v) for v in data["boundaries"]],
            values=data["values"],
            source_unit=data.get("source_unit"),
            target_unit=data.get("target_unit"),
            uid=data.get("id"),
            name=data.get("name"),
        )

    def to_table_map(
        self, kind: InterpolationKind = InterpolationKind.previous
    ) -> TableMap:
        """Convert to TableMap for numeric values.

        This allows using TableMap operations on interval data when values are
        numeric.

        Args:
            kind: Interpolation kind. Default is "previous" (step function).

        Returns:
            TableMap with the same boundaries and values.

        Raises:
            TypeError: If values are not numeric.
        """
        if not all(isinstance(v, (int, float, Fraction)) for v in self._values):
            raise TypeError("to_table_map() requires numeric values")

        # Need at least 2 points for TableMap; add extrapolation point
        x_values = list(self._boundaries)
        y_values = [float(v) for v in self._values]

        # Add final extrapolation point (extend last interval)
        if len(x_values) >= 1:
            # Use final value extending one unit beyond last boundary
            final_x = x_values[-1] + 1.0
            x_values.append(final_x)
            y_values.append(y_values[-1])

        return TableMap(
            x_values=x_values,
            y_values=y_values,
            kind=kind,
            extrapolate=ExtrapolationPolicy.extrapolate,
            source_unit=self._source_unit,
            target_unit=self._target_unit,
        )

    def __repr__(self) -> str:
        n = len(self._boundaries)
        parts = [f"n_intervals={n}"]
        if self._source_unit:
            parts.append(f"source_unit={self._source_unit}")
        if self._target_unit:
            parts.append(f"target_unit={self._target_unit}")
        return f"IntervalToConstantMap({', '.join(parts)})"


# endregion


# region QuartersToMeasureNumber


class QuartersToMeasureNumber(IntervalToConstantMap[str]):
    """Map quarters to measure number labels (no interpolation).

    Given a quarter position, returns the MN label (e.g., "1", "19a", "0")
    of the measure containing that position.

    This is NOT a coordinate conversion map - it returns string labels,
    not numeric coordinates. Therefore target_unit is None.

    MN labels are strings because they may contain suffixes (e.g., "19a", "19b"
    for split bars, or "0" for anacrusis).

    Examples:
        >>> cmap = QuartersToMeasureNumber(
        ...     boundaries=[0, 4, 8, 12],
        ...     mns=["1", "2", "3", "4"],
        ... )
        >>> cmap(0.0)    # Start of M1
        '1'
        >>> cmap(3.5)    # Still in M1 (assuming 4 quarters/measure)
        '1'
        >>> cmap(4.0)    # Start of M2
        '2'

        >>> # From MetricMap
        >>> cmap = QuartersToMeasureNumber.from_metric_map(meter)
    """

    def __init__(
        self,
        *,
        boundaries: Sequence[CoordinateValue],
        mns: Sequence[str],
        source_unit: TimeUnit | str = TimeUnit.quarters,
        uid: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize a QuartersToMeasureNumber map.

        Args:
            boundaries: Measure start positions in quarters.
            mns: Measure Number labels for each measure.
            source_unit: Source unit (default: quarters).
            uid: Optional explicit ID.
            name: Human-readable name (default: "quarters_to_mn").
        """
        super().__init__(
            boundaries=boundaries,
            values=mns,
            source_unit=source_unit,
            target_unit=None,  # Not a coordinate map - returns labels
            uid=uid,
            name=name or "quarters_to_mn",
        )

    @property
    def mns(self) -> list[str]:
        """The measure number labels."""
        return self._values

    @classmethod
    def from_metric_map(cls, meter: MetricMap) -> QuartersToMeasureNumber:
        """Create from a MetricMap.

        Args:
            meter: MetricMap with measure boundary information.

        Returns:
            QuartersToMeasureNumber map.
        """
        boundaries = list(meter._starts_frac)
        mns = list(meter._mns)
        return cls(boundaries=boundaries, mns=mns)

    @classmethod
    def from_measure_data(cls, measures: MeasureData) -> QuartersToMeasureNumber:
        """Create from MeasureData (loaded from TSV/JSON).

        Args:
            measures: MeasureData with measure events.

        Returns:
            QuartersToMeasureNumber map.
        """
        if len(measures) == 0:
            raise ValueError("MeasureData is empty")

        # Extract start positions and MN labels from the PyArrow table
        boundaries: list[float] = []
        mns: list[str] = []

        for event in measures:
            start = event.get("start")
            mn = event.get("mn")

            # Handle coordinate struct format
            if isinstance(start, dict) and "value" in start:
                start_val = float(start["value"])
            elif start is not None:
                start_val = float(start)
            else:
                continue

            # Handle MN (may be None, convert to string)
            if mn is None:
                # Fall back to MC if MN is not available
                mc = event.get("mc")
                mn_str = str(mc) if mc is not None else "?"
            else:
                mn_str = str(mn)

            boundaries.append(start_val)
            mns.append(mn_str)

        return cls(boundaries=boundaries, mns=mns)

    def to_floating_measures(self) -> QuartersToFloatingMeasures:
        """Convert string MN labels to floating-point measure map.

        Non-numeric suffixes (e.g., "a" in "19a") are stripped with a warning.

        Returns:
            QuartersToFloatingMeasures map with interpolation.

        Raises:
            ValueError: If any MN label cannot be parsed to a number.
        """
        y_values: list[float] = []
        stripped_any = False

        for mn in self._values:
            s = str(mn)
            # Extract leading numeric part (including negative and decimals)
            match = re.match(r"^-?\d+\.?\d*", s)
            if match:
                numeric = float(match.group())
                if match.group() != s:
                    stripped_any = True
                y_values.append(numeric)
            else:
                raise ValueError(f"Cannot convert MN '{s}' to numeric measure")

        if stripped_any:
            warnings.warn(
                "Non-numeric suffixes were stripped from MN labels; "
                "converting back will lose this information.",
                UserWarning,
                stacklevel=2,
            )

        return QuartersToFloatingMeasures(
            x_values=self._boundaries_original,
            y_values=y_values,
            source_unit=self._source_unit,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d["type"] = "QuartersToMeasureNumber"
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuartersToMeasureNumber:
        """Deserialize from dictionary."""
        return cls(
            boundaries=[wire_to_rational(v) for v in data["boundaries"]],
            mns=[str(v) for v in data["values"]],
            source_unit=data.get("source_unit", TimeUnit.quarters),
            uid=data.get("id"),
            name=data.get("name"),
        )

    def __repr__(self) -> str:
        n = len(self._boundaries)
        return f"QuartersToMeasureNumber(n_measures={n})"


# endregion


# region QuartersToFloatingMeasures


class QuartersToFloatingMeasures(TableMap):
    """Map quarters to measure coordinates (with linear interpolation).

    Returns continuous measure coordinates where:
    - 1.0 = start of measure 1
    - 1.5 = halfway through measure 1
    - 2.0 = start of measure 2

    This IS a coordinate conversion map: it converts from quarters to
    measures (TimeUnit.measures).

    This is useful for visualization (e.g., piano roll x-axis in measures)
    and for interpolating positions within measures.

    Examples:
        >>> cmap = QuartersToFloatingMeasures(
        ...     x_values=[0, 4, 8, 12],
        ...     y_values=[1.0, 2.0, 3.0, 4.0],
        ... )
        >>> cmap(0.0)    # Start of M1
        1.0
        >>> cmap(2.0)    # Halfway through M1 (4 quarters/measure)
        1.5
        >>> cmap(4.0)    # Start of M2
        2.0

        >>> # From MetricMap
        >>> cmap = QuartersToFloatingMeasures.from_metric_map(meter)
    """

    def __init__(
        self,
        *,
        x_values: Sequence[CoordinateValue],
        y_values: Sequence[float],
        source_unit: TimeUnit | str = TimeUnit.quarters,
        target_unit: TimeUnit | str = TimeUnit.floating_measures,
        uid: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize a QuartersToFloatingMeasures map.

        Args:
            x_values: Measure start positions in quarters.
            y_values: Measure coordinates (1.0, 2.0, ...) at each start.
            source_unit: Source unit (default: quarters).
            target_unit: Target unit (default: measures).
            uid: Optional explicit ID.
            name: Human-readable name (default: "quarters_to_measures").
        """
        super().__init__(
            x_values=x_values,
            y_values=y_values,
            kind=InterpolationKind.linear,
            extrapolate=ExtrapolationPolicy.extrapolate,
            source_unit=source_unit,
            target_unit=target_unit,
            uid=uid,
        )
        self._name = name or "quarters_to_measures"

    @classmethod
    def from_metric_map(cls, meter: MetricMap) -> QuartersToFloatingMeasures:
        """Create from a MetricMap.

        Uses MN integers (or MC if MN not available) as measure numbers.
        Adds a final extrapolation point for the end of the last measure.

        Args:
            meter: MetricMap with measure boundary information.

        Returns:
            QuartersToFloatingMeasures map.
        """
        x_values: list[Fraction] = list(meter._starts_frac)
        y_values: list[float] = []

        # Convert MN labels to floats
        for i, mn in enumerate(meter._mns):
            try:
                # Try parsing MN as numeric (strip non-numeric suffix)
                match = re.match(r"^-?\d+\.?\d*", str(mn))
                if match:
                    y_values.append(float(match.group()))
                else:
                    # Fall back to MC (1-indexed)
                    y_values.append(float(meter._mcs[i]))
            except (ValueError, TypeError):
                # Fall back to MC
                y_values.append(float(meter._mcs[i]))

        # Add final extrapolation point
        final_x = meter.total_length
        final_y = y_values[-1] + 1.0
        x_values.append(final_x)
        y_values.append(final_y)

        return cls(x_values=x_values, y_values=y_values)

    @classmethod
    def from_measure_data(cls, measures: MeasureData) -> QuartersToFloatingMeasures:
        """Create from MeasureData (loaded from TSV/JSON).

        Args:
            measures: MeasureData with measure events.

        Returns:
            QuartersToFloatingMeasures map.
        """
        if len(measures) == 0:
            raise ValueError("MeasureData is empty")

        x_values: list[float] = []
        y_values: list[float] = []

        for event in measures:
            start = event.get("start")
            mn = event.get("mn")
            mc = event.get("mc")

            # Handle coordinate struct format
            if isinstance(start, dict) and "value" in start:
                start_val = float(start["value"])
            elif start is not None:
                start_val = float(start)
            else:
                continue

            # Determine measure number (prefer MN, fall back to MC)
            mn_val: float
            if mn is not None:
                try:
                    match = re.match(r"^-?\d+\.?\d*", str(mn))
                    if match:
                        mn_val = float(match.group())
                    else:
                        mn_val = (
                            float(mc) if mc is not None else float(len(y_values) + 1)
                        )
                except (ValueError, TypeError):
                    mn_val = float(mc) if mc is not None else float(len(y_values) + 1)
            elif mc is not None:
                mn_val = float(mc)
            else:
                mn_val = float(len(y_values) + 1)

            x_values.append(start_val)
            y_values.append(mn_val)

        # Add final extrapolation point
        # Get duration of last measure from our collected y_values
        # Use the spacing between last two measures as estimate, or default to 4
        if len(x_values) >= 2:
            # Estimate duration as spacing between last two measure starts
            last_duration = x_values[-1] - x_values[-2]
            final_x = x_values[-1] + last_duration
        else:
            # Assume 4 quarters if only one measure
            final_x = x_values[-1] + 4.0

        final_y = y_values[-1] + 1.0
        x_values.append(final_x)
        y_values.append(final_y)

        return cls(x_values=x_values, y_values=y_values)

    def inverse(self) -> TableMap:
        """Return the inverse map (measures -> quarters).

        Returns:
            A TableMap converting measures to quarters.

        Raises:
            NotImplementedError: If not invertible (should not happen for this map).
        """
        if not self._is_invertible:
            raise NotImplementedError(
                "Cannot invert QuartersToFloatingMeasures: y values are not strictly monotonic"
            )

        # The inverse goes from measures to quarters
        # Use the base TableMap class for the inverse
        if self._y_decreasing:
            return TableMap(
                x_values=list(reversed(self._y_original)),
                y_values=list(reversed(self._x_original)),
                kind=self._kind,
                extrapolate=self._extrapolate,
                source_unit=self._target_unit,
                target_unit=self._source_unit,
            )
        else:
            return TableMap(
                x_values=self._y_original,
                y_values=self._x_original,
                kind=self._kind,
                extrapolate=self._extrapolate,
                source_unit=self._target_unit,
                target_unit=self._source_unit,
            )

    def to_measure_number_map(
        self,
        mns: Sequence[str] | None = None,
    ) -> QuartersToMeasureNumber:
        """Convert to non-interpolating measure number map.

        Args:
            mns: MN labels to use. If None, uses floor(y_value) as string.

        Returns:
            QuartersToMeasureNumber with the same boundaries.
        """
        # Exclude final extrapolation point
        boundaries = list(self._x_original[:-1])

        if mns is None:
            # Generate MN labels from y values
            mns_list = [str(int(y)) for y in self._y[:-1]]
        else:
            mns_list = list(mns)

        return QuartersToMeasureNumber(
            boundaries=boundaries,
            mns=mns_list,
            source_unit=self._source_unit,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d["type"] = "QuartersToFloatingMeasures"
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuartersToFloatingMeasures:
        """Deserialize from dictionary."""
        return cls(
            x_values=[wire_to_rational(v) for v in data["x_values"]],
            y_values=[float(wire_to_rational(v)) for v in data["y_values"]],
            source_unit=data.get("source_unit", TimeUnit.quarters),
            target_unit=data.get("target_unit", TimeUnit.floating_measures),
            uid=data.get("id"),
            name=data.get("name"),
        )

    def __repr__(self) -> str:
        n = len(self._x) - 1  # Exclude extrapolation point
        return f"QuartersToFloatingMeasures(n_measures={n})"


# endregion
