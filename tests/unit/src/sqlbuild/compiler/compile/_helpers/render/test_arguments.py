from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.render.arguments import render_parameterized_sql
from sqlbuild.compiler.compile.exceptions import CompileInputError
from tests.unit.src.sqlbuild.compiler.compile._helpers.render._test_types import (
    ParameterizedSqlRenderErrorTestCase,
    ParameterizedSqlRenderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlRenderTestCase(
            description="renders raw and quoted values with SQL semantics",
            sql="SELECT @relation, @'role', @enabled, @limit, @missing, @'values'",
            arguments={
                "relation": "analytics.orders",
                "role": "O'Brien",
                "enabled": True,
                "limit": 3,
                "missing": None,
                "values": ["reader", "writer"],
            },
            expected_sql=("SELECT analytics.orders, 'O''Brien', TRUE, 3, NULL, 'reader', 'writer'"),
        ),
        ParameterizedSqlRenderTestCase(
            description="preserves macro and declaration calls",
            sql='SELECT @grant_select(), @enum("role").ADMIN, @const("limit")',
            arguments={},
            expected_sql='SELECT @grant_select(), @enum("role").ADMIN, @const("limit")',
        ),
        ParameterizedSqlRenderTestCase(
            description="does not rescan rendered quoted values as raw arguments",
            sql="SELECT @'email'",
            arguments={"email": "O'Brien@example.com"},
            expected_sql="SELECT 'O''Brien@example.com'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_arguments_when_rendering_then_returns_expected_sql(
    test_case: ParameterizedSqlRenderTestCase,
) -> None:
    rendered: str = render_parameterized_sql(
        sql=test_case.sql,
        arguments=test_case.arguments,
        owner_label="models/orders.sql post_hooks[0]",
        definition_label="SQL hook 'grant_access'",
        reject_unused=True,
    )

    assert rendered == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlRenderErrorTestCase(
            description="rejects missing argument",
            sql="SELECT @role",
            arguments={},
            expected_error_fragment="missing argument 'role'",
        ),
        ParameterizedSqlRenderErrorTestCase(
            description="rejects unused argument",
            sql="SELECT 1",
            arguments={"unused": "value"},
            expected_error_fragment=r"unknown argument\(s\).*unused",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_arguments_when_rendering_then_raises(
    test_case: ParameterizedSqlRenderErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        render_parameterized_sql(
            sql=test_case.sql,
            arguments=test_case.arguments,
            owner_label="models/orders.sql post_hooks[0]",
            definition_label="SQL hook 'grant_access'",
            reject_unused=True,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
