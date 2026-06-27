from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.sqlbuild_model_selectors import (
    resolve_sqlbuild_model_selector_names,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    SqlbuildModelSelectorNamesTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.helpers import (
    build_sqlbuild_model_selector_project,
)

TEST_CASES: list[SqlbuildModelSelectorNamesTestCase] = [
    SqlbuildModelSelectorNamesTestCase(
        description="resolves model name selector",
        term="fact_orders",
        expected_model_names=("fact_orders",),
        expected_translation=None,
    ),
    SqlbuildModelSelectorNamesTestCase(
        description="resolves tag selector",
        term="tag:nightly",
        expected_model_names=("fact_orders", "dim_customers"),
        expected_translation=None,
    ),
    SqlbuildModelSelectorNamesTestCase(
        description="resolves path selector",
        term="path:models/marts",
        expected_model_names=("fact_orders", "dim_customers"),
        expected_translation=None,
    ),
    SqlbuildModelSelectorNamesTestCase(
        description="translates backslash path selector",
        term="path:models\\marts",
        expected_model_names=("fact_orders", "dim_customers"),
        expected_translation="path:models/marts",
    ),
    SqlbuildModelSelectorNamesTestCase(
        description="unknown selector resolves empty",
        term="state:modified",
        expected_model_names=(),
        expected_translation=None,
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_sqlbuild_model_selector_when_resolving_names_then_returns_expected_names(
    test_case: SqlbuildModelSelectorNamesTestCase,
) -> None:
    model_names, translation = resolve_sqlbuild_model_selector_names(
        project=build_sqlbuild_model_selector_project(),
        term=test_case.term,
    )

    assert model_names == test_case.expected_model_names
    assert translation == test_case.expected_translation
