"""Shared validation and projection for coordinate-retrieval APIs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence, Set
from fractions import Fraction
from typing import Literal, TypeAlias

import numpy as np
import pandas as pd

from .enums import NumberType, TimeUnit
from .time import Coordinate, IdCoordinate

CoordinateInput: TypeAlias = int | float | Fraction | Coordinate | IdCoordinate
CoordinateCollection: TypeAlias = (
    Sequence[CoordinateInput] | np.ndarray | pd.Index | pd.Series
)
KeyCollection: TypeAlias = Sequence[str] | pd.Index | pd.Series
CoordinateResult: TypeAlias = IdCoordinate | Coordinate | float | int | Fraction
CoordinateFormat: TypeAlias = Literal[
    "id_coordinate", "coordinate", "float", "int", "fraction", "series"
]
Rounding: TypeAlias = Literal["round", "floor", "ceil", "truncate"]

COORDINATE_FORMATS: tuple[str, ...] = (
    "id_coordinate",
    "coordinate",
    "float",
    "int",
    "fraction",
    "series",
)
ROUNDING_MODES: tuple[str, ...] = ("round", "floor", "ceil", "truncate")


def number_type_for_converted_unit(preferred: NumberType, unit: TimeUnit) -> NumberType:
    """Return a valid canonical type for a converted unit coordinate.

    Args:
        preferred: Number type declared by the selected timeline axis.
        unit: Unit requested for the converted representation.

    Returns:
        The preferred type when the target unit admits it, otherwise the
        target unit's default type.
    """
    if preferred in unit.allowed_number_types:
        return preferred
    return unit.default_number_type


def validate_retrieval_options(format: str, rounding: str) -> None:
    """Validate the closed output-format and rounding vocabularies.

    Args:
        format: Requested coordinate output format.
        rounding: Integral projection mode.

    Raises:
        ValueError: If either option is outside its closed vocabulary.
    """
    if format not in COORDINATE_FORMATS:
        raise ValueError(
            f"Unknown coordinate format {format!r}. Use one of "
            f"{', '.join(COORDINATE_FORMATS)}."
        )
    if rounding not in ROUNDING_MODES:
        raise ValueError(
            f"Unknown rounding mode {rounding!r}. Use one of "
            f"{', '.join(ROUNDING_MODES)}."
        )


def is_coordinate_input(value: object) -> bool:
    """Return whether *value* is one accepted scalar coordinate input."""
    return not isinstance(value, bool) and isinstance(
        value, (int, float, Fraction, Coordinate)
    )


def collection_values(value: object) -> tuple[list[object], pd.Index | None]:
    """Validate and eagerly materialize one accepted one-dimensional collection.

    Args:
        value: Candidate coordinate or key collection.

    Returns:
        Materialized values and a pandas index to preserve, when supplied.

    Raises:
        TypeError: If the value is not an accepted finite, one-dimensional
            collection.
    """
    if isinstance(value, (str, bytes, bytearray, Mapping, Set, Iterator)):
        raise TypeError(
            f"Unsupported collection type: {type(value).__name__}; expected a "
            "finite one-dimensional sequence, NumPy array, pandas Index, or Series"
        )
    if isinstance(value, pd.Series):
        return [_python_numeric(item) for item in value.array], value.index
    if isinstance(value, pd.Index):
        return [_python_numeric(item) for item in value], value
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise TypeError("NumPy coordinate collections must be one-dimensional")
        if value.dtype.kind not in "biufO":
            raise TypeError(
                f"Unsupported NumPy dtype {value.dtype}; expected numeric or object"
            )
        return [_python_numeric(item) for item in value], None
    if isinstance(value, Sequence):
        return list(value), None
    raise TypeError(
        f"Unsupported collection type: {type(value).__name__}; expected a "
        "finite one-dimensional sequence, NumPy array, pandas Index, or Series"
    )


def _python_numeric(value: object) -> object:
    """Normalize a NumPy scalar to the corresponding Python scalar."""
    return value.item() if isinstance(value, np.generic) else value


def validate_coordinate_collection(
    value: object,
) -> tuple[list[CoordinateInput], pd.Index | None]:
    """Validate a plural coordinate input atomically and preserve pandas index.

    Args:
        value: Candidate collection.

    Returns:
        Coordinate inputs and optional preserved pandas index.

    Raises:
        TypeError: If any element is not a scalar coordinate input.
    """
    values, index = collection_values(value)
    for position, item in enumerate(values):
        if not is_coordinate_input(item):
            raise TypeError(
                f"Coordinate collection element {position} has unsupported type "
                f"{type(item).__name__}"
            )
    return values, index  # type: ignore[return-value]


def validate_key_collection(value: object) -> tuple[list[str], pd.Index | None]:
    """Validate a plural key input atomically and preserve pandas index.

    Args:
        value: Candidate key collection.

    Returns:
        String keys and optional preserved pandas index.

    Raises:
        TypeError: If any element is not a string.
    """
    values, index = collection_values(value)
    for position, item in enumerate(values):
        if not isinstance(item, str):
            raise TypeError(
                f"Key collection element {position} has unsupported type "
                f"{type(item).__name__}"
            )
    return values, index  # type: ignore[return-value]


def classify_dispatch_input(value: object, *, empty_is_keys: bool = False) -> str:
    """Classify a dispatcher input as scalar/plural coordinate or key input.

    Args:
        value: Dispatcher input.
        empty_is_keys: Route an empty collection to the key branch.

    Returns:
        One of ``"coordinate"``, ``"coordinates"``, ``"key"``, or
        ``"keys"``.

    Raises:
        TypeError: If the runtime form is unsupported or mixes key and
            coordinate elements.
    """
    if isinstance(value, str):
        return "key"
    if is_coordinate_input(value):
        return "coordinate"
    values, _ = collection_values(value)
    if not values:
        return "keys" if empty_is_keys else "coordinates"
    are_keys = [isinstance(item, str) for item in values]
    are_coordinates = [is_coordinate_input(item) for item in values]
    if all(are_keys):
        return "keys"
    if all(are_coordinates):
        return "coordinates"
    raise TypeError(
        "Dispatcher collections must contain only string keys or only coordinate inputs"
    )


def _series_from_coordinates(
    coordinates: Sequence[IdCoordinate],
    *,
    index: pd.Index | None,
    name: str,
    empty_number_type: NumberType | None,
) -> pd.Series:
    """Build the canonical numeric pandas view for coordinate results."""
    values = [coordinate.value for coordinate in coordinates]
    result_index = index if index is not None else pd.RangeIndex(len(values))
    if not values:
        if empty_number_type is NumberType.float:
            dtype: str | type[object] = "float64"
        elif empty_number_type is NumberType.int:
            dtype = "int64"
        else:
            dtype = object
        return pd.Series(values, index=result_index, name=name, dtype=dtype)
    axes = {coordinate.timeline_id for coordinate in coordinates}
    if len(axes) != 1:
        return pd.Series(values, index=result_index, name=name, dtype=object)
    kinds = {coordinate.number_type for coordinate in coordinates}
    if len(kinds) != 1:
        return pd.Series(values, index=result_index, name=name, dtype=object)
    kind = coordinates[0].number_type.name
    if kind == "fraction":
        return pd.Series(values, index=result_index, name=name, dtype=object)
    if kind == "float":
        return pd.Series(values, index=result_index, name=name, dtype="float64")
    try:
        return pd.Series(values, index=result_index, name=name, dtype="int64")
    except OverflowError:
        return pd.Series(values, index=result_index, name=name, dtype=object)


def format_coordinates(
    coordinates: Sequence[IdCoordinate],
    *,
    format: CoordinateFormat = "id_coordinate",
    rounding: Rounding = "round",
    scalar: bool,
    index: pd.Index | None = None,
    series_name: str | None = None,
    empty_number_type: NumberType | None = None,
) -> CoordinateResult | list[CoordinateResult] | pd.Series:
    """Project canonical ID coordinates into one requested public format.

    Args:
        coordinates: Canonical result coordinates.
        format: Requested output format.
        rounding: Integral projection mode.
        scalar: Whether the caller supplied a scalar query.
        index: Optional pandas index to preserve.
        series_name: Required Series name; defaults to the sole result axis.
        empty_number_type: Declared axis representation for an empty Series.

    Returns:
        One scalar, a list of scalar leaves, or a pandas Series.

    Raises:
        ValueError: If an option is invalid or a scalar result does not have
            exactly one coordinate.
    """
    validate_retrieval_options(format, rounding)
    if scalar and len(coordinates) != 1:
        raise ValueError("A scalar coordinate query must resolve exactly one result")
    if format == "series":
        name = series_name
        if name is None:
            name = coordinates[0].timeline_id if coordinates else "coordinate"
        return _series_from_coordinates(
            coordinates,
            index=index,
            name=name,
            empty_number_type=empty_number_type,
        )

    def project(coordinate: IdCoordinate) -> CoordinateResult:
        if format == "id_coordinate":
            return coordinate
        if format == "coordinate":
            return Coordinate(
                coordinate.value,
                coordinate.unit,
                number_type=coordinate.number_type,
            )
        if format == "float":
            return coordinate.to_float()
        if format == "int":
            return coordinate.to_int(rounding)
        return coordinate.to_fraction()

    projected = [project(coordinate) for coordinate in coordinates]
    return projected[0] if scalar else projected


def coordinate_wire_entry(coordinate: Coordinate) -> dict[str, object]:
    """Serialize one canonical coordinate as the v2 rational wire entry.

    Args:
        coordinate: Coordinate to serialize.

    Returns:
        A typed coordinate wire dictionary.
    """
    value = coordinate.value
    numerator: int | None = None
    denominator: int | None = None
    if isinstance(value, Fraction):
        numerator = value.numerator
        denominator = value.denominator
    return {
        "value": float(value),
        "numerator": numerator,
        "denominator": denominator,
        "unit": coordinate.unit.value,
        "number_type": coordinate.number_type.name,
    }
