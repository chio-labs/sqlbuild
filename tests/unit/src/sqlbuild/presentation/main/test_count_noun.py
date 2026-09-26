from __future__ import annotations

import pytest

from sqlbuild.presentation.main.count_noun import format_count_noun
from tests.unit.src.sqlbuild.presentation.main._test_types import CountNounTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        CountNounTestCase("one uses the singular", 1, "relation", None, "1 relation"),
        CountNounTestCase("zero uses the plural", 0, "object", None, "0 objects"),
        CountNounTestCase("many uses the plural", 3, "state item", None, "3 state items"),
        CountNounTestCase("irregular plural for many", 2, "match", "matches", "2 matches"),
        CountNounTestCase("irregular noun for one", 1, "child", "children", "1 child"),
    ),
    ids=lambda case: case.description,
)
def test_given_count_when_formatting_noun_then_uses_singular_only_for_one(
    test_case: CountNounTestCase,
) -> None:
    assert (
        format_count_noun(
            count=test_case.count, singular=test_case.singular, plural=test_case.plural
        )
        == test_case.expected_text
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
