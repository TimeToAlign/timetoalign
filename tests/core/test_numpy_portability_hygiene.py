"""Tests for numpy portability hygiene across the package.

Validation logic is documented in ``tests/core/README.md`` under
"test_numpy_portability_hygiene.py".
"""

from __future__ import annotations

import ast
from pathlib import Path

import timetoalign

PACKAGE_ROOT = Path(timetoalign.__file__).parent

# numpy functions taking an integer *argument* bound to a C type rather than
# to a numpy width, so that which loops exist depends on the platform.
# ``ldexp`` is the one such function this library has ever reached for: its
# exponent is offered as ``'di->d'`` and ``'dl->d'``, so an int64 exponent
# binds where a C long is 64 bits and finds no loop at all where it is 32.
#
# ``frexp`` is deliberately absent: its exponent is an *output*, always a C
# int, and reading a 32-bit integer out is not a portability question.
C_TYPED_ARGUMENT_FUNCTIONS = frozenset({"ldexp"})

# numpy aliases for whichever integer the platform's C ABI calls native.  An
# explicit width (``np.int64``, ``np.int32``) says what it means everywhere;
# these say something different on Windows than on Linux.
PLATFORM_WIDTH_ALIASES = frozenset({"int_", "long", "ulong", "intc", "uintc"})

NUMPY_NAMES = frozenset({"np", "numpy"})


def _is_numpy(node: ast.expr) -> bool:
    """Whether *node* is the numpy module as this package imports it."""
    return isinstance(node, ast.Name) and node.id in NUMPY_NAMES


def _names_builtin_int(node: ast.expr) -> bool:
    """Whether *node* spells the builtin ``int`` as a dtype."""
    return (isinstance(node, ast.Name) and node.id == "int") or (
        isinstance(node, ast.Constant) and node.value == "int"
    )


def _offences(tree: ast.AST) -> list[tuple[int, str]]:
    """Return every platform-dependent numpy construct in one parsed module."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _is_numpy(node.value):
            if node.attr in C_TYPED_ARGUMENT_FUNCTIONS:
                found.append((node.lineno, f"np.{node.attr}"))
            elif node.attr in PLATFORM_WIDTH_ALIASES:
                found.append((node.lineno, f"np.{node.attr}"))
        elif isinstance(node, ast.keyword):
            if node.arg == "dtype" and _names_builtin_int(node.value):
                found.append((node.lineno, "dtype=int"))
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "astype"
                and node.args
                and _names_builtin_int(node.args[0])
            ):
                found.append((node.lineno, "astype(int)"))
    # ``ast.walk`` is breadth-first; report in source order so a failure reads
    # like a file rather than like a tree traversal.
    return sorted(found)


def test_no_platform_dependent_numpy_constructs() -> None:
    """The library's integer widths are its own choice, not the platform's.

    Storage here is exact: an int64 numerator means 64 bits of numerator
    wherever the package runs. That holds only while every width in the code
    is stated outright. The constructs below each hand the choice to the C
    ABI instead — silently, and identically on every machine the developers
    own, which is what makes them worth a test rather than a review habit.

    A new use is not necessarily wrong, but it is a decision: make the width
    explicit, or scale by a value instead of by an exponent, and if neither
    applies, say so here and in ``tests/conftest.py`` so that
    ``platform_contract`` can emulate the platform being relied on.
    """
    offences: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offences.extend(
            f"{path.relative_to(PACKAGE_ROOT)}:{line}: {construct}"
            for line, construct in _offences(tree)
        )

    assert offences == []


def test_the_scan_recognises_each_construct() -> None:
    """A hygiene test that cannot fail is not a hygiene test.

    Every pattern is exercised against a source snippet that contains it, so
    that a scan quietly stopping to match anything shows up here rather than
    as a permanently green suite.
    """
    source = "\n".join(
        [
            "import numpy as np",
            "a = np.ldexp(values, shift)",
            "c = np.int_(3)",
            "d = np.long(3)",
            "e = np.intc(3)",
            "f = np.array([1], dtype=int)",
            "g = values.astype(int)",
            "h = values.astype('int')",
        ]
    )

    assert [construct for _, construct in _offences(ast.parse(source))] == [
        "np.ldexp",
        "np.int_",
        "np.long",
        "np.intc",
        "dtype=int",
        "astype(int)",
        "astype(int)",
    ]


def test_explicit_widths_are_not_flagged() -> None:
    """The scan must leave the spellings it is asking for alone."""
    source = "\n".join(
        [
            "import numpy as np",
            "a = np.int64(1) << shift",
            "b = values.astype(np.int64)",
            "c = np.array([1], dtype=np.int32)",
            "d = np.rint(values * denominator.astype(np.float64))",
            "e = int(value)",
            "f = np.minimum(low, high)",
            "g = np.frexp(values)",
        ]
    )

    assert _offences(ast.parse(source)) == []
