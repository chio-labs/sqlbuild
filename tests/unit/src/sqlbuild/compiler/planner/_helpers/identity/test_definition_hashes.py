"""Unit tests for planner definition fingerprints that name failing resources."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.identity.hashing import (
    function_definition_hash,
    model_definition_hash,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from tests.unit.src.sqlbuild.compiler.planner._helpers.identity._test_types import (
    DefinitionHashFailureTestCase,
)

_UNTOKENIZABLE_SQL: str = "SELECT 'open FROM orders"


@pytest.mark.parametrize(
    "test_case",
    [DefinitionHashFailureTestCase("model", "Model 'orders' SQL cannot be fingerprinted", "S025")],
    ids=lambda case: case.description,
)
def test_given_untokenizable_model_when_hashing_then_planning_error_names_model(
    test_case: DefinitionHashFailureTestCase,
) -> None:
    with pytest.raises(PlannerInputError, match=test_case.expected_message) as raised:
        _ = model_definition_hash(
            model_name="orders", query_sql=_UNTOKENIZABLE_SQL, dialect="duckdb"
        )

    assert raised.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        DefinitionHashFailureTestCase(
            "SQL function", "Function 'is_open' cannot be fingerprinted", "S025"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_untokenizable_sql_function_when_hashing_then_planning_error_names_function(
    test_case: DefinitionHashFailureTestCase,
) -> None:
    with pytest.raises(PlannerInputError, match=test_case.expected_message) as raised:
        _ = function_definition_hash(
            function_name="is_open",
            fingerprint_sql=_UNTOKENIZABLE_SQL,
            language="sql",
            dialect="duckdb",
        )

    assert raised.value.code == test_case.expected_code
