from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.python_units import extract_python_units
from scripts.dupscore.models import CloneUnit
from tests.unit.scripts.dupscore._helpers.clones.python_units._test_types import (
    PythonKeyTestCase,
    PythonUnitsTestCase,
)

_LAYOUT_SOURCE: str = """\
import functools


@functools.cache
def load_orders(path):
    def parse(line):
        return line.split(",")
    return [parse(line) for line in open(path)]


class Warehouse:
    class Shelf:
        def label(self):
            return "shelf"

    async def restock(self, count):
        return count + 1


if True:
    def conditional_helper():
        return None
"""


@pytest.mark.parametrize(
    "test_case",
    [
        PythonUnitsTestCase(
            description="functions, nested class methods, and conditional defs are units",
            source=_LAYOUT_SOURCE,
            expected_units=(
                ("load_orders", 5, 8),
                ("Warehouse.Shelf.label", 13, 14),
                ("Warehouse.restock", 16, 17),
                ("conditional_helper", 21, 22),
            ),
        ),
        PythonUnitsTestCase(
            description="unparseable source yields no units",
            source="def broken(:\n    pass\n",
            expected_units=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_source_when_extracting_units_then_returns_expected_units(
    test_case: PythonUnitsTestCase,
) -> None:
    units: tuple[CloneUnit, ...] = extract_python_units(
        relative_path="src/sqlbuild/demo.py", source=test_case.source
    )

    assert (
        tuple((unit.name, unit.start_line, unit.end_line) for unit in units)
        == test_case.expected_units
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonKeyTestCase(
            description="keyword-only markers and defaults still change identity",
            left_source='def f(a, b):\n    """Doc."""\n    total = a + b  # sum\n    return total\n',
            right_source=(
                "def f(a: int, *, b: int = 0) -> int:\n    total: int = a + b\n    return total\n"
            ),
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
        PythonKeyTestCase(
            description="annotations and docstring only differences are exact",
            left_source='def f(a, b):\n    """Doc."""\n    total = a + b  # sum\n    return total\n',
            right_source=(
                "def f(a: int, b: list[int]) -> int:\n    total: int = a + b\n    return total\n"
            ),
            expected_same_concrete=True,
            expected_same_normalized=True,
        ),
        PythonKeyTestCase(
            description="renamed identifiers and literals share the normalised stream",
            left_source='def f(a):\n    return g(a, "x", 1)\n',
            right_source='def other(value):\n    return h(value, "y", 2)\n',
            expected_same_concrete=False,
            expected_same_normalized=True,
        ),
        PythonKeyTestCase(
            description="different literal kinds keep distinct placeholders",
            left_source='def f(a):\n    return g(a, "x")\n',
            right_source="def f(a):\n    return g(a, 1)\n",
            expected_same_concrete=False,
            expected_same_normalized=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_functions_when_extracting_then_identity_keys_reflect_normalisation(
    test_case: PythonKeyTestCase,
) -> None:
    left: CloneUnit = extract_python_units(relative_path="a.py", source=test_case.left_source)[0]
    right: CloneUnit = extract_python_units(relative_path="b.py", source=test_case.right_source)[0]

    assert (left.concrete_key == right.concrete_key) is test_case.expected_same_concrete
    assert (left.normalized_key == right.normalized_key) is test_case.expected_same_normalized
