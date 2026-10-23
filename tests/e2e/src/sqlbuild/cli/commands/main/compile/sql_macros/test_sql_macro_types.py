"""E2E coverage for ANY SQL macro arguments."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros._test_types import (
    SqlMacroBuildTestCase,
    SqlMacroErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros.helpers import (
    DATABASE,
    orders_model,
    output,
    run_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb

_ORDER_KEY: dict[str, str] = {
    "macros/sql/order_key.sql": (
        'MACRO (\n  description "Order key from the country and the order",\n'
        "  arguments (country_code VARCHAR, order_ref ANY),\n"
        "  returns VARCHAR,\n);\n\n"
        "@country_code || '::' || CAST(@order_ref AS VARCHAR)\n"
    )
}


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroBuildTestCase(
            description="any_argument_takes_a_number_a_string_and_an_expression",
            files={
                **_ORDER_KEY,
                **orders_model(
                    "SELECT order_id,\n"
                    "  @sql.order_key(country_code, order_id) AS by_number,\n"
                    "  @sql.order_key(country_code, status) AS by_text,\n"
                    "  @sql.order_key(country_code, amount_cents / 100) AS by_expression\n"
                    'FROM __ref("stg_orders")\nWHERE order_id = 2\n'
                ),
            },
            query="SELECT by_number, by_text, by_expression FROM orders",
            expected_rows=[("FR::2", "FR::closed", "FR::5.0")],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_any_argument_when_building_then_callers_pass_values_of_any_type(
    test_case: SqlMacroBuildTestCase, tmp_path: Path
) -> None:
    project_dir, result = run_project(tmp_path=tmp_path, files=test_case.files, command=("build",))

    assert result.returncode == 0, output(result)
    assert "P017" not in output(result)
    assert (
        query_duckdb(db_path=project_dir / DATABASE, sql=test_case.query) == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroErrorTestCase(
            description="a_list_passed_to_an_any_argument",
            files={
                **_ORDER_KEY,
                **orders_model(
                    'SELECT @sql.order_key(country_code, [1, 2]) AS k FROM __ref("stg_orders")\n'
                ),
            },
            expected_code="P017",
            expected_fragments=(
                "argument order_ref of macro order_key() expects ANY: a scalar SQL expression",
            ),
        ),
        SqlMacroErrorTestCase(
            description="any_with_const",
            files={
                "macros/sql/order_key.sql": (
                    'MACRO (description "Key", arguments (order_ref ANY CONST), '
                    "returns VARCHAR);\n\nCAST(@order_ref AS VARCHAR)\n"
                ),
                **orders_model('SELECT @sql.order_key(1) AS k FROM __ref("stg_orders")\n'),
            },
            expected_code="P015",
            expected_fragments=(
                "argument order_ref ANY CONST: a CONST argument needs a type its values are "
                "checked against",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_any_argument_misused_when_compiling_then_it_fails(
    test_case: SqlMacroErrorTestCase, tmp_path: Path
) -> None:
    _, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=("compile", "--no-cache")
    )

    assert result.returncode == 1, output(result)
    assert f"error[{test_case.expected_code}]" in output(result)
    for fragment in test_case.expected_fragments:
        assert fragment in output(result)
