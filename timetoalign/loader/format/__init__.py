"""Format loader sub-package for TimeToAlign!

This sub-package contains loaders for generic file formats (JSON, XML, etc.)
that are configurable via field mapping. These loaders parse structure rather
than music-specific semantics, serving as base classes for domain-specific
subclasses.

Loaders:
    JsonLoader: Configurable JSON loader that normalises nested structures
        into flat PyArrow tables (one row per principal object).
"""

from __future__ import annotations

from .json import JsonLoader

__all__ = [
    "JsonLoader",
]
