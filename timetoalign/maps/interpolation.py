"""InterpolationMap: Core bidirectional coordinate conversion engine.

This module provides InterpolationMap, a lightweight dataclass for O(log n)
bidirectional coordinate conversion using numpy.interp.

InterpolationMap is the internal engine used by:
- TimelineGroup coordinate conversion
- TableMap forward/inverse conversions
- WarpMap alignment warping

Parent-child coordinate conversion in Timeline uses exact offset arithmetic
instead (Phase 6.1).

It is NOT a ConversionMap subclass - it's a lower-level building block
optimized for performance. ConversionMap has richer functionality (units,
serialization, composition) while InterpolationMap is pure interpolation.

Design rationale (from unified_timestamp_architecture.md):
- No table lookups for coordinate conversion - direct np.interp calls
- Precomputed sorted arrays enable O(log n) binary search
- Bidirectional: forward (source -> target) and inverse (target -> source)
- Immutable: safe to share between threads/contexts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from ..core.enums import TimeUnit
    from .table import TableMap

module_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InterpolationMap:
    """Bidirectional coordinate mapping using numpy.interp.

    Provides O(log n) coordinate conversion without table lookup.
    Used for:
    - Parent <-> Child timeline relationships
    - Timeline <-> Group relationships
    - C-Map forward and inverse conversions

    The map is bidirectional: forward() converts source -> target,
    inverse() converts target -> source.

    Attributes:
        source_coords: Sorted source axis coordinates (float64).
        target_coords: Corresponding target values (float64).
        source_id: Timeline/C-Map ID for source.
        target_id: Timeline/C-Map ID for target.
        source_unit: The unit of source coordinates (optional).
        target_unit: The unit of target coordinates (optional).

    Examples:
        >>> # Simple offset relationship: child at offset 10 in parent
        >>> imap = InterpolationMap(
        ...     source_coords=np.array([0.0, 100.0]),  # child coords
        ...     target_coords=np.array([10.0, 110.0]),  # parent coords
        ...     source_id="child:1",
        ...     target_id="parent:1",
        ... )
        >>> imap.forward(50.0)  # child 50 -> parent 60
        60.0
        >>> imap.inverse(60.0)  # parent 60 -> child 50
        50.0

        >>> # Tempo map: ticks to seconds
        >>> imap = InterpolationMap(
        ...     source_coords=np.array([0.0, 480.0, 960.0]),
        ...     target_coords=np.array([0.0, 0.5, 1.5]),
        ...     source_id="ticks",
        ...     target_id="seconds",
        ... )
        >>> imap.forward(240.0)  # 240 ticks -> 0.25 seconds
        0.25
    """

    source_coords: NDArray[np.floating[Any]] = field(repr=False)
    target_coords: NDArray[np.floating[Any]] = field(repr=False)
    source_id: str
    target_id: str
    source_unit: "TimeUnit | None" = field(default=None)
    target_unit: "TimeUnit | None" = field(default=None)

    def __post_init__(self) -> None:
        """Validate arrays after initialization."""
        if len(self.source_coords) != len(self.target_coords):
            raise ValueError(
                f"source_coords and target_coords must have same length, "
                f"got {len(self.source_coords)} and {len(self.target_coords)}"
            )
        if len(self.source_coords) < 2:
            raise ValueError("InterpolationMap requires at least 2 anchor points")

        # Validate source_coords is monotonically increasing
        if not np.all(np.diff(self.source_coords) > 0):
            raise ValueError("source_coords must be strictly monotonically increasing")

    @property
    def n_anchors(self) -> int:
        """Number of anchor points."""
        return len(self.source_coords)

    @property
    def source_min(self) -> float:
        """Minimum source coordinate."""
        return float(self.source_coords[0])

    @property
    def source_max(self) -> float:
        """Maximum source coordinate."""
        return float(self.source_coords[-1])

    @property
    def target_min(self) -> float:
        """Minimum target coordinate."""
        return float(np.min(self.target_coords))

    @property
    def target_max(self) -> float:
        """Maximum target coordinate."""
        return float(np.max(self.target_coords))

    @property
    def is_invertible(self) -> bool:
        """Whether this map can be inverted.

        True if target_coords are strictly monotonic (increasing or decreasing).
        """
        diff = np.diff(self.target_coords)
        return bool(np.all(diff > 0) or np.all(diff < 0))

    # region Forward/Inverse Conversion

    @staticmethod
    def _interp_with_extrapolation(
        values: float | NDArray[np.floating[Any]],
        xp: NDArray[np.floating[Any]],
        fp: NDArray[np.floating[Any]],
    ) -> float | NDArray[np.floating[Any]]:
        """Interpolate with linear extrapolation outside bounds.

        numpy.interp clips values to the boundary - this method extends
        linearly using the slope at the boundary.

        Args:
            values: Values to interpolate.
            xp: X coordinates (must be increasing).
            fp: Y coordinates.

        Returns:
            Interpolated/extrapolated values.
        """
        values_arr = np.atleast_1d(values)
        result = np.interp(values_arr, xp, fp)

        # Extrapolate below minimum
        below_mask = values_arr < xp[0]
        if np.any(below_mask):
            slope_left = (fp[1] - fp[0]) / (xp[1] - xp[0])
            result[below_mask] = fp[0] + slope_left * (values_arr[below_mask] - xp[0])

        # Extrapolate above maximum
        above_mask = values_arr > xp[-1]
        if np.any(above_mask):
            slope_right = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
            result[above_mask] = fp[-1] + slope_right * (
                values_arr[above_mask] - xp[-1]
            )

        # Return scalar if input was scalar
        if np.isscalar(values):
            return float(result[0])
        return result

    def forward(
        self,
        values: float | NDArray[np.floating[Any]],
    ) -> float | NDArray[np.floating[Any]]:
        """Convert from source to target coordinates.

        Uses numpy.interp for O(log n) lookup with linear interpolation.
        Values outside source range are extrapolated linearly.

        Args:
            values: Source coordinate(s) to convert.

        Returns:
            Target coordinate(s), same shape as input.
        """
        return self._interp_with_extrapolation(
            values, self.source_coords, self.target_coords
        )

    def inverse(
        self,
        values: float | NDArray[np.floating[Any]],
    ) -> float | NDArray[np.floating[Any]]:
        """Convert from target to source coordinates.

        Uses numpy.interp with swapped axes for O(log n) lookup.
        Values outside target range are extrapolated linearly.

        Args:
            values: Target coordinate(s) to convert.

        Returns:
            Source coordinate(s), same shape as input.

        Raises:
            ValueError: If target_coords are not strictly monotonic.
        """
        if not self.is_invertible:
            raise ValueError("Cannot invert: target_coords are not strictly monotonic")

        # If target is decreasing, we need to reverse for interp
        # (interp requires xp to be increasing)
        if self.target_coords[0] > self.target_coords[-1]:
            # Reverse both arrays for interp
            return self._interp_with_extrapolation(
                values,
                self.target_coords[::-1],
                self.source_coords[::-1],
            )
        return self._interp_with_extrapolation(
            values, self.target_coords, self.source_coords
        )

    # endregion

    # region Factory Methods

    @classmethod
    def from_table_map(cls, tmap: "TableMap") -> "InterpolationMap":
        """Create from an existing TableMap.

        This extracts the core interpolation data from a TableMap,
        allowing it to be used in the unified timestamp system.

        Args:
            tmap: The TableMap to convert.

        Returns:
            InterpolationMap with the same anchor points.

        Note:
            Only linear interpolation is preserved. Other interpolation
            kinds (nearest, previous, next) are converted to linear.
        """
        return cls(
            source_coords=tmap.x_values.copy(),
            target_coords=tmap.y_values.copy(),
            source_id=tmap.id,
            target_id=f"{tmap.id}:target",
            source_unit=tmap.source_unit,
            target_unit=tmap.target_unit,
        )

    @classmethod
    def identity(
        cls,
        start: float = 0.0,
        end: float = 1.0,
        timeline_id: str = "identity",
    ) -> "InterpolationMap":
        """Create an identity map (output = input).

        Useful for testing or placeholder mappings.

        Args:
            start: Start coordinate.
            end: End coordinate.
            timeline_id: ID to use for both source and target.

        Returns:
            InterpolationMap where forward(x) == x.
        """
        coords = np.array([start, end], dtype=np.float64)
        return cls(
            source_coords=coords,
            target_coords=coords.copy(),
            source_id=timeline_id,
            target_id=timeline_id,
        )

    # endregion

    # region Display

    def __repr__(self) -> str:
        return (
            f"InterpolationMap(source={self.source_id!r}, target={self.target_id!r}, "
            f"n_anchors={self.n_anchors})"
        )

    def __str__(self) -> str:
        return f"InterpolationMap({self.source_id} -> {self.target_id})"

    # endregion
