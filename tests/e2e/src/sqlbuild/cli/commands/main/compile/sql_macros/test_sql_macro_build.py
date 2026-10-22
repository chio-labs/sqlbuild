"""E2E coverage for building, formatting and inspecting models that call SQL macros."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros._test_types import (
    SqlMacroBuildTestCase,
    SqlMacroCommandTestCase,
    SqlMacroEditTestCase,
    SqlMacroFormatTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_macros.helpers import (
    ALL_MACROS,
    BRACKET,
    CENTS_TO_DOLLARS,
    CLEAN_ORDERS,
    DATABASE,
    IN_SUPPORTED_COUNTRY,
    LATEST_PER_KEY,
    inspected_text,
    orders_model,
    output,
    run_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb, run_sqb

_UNION_COLUMNS: dict[str, str] = {
    "macros/sql/order_columns.sql": (
        'MACRO (description "Order columns in a fixed order", arguments (src RELATION '
        "(order_id BIGINT, status VARCHAR)));\n\nSELECT @src.order_id, @src.status\n"
    )
}
_HAS_TAG: dict[str, str] = {
    "macros/sql/has_tag.sql": (
        'MACRO (description "Whether the tags hold a tag", arguments (tags VARCHAR[], '
        "tag VARCHAR CONST), returns BOOLEAN);\n\nlist_contains(@tags, @tag)\n"
    )
}
_STATUS_LABEL: dict[str, str] = {
    "macros/sql/status_label.sql": (
        'MACRO (description "Status label", arguments (status VARCHAR CONST), returns VARCHAR);'
        "\n\n'status: ' || @status\n"
    )
}
_FIRST_ORDERS: dict[str, str] = {
    "macros/sql/first_orders.sql": (
        'MACRO (description "First orders", arguments (src RELATION (order_id BIGINT), '
        "n BIGINT CONST));\n\nWITH firsts AS (SELECT s.order_id FROM @src AS s "
        "ORDER BY s.order_id LIMIT @n)\n"
    )
}
_IS_STATUS: dict[str, str] = {
    "macros/sql/is_status.sql": (
        'MACRO (description "Whether the status column matches", arguments (status VARCHAR), '
        "returns BOOLEAN);\n\nstatus = @status\n"
    )
}
_SCOPED_DOUBLED: dict[str, str] = {
    "models/marts/_sqlbuild/_macros/sql/doubled.sql": (
        'MACRO (description "Doubled", arguments (v BIGINT), returns BIGINT);\n\n@v * 2\n'
    )
}


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroBuildTestCase(
            description="expression_macros_with_const_defaults_nesting_and_python_composition",
            files={
                **CENTS_TO_DOLLARS,
                **ALL_MACROS,
                **orders_model(
                    "SELECT\n  o.order_id,\n"
                    "  @sql.cents_to_dollars(o.amount_cents) AS amount,\n"
                    "  @sql.cents_to_dollars(o.fee_cents + o.tax_cents, places := 0) AS fees,\n"
                    "  @sql.net_amount(o.amount_cents, o.fee_cents) AS net,\n"
                    "  @py.bracket(@sql.cents_to_dollars(o.amount_cents)) AS label\n"
                    'FROM __ref("stg_orders") AS o\nWHERE o.order_id = 2\n'
                ),
            },
            query="SELECT order_id, amount, fees, net, label FROM orders",
            expected_rows=[(2, 5.0, 1.0, 4.5, "[5.0]")],
        ),
        SqlMacroBuildTestCase(
            description="cte_list_and_column_list_macros_with_enum_and_list_constant_arguments",
            files={
                **ALL_MACROS,
                **orders_model(
                    'WITH orders_raw AS (SELECT * FROM __ref("stg_orders")),\n'
                    "@sql.clean_orders(orders_raw)\n"
                    "final AS (\n  SELECT o.order_id, @sql.audit_columns(o)\n  FROM latest AS o\n"
                    "  WHERE @sql.is_open_status(o.status)\n"
                    '    AND @sql.in_supported_country(o.country_code, countries := @const("supported_countries"))\n'
                    ")\nSELECT * FROM final\n"
                ),
            },
            query="SELECT order_id, CAST(updated_at AS VARCHAR), was_updated FROM orders",
            expected_rows=[(1, "2026-01-03 00:00:00", True)],
        ),
        SqlMacroBuildTestCase(
            description="column_of_argument_and_list_default",
            files={
                **LATEST_PER_KEY,
                **IN_SUPPORTED_COUNTRY,
                **orders_model(
                    'WITH orders_raw AS (SELECT * FROM __ref("stg_orders")),\n'
                    "@sql.latest_per_key(orders_raw, key := status),\n"
                    "final AS (SELECT status, order_id FROM latest_rows "
                    "WHERE @sql.in_supported_country(country_code))\n"
                    "SELECT * FROM final\n"
                ),
            },
            query="SELECT status, order_id FROM orders ORDER BY status",
            expected_rows=[("closed", 2)],
        ),
        SqlMacroBuildTestCase(
            description="column_list_repeated_across_union_all_branches",
            files={
                **_UNION_COLUMNS,
                **orders_model(
                    'WITH o AS (SELECT * FROM __ref("stg_orders"))\n'
                    "SELECT @sql.order_columns(o) FROM o WHERE o.status = 'open'\n"
                    "UNION ALL\n"
                    "SELECT @sql.order_columns(o) FROM o WHERE o.status = 'closed'\n"
                ),
            },
            query="SELECT order_id, status FROM orders ORDER BY order_id, status",
            expected_rows=[(1, "open"), (1, "open"), (2, "closed"), (3, "open")],
        ),
        SqlMacroBuildTestCase(
            description="runtime_array_parameter_and_const_scalar",
            files={
                **_HAS_TAG,
                **orders_model(
                    "WITH tagged AS (SELECT 1 AS order_id, ['vip', 'gift'] AS tags "
                    "UNION ALL SELECT 2, ['gift'])\n"
                    "SELECT order_id, @sql.has_tag(tags, 'vip') AS is_vip FROM tagged\n"
                ),
            },
            query="SELECT order_id, is_vip FROM orders ORDER BY order_id",
            expected_rows=[(1, True), (2, False)],
        ),
        SqlMacroBuildTestCase(
            description="const_argument_takes_an_enum_value",
            files={
                **_STATUS_LABEL,
                **orders_model('SELECT @sql.status_label(@enum("order_status").OPEN) AS label\n'),
            },
            query="SELECT label FROM orders",
            expected_rows=[("status: open",)],
        ),
        SqlMacroBuildTestCase(
            description="const_parameter_as_limit_and_aliased_relation",
            files={
                **_FIRST_ORDERS,
                **orders_model(
                    'WITH o AS (SELECT DISTINCT order_id FROM __ref("stg_orders")),\n'
                    "@sql.first_orders(o, 2)\nSELECT order_id FROM firsts\n"
                ),
            },
            query="SELECT order_id FROM orders ORDER BY order_id",
            expected_rows=[(1,), (2,)],
        ),
        SqlMacroBuildTestCase(
            description="column_and_parameter_sharing_a_name",
            files={
                **_IS_STATUS,
                **orders_model(
                    "SELECT DISTINCT order_id, @sql.is_status('open') AS is_open "
                    'FROM __ref("stg_orders")\n'
                ),
            },
            query="SELECT order_id, is_open FROM orders ORDER BY order_id",
            expected_rows=[(1, True), (2, False), (3, True)],
        ),
        SqlMacroBuildTestCase(
            description="macro_scoped_to_a_model_folder",
            files={
                **_SCOPED_DOUBLED,
                **orders_model(
                    'SELECT DISTINCT order_id, @sql.doubled(order_id) AS doubled FROM __ref("stg_orders")\n'
                ),
            },
            query="SELECT order_id, doubled FROM orders ORDER BY order_id",
            expected_rows=[(1, 2), (2, 4), (3, 6)],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_model_calling_sql_macros_when_building_then_the_expanded_model_holds_the_rows(
    test_case: SqlMacroBuildTestCase, tmp_path: Path
) -> None:
    project_dir, result = run_project(tmp_path=tmp_path, files=test_case.files, command=("build",))

    assert result.returncode == 0, output(result)
    assert (
        query_duckdb(db_path=project_dir / DATABASE, sql=test_case.query) == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroCommandTestCase(
            description="python_macros_in_their_folder_render_as_before",
            files={
                **BRACKET,
                **orders_model(
                    'SELECT @py.bracket("order_id") AS label FROM __ref("stg_orders")\n'
                ),
            },
            command=("compile",),
            expected_returncode=0,
            expected_fragments=("'[' || CAST(order_id AS VARCHAR) || ']' AS label",),
            inspected_paths=("target/compiled/models/marts/orders.sql",),
        ),
        SqlMacroCommandTestCase(
            description="lineage_reads_the_arguments_of_a_sql_macro",
            files={
                **CENTS_TO_DOLLARS,
                **orders_model(
                    "SELECT o.order_id, @sql.cents_to_dollars(o.fee_cents + o.tax_cents, "
                    'places := 0) AS fees FROM __ref("stg_orders") AS o\n'
                ),
            },
            command=("lineage", "orders.fees", "--format", "list"),
            expected_returncode=0,
            expected_fragments=(
                "stg_orders.fee_cents -> orders.fees",
                "stg_orders.tax_cents -> orders.fees",
            ),
        ),
        SqlMacroCommandTestCase(
            description="rules_see_through_a_cte_macro_call",
            files={
                **CLEAN_ORDERS,
                **orders_model(
                    'WITH orders_raw AS (SELECT * FROM __ref("stg_orders")),\n'
                    "@sql.clean_orders(orders_raw)\nfinal AS (SELECT order_id FROM latest)\n"
                    "SELECT order_id FROM final\n"
                ),
            },
            command=("rules", "run", "SQBRMODEL102"),
            expected_returncode=1,
            expected_fragments=("models/marts/orders.sql", "[SQBRMODEL102]"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_project_with_macros_when_running_a_command_then_its_output_reflects_them(
    test_case: SqlMacroCommandTestCase, tmp_path: Path
) -> None:
    project_dir, result = run_project(
        tmp_path=tmp_path, files=test_case.files, command=test_case.command
    )
    printed: str = output(result) + inspected_text(
        project_dir=project_dir, relative_paths=test_case.inspected_paths
    )

    assert result.returncode == test_case.expected_returncode, printed
    for fragment in test_case.expected_fragments:
        assert fragment in printed, printed


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroEditTestCase(
            description="edited_expression_macro",
            files={
                **CENTS_TO_DOLLARS,
                **orders_model(
                    "SELECT DISTINCT order_id, @sql.cents_to_dollars(fee_cents) AS fee "
                    'FROM __ref("stg_orders")\nWHERE order_id = 2\n'
                ),
            },
            edited_path="macros/sql/cents_to_dollars.sql",
            replaced_text=("/ 100", "/ 10"),
            query="SELECT fee FROM orders",
            expected_rows=[(5.0,)],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_an_edited_sql_macro_when_rebuilding_then_its_callers_use_the_new_body(
    test_case: SqlMacroEditTestCase, tmp_path: Path
) -> None:
    project_dir, first = run_project(tmp_path=tmp_path, files=test_case.files, command=("build",))
    assert first.returncode == 0, output(first)
    macro: Path = project_dir / test_case.edited_path
    macro.write_text(macro.read_text().replace(*test_case.replaced_text), encoding="utf-8")

    second: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert second.returncode == 0, output(second)
    assert (
        query_duckdb(db_path=project_dir / DATABASE, sql=test_case.query) == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqlMacroFormatTestCase(
            description="cte_list_macro_and_its_call",
            files={
                "macros/sql/pair.sql": (
                    'MACRO (description "Pair", arguments (src RELATION (order_id BIGINT)));\n\n'
                    "with a as (select * from @src), b as (select order_id from a)\n"
                ),
                **orders_model(
                    'WITH o AS (SELECT * FROM __ref("stg_orders")),\n@sql.pair(o)\n'
                    "final AS (SELECT order_id FROM b)\nSELECT * FROM final\n"
                ),
            },
            formatted_path="macros/sql/pair.sql",
            expected_ending=(
                "WITH a AS (\n  SELECT *\n  FROM @src\n),\n\nb AS (\n  SELECT order_id\n"
                "  FROM a\n)\n"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_macro_files_when_formatting_then_bodies_and_calls_are_normalised(
    test_case: SqlMacroFormatTestCase, tmp_path: Path
) -> None:
    project_dir, result = run_project(tmp_path=tmp_path, files=test_case.files, command=("format",))

    assert result.returncode == 0, output(result)
    formatted: str = (project_dir / test_case.formatted_path).read_text(encoding="utf-8")
    assert formatted.endswith(test_case.expected_ending), formatted
    check: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "format", "--check"), project_dir=project_dir
    )
    assert check.returncode == 0, output(check)
    compiled: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )
    assert compiled.returncode == 0, output(compiled)
