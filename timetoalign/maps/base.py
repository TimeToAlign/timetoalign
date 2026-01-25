"""Base classes and protocols for conversion maps.

This module defines the ConversionMap abstract base class that all
map implementations must inherit from.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union

import numpy as np
from numpy.typing import NDArray

from ..core.enums import TimeUnit
from ..core.ids import IdGenerator
from ..core.types import Coordinate, CoordinateValue

if TYPE_CHECKING:
    from typing_extensions import Self

module_logger = logging.getLogger(__name__)

# Type variable for the output type of a map
T = TypeVar("T")

# Input types that maps can accept
MapInput = Union[CoordinateValue, Coordinate, NDArray[np.floating[Any]]]

# Module-level ID generator for maps
_map_id_generator = IdGenerator(scope="map")


def _reset_map_ids() -> None:
    """Reset the module-level ID generator. For testing only."""
    global _map_id_generator
    _map_id_generator = IdGenerator(scope="map")


# region ConversionMap


class ConversionMap(ABC, Generic[T]):
    """Abstract base class for coordinate conversion maps.

    A ConversionMap transforms coordinates from one representation to another.
    Maps are callable and support both scalar and array inputs.

    The key methods are:
    - __call__(value): Convert a single value or array
    - inverse(): Get the inverse map (if invertible)

    Attributes:
        id: Unique identifier for this map instance.
        source_unit: The unit of input coordinates (optional).
        target_unit: The unit of output coordinates (optional).

    Examples:
        >>> # Create a map that doubles values
        >>> linear = LinearMap(scalar=2.0)
        >>> linear(5.0)
        10.0

        >>> # Maps are callable
        >>> linear(np.array([1.0, 2.0, 3.0]))
        array([2., 4., 6.])

        >>> # Get the inverse
        >>> inv = linear.inverse()
        >>> inv(10.0)
        5.0
    """

    # Class-level attributes that subclasses may override
    _default_source_unit: TimeUnit | None = None
    _default_target_unit: TimeUnit | None = None

    def __init__(
        self,
        *,
        source_unit: TimeUnit | str | None = None,
        target_unit: TimeUnit | str | None = None,
        uid: str | None = None,
    ) -> None:
        """Initialize a ConversionMap.

        Args:
            source_unit: The unit of input coordinates. Defaults to class default.
            target_unit: The unit of output coordinates. Defaults to class default.
            uid: Optional explicit ID. If None, auto-generated.
        """
        # Generate or use provided ID
        if uid is not None:
            self._id = uid
        else:
            self._id = _map_id_generator.create(type_hint=self.__class__.__name__)

        # Set units
        if source_unit is not None:
            self._source_unit = TimeUnit(source_unit)
        else:
            self._source_unit = self._default_source_unit

        if target_unit is not None:
            self._target_unit = TimeUnit(target_unit)
        else:
            self._target_unit = self._default_target_unit

        self._logger = module_logger.getChild(self.__class__.__name__)

    @property
    def id(self) -> str:
        """Unique identifier for this map."""
        return self._id

    @property
    def source_unit(self) -> TimeUnit | None:
        """The unit of input coordinates, if specified."""
        return self._source_unit

    @property
    def target_unit(self) -> TimeUnit | None:
        """The unit of output coordinates, if specified."""
        return self._target_unit

    @property
    def is_invertible(self) -> bool:
        """Whether this map has a well-defined inverse.

        Subclasses should override if they are not invertible.
        """
        return True

    # region Conversion methods

    def __call__(
        self,
        value: MapInput,
        **kwargs: Any,
    ) -> T | NDArray[Any]:
        """Convert a value or array of values.

        This is the primary interface for using a map.

        Args:
            value: A scalar, Coordinate, or numpy array.
            **kwargs: Additional arguments passed to _convert_scalar or _convert_array.

        Returns:
            The converted value(s), matching input shape.

        Raises:
            ValueError: If the input Coordinate has an incompatible unit.
        """
        # Handle Coordinate input
        if isinstance(value, Coordinate):
            if self._source_unit is not None and value.unit != self._source_unit:
                raise ValueError(
                    f"Coordinate unit {value.unit} does not match "
                    f"map source unit {self._source_unit}"
                )
            return self._convert_scalar(value.value, **kwargs)

        # Handle array input
        if isinstance(value, np.ndarray):
            return self._convert_array(value, **kwargs)

        # Handle scalar input
        return self._convert_scalar(value, **kwargs)

    @abstractmethod
    def _convert_scalar(self, value: CoordinateValue, **kwargs: Any) -> T:
        """Convert a single scalar value.

        Args:
            value: The numeric value to convert.
            **kwargs: Subclass-specific arguments.

        Returns:
            The converted value.
        """
        ...

    def _convert_array(self, values: NDArray[Any], **kwargs: Any) -> NDArray[Any]:
        """Convert an array of values.

        Default implementation uses vectorized scalar conversion.
        Subclasses may override for efficiency.

        Args:
            values: Array of values to convert.
            **kwargs: Subclass-specific arguments.

        Returns:
            Array of converted values.
        """
        # Default: vectorize the scalar conversion
        vec_convert = np.vectorize(lambda x: self._convert_scalar(x, **kwargs))
        return vec_convert(values)

    # endregion

    # region Inverse

    @abstractmethod
    def inverse(self) -> Self:
        """Return the inverse of this map.

        Returns:
            A new ConversionMap that reverses this transformation.

        Raises:
            NotImplementedError: If the map is not invertible.
        """
        ...

    # endregion

    # region Composition

    def then(self, other: ConversionMap[Any]) -> ConversionMap[Any]:
        """Compose this map with another (this first, then other).

        Args:
            other: The map to apply after this one.

        Returns:
            A ChainMap that applies both maps in sequence.
        """
        # Import here to avoid circular imports
        from .composite import ChainMap

        return ChainMap([self, other])

    def __rshift__(self, other: ConversionMap[Any]) -> ConversionMap[Any]:
        """Compose maps using >> operator (self >> other)."""
        return self.then(other)

    # endregion

    # region Serialization

    def to_dict(self) -> dict[str, Any]:
        """Serialize the map to a dictionary.

        Subclasses should call super().to_dict() and add their parameters.

        Returns:
            Dictionary representation of the map.
        """
        return {
            "type": self.__class__.__name__,
            "id": self._id,
            "source_unit": self._source_unit.name if self._source_unit else None,
            "target_unit": self._target_unit.name if self._target_unit else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversionMap[Any]:
        """Deserialize a map from a dictionary.

        Args:
            data: Dictionary representation.

        Returns:
            A ConversionMap instance.

        Raises:
            ValueError: If the type is unknown.
        """
        map_type = data.get("type")
        if map_type is None:
            raise ValueError("Map dictionary must include 'type'")

        # Import all map types for dispatch
        from .composite import ChainMap, PiecewiseMap
        from .linear import LinearMap, ScalarMap, ShiftMap
        from .table import TableMap

        type_map = {
            "LinearMap": LinearMap,
            "ScalarMap": ScalarMap,
            "ShiftMap": ShiftMap,
            "TableMap": TableMap,
            "ChainMap": ChainMap,
            "PiecewiseMap": PiecewiseMap,
        }

        if map_type not in type_map:
            raise ValueError(f"Unknown map type: {map_type}")

        return type_map[map_type].from_dict(data)

    # endregion

    # region Display

    def __repr__(self) -> str:
        parts = [f"id={self._id!r}"]
        if self._source_unit:
            parts.append(f"source_unit={self._source_unit}")
        if self._target_unit:
            parts.append(f"target_unit={self._target_unit}")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        if self._source_unit and self._target_unit:
            return (
                f"{self.__class__.__name__}({self._source_unit} -> {self._target_unit})"
            )
        return f"{self.__class__.__name__}({self._id})"

    # endregion

    # region Equality

    def __eq__(self, other: object) -> bool:
        """Two maps are equal if they have the same type and parameters."""
        if not isinstance(other, ConversionMap):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __hash__(self) -> int:
        """Hash based on the map's ID."""
        return hash(self._id)

    # endregion


# endregion
