from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    PolyglotDefaultGuardTestCase,
    PolyglotExplicitGuardTestCase,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis.main.helpers import nested_coalesce_sql


@pytest.mark.parametrize(
    "test_case",
    (
        PolyglotDefaultGuardTestCase(
            description="trusted SQL exceeds the defensive default",
            function_depth=65,
            expected_kind="select",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_deep_trusted_sql_when_parsing_then_sqlbuild_uses_bounded_budget(
    test_case: PolyglotDefaultGuardTestCase,
) -> None:
    polyglot_module: Any = import_polyglot_sql()

    parsed: Any = polyglot_module.parse_one(
        nested_coalesce_sql(function_depth=test_case.function_depth),
        dialect="snowflake",
    )

    assert parsed.kind == test_case.expected_kind


@pytest.mark.parametrize(
    "test_case",
    (
        PolyglotExplicitGuardTestCase(
            description="caller retains the defensive default",
            function_depth=65,
            maximum_function_depth=64,
            expected_error_pattern="FUNCTION_NESTING_DEPTH_EXCEEDED",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_explicit_guard_when_parsing_then_caller_budget_is_preserved(
    test_case: PolyglotExplicitGuardTestCase,
) -> None:
    polyglot_module: Any = import_polyglot_sql()

    with pytest.raises(polyglot_module.ParseError, match=test_case.expected_error_pattern):
        polyglot_module.parse_one(
            nested_coalesce_sql(function_depth=test_case.function_depth),
            dialect="snowflake",
            complexity_guard={"maxFunctionCallDepth": test_case.maximum_function_depth},
        )


@pytest.mark.parametrize(
    "test_case",
    (
        PolyglotExplicitGuardTestCase(
            description="analysis options retain the caller guard",
            function_depth=65,
            maximum_function_depth=64,
            expected_error_pattern="FUNCTION_NESTING_DEPTH_EXCEEDED",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_options_guard_when_analyzing_then_caller_budget_is_preserved(
    test_case: PolyglotExplicitGuardTestCase,
) -> None:
    polyglot_module: Any = import_polyglot_sql()

    with pytest.raises(polyglot_module.ParseError, match=test_case.expected_error_pattern):
        polyglot_module.analyze_query(
            nested_coalesce_sql(function_depth=test_case.function_depth),
            {
                "dialect": "snowflake",
                "complexityGuard": {
                    "maxFunctionCallDepth": test_case.maximum_function_depth,
                },
            },
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
