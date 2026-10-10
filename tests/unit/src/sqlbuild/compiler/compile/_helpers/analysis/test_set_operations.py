from __future__ import annotations

import random
import re

import pytest

from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import names_set_operation
from tests.unit.src.sqlbuild.compiler.compile._helpers.analysis._test_types import (
    SetOperationSearchTestCase,
)

_PYTHON_SEARCH: re.Pattern[str] = re.compile(r"\b(?:UNION|INTERSECT|EXCEPT)\b", re.IGNORECASE)
_PIECES: tuple[str, ...] = (
    "SELECT order_id FROM orders",
    " union ",
    " UNION ALL ",
    " Intersect ",
    " except ",
    "_union",
    "unions",
    "\u0131ntersect",
    "\u0130NTERSECT",
    "INTER\u017fECT",
    "EXCEPT\u00df",
    "\u0149union",
    "\u00e9except",
    "union\u0301",
    " customers ",
    "\n",
    "\u0130",
    "\u017f",
    "-- intersect\n",
)


@pytest.mark.parametrize(
    "test_case",
    [
        SetOperationSearchTestCase(
            description="keywords in every case, with folding and boundary characters",
            seed=20261010,
            count=4000,
            expected_minimum_matches=1000,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_searching_set_operations_then_matches_python_search(
    test_case: SetOperationSearchTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [
        "".join(rng.choices(_PIECES, k=rng.randint(1, 6))) for _ in range(test_case.count)
    ]
    expected: list[bool] = [_PYTHON_SEARCH.search(sql) is not None for sql in sqls]

    assert [names_set_operation(sql) for sql in sqls] == expected
    assert sum(expected) >= test_case.expected_minimum_matches


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
