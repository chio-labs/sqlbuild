"""Real CLI coverage for how SQBRSQL028 judges the qualification of SQL macro slot reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import run_cli as main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    MacroSlotQualificationTestCase,
)

_PROJECT: str = (
    'name = "shop"\n'
    'adapter = "duckdb"\n'
    'default_target = "dev"\n\n'
    "[connections.local]\n"
    'database = "shop.duckdb"\n\n'
    "[targets.dev]\n"
    'connection = "local"\n'
    'schema = "dev"\n\n'
    "[rules]\n"
    'select = ["SQBRSQL028"]\n'
)
_WEEKLY_ORDERS: str = (
    'MODEL (\n  description "Weekly orders per product",\n  materialized table,\n);\n\n'
    "SELECT 1 AS product_id, CAST(10 AS BIGINT) AS orders_placed, "
    "CAST(1 AS BIGINT) AS refund_count\n"
)
_REFUND_RATES: str = (
    'MODEL (\n  description "Weekly refund rate per product",\n  materialized table,\n);\n\n'
    'WITH weekly AS (SELECT * FROM __ref("weekly_orders")),\n'
    "@sql.weekly_rates(weekly, weekly.keys := (product_id), "
    "weekly.order_count := orders_placed, __cte := by_product)\n"
    "final AS (SELECT * FROM by_product)\n"
    "SELECT * FROM final\n"
)


def _weekly_rates(first_step: str) -> str:
    return (
        'MACRO (\n  description "Weekly refund rate per grain",\n'
        "  arguments (weekly RELATION (keys COLUMNS, order_count BIGINT, refund_count BIGINT)),\n"
        ");\n\n"
        f"WITH counted AS (\n{first_step}\n),\n\n"
        "rated AS (\n"
        "  SELECT\n"
        "    @weekly.keys,\n"
        "    SUM(refunds) / NULLIF(SUM(orders), 0) AS refund_rate\n"
        "  FROM counted\n"
        "  GROUP BY @weekly.keys\n"
        ")\n"
    )


def _rates_project(first_step: str) -> dict[str, str]:
    return {
        "models/weekly_orders.sql": _WEEKLY_ORDERS,
        "models/refund_rates.sql": _REFUND_RATES,
        "models/_macros/sql/weekly_rates.sql": _weekly_rates(first_step),
    }


@pytest.mark.parametrize(
    "test_case",
    [
        MacroSlotQualificationTestCase(
            description="a first step written in plain slot reads passes",
            files=_rates_project(
                "  SELECT\n"
                "    @weekly.keys,\n"
                "    @weekly.order_count AS orders,\n"
                "    @weekly.refund_count AS refunds\n"
                "  FROM @weekly"
            ),
            expected_exit_code=0,
            expected_fragments=("Project compiled",),
            absent_fragments=("SQBRSQL028",),
        ),
        MacroSlotQualificationTestCase(
            description="aliased slot reads beside a plain group read fail once, at the macro",
            files=_rates_project(
                "  SELECT\n"
                "    @weekly.keys,\n"
                "    s.@weekly.order_count AS orders,\n"
                "    s.@weekly.refund_count AS refunds\n"
                "  FROM @weekly AS s"
            ),
            expected_exit_code=1,
            expected_fragments=(
                "--> models/_macros/sql/weekly_rates.sql:8:5",
                "to qualify it, read through an alias: `FROM @rel AS s`, then `s.@rel.column`",
            ),
            absent_fragments=("--> models/refund_rates.sql",),
        ),
        MacroSlotQualificationTestCase(
            description="an expression macro's plain reads leave the caller's style to the caller",
            files={
                "models/orders.sql": (
                    'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
                    "SELECT 1 AS order_id, CAST(10 AS DOUBLE) AS amount, "
                    "CAST(1 AS DOUBLE) AS discount\n"
                ),
                "models/_macros/sql/net_amount.sql": (
                    'MACRO (\n  description "Order amount after discount",\n'
                    "  arguments (orders RELATION (amount DOUBLE, discount DOUBLE)),\n);\n\n"
                    "@orders.amount - @orders.discount\n"
                ),
                "models/order_totals.sql": (
                    'MODEL (\n  description "Net amount per order",\n  materialized table,\n);\n\n'
                    "SELECT order_id, @sql.net_amount(orders) AS net\n"
                    'FROM __ref("orders") AS orders\n'
                ),
            },
            expected_exit_code=0,
            expected_fragments=("Project compiled",),
            absent_fragments=("SQBRSQL028",),
        ),
        MacroSlotQualificationTestCase(
            description="a caller that mixes styles itself still fails",
            files={
                "models/orders.sql": (
                    'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
                    "SELECT 1 AS order_id, 'open' AS status\n"
                ),
                "models/open_orders.sql": (
                    'MODEL (\n  description "Open orders",\n  materialized table,\n);\n\n'
                    'SELECT o.order_id, status FROM __ref("orders") AS o\n'
                ),
            },
            expected_exit_code=1,
            expected_fragments=("error[SQBRSQL028]", "--> models/open_orders.sql"),
            absent_fragments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_slot_reads_when_compiling_then_qualification_is_judged_as_written(
    test_case: MacroSlotQualificationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files: dict[str, str] = {"sqlbuild_project.toml": _PROJECT, **test_case.files}
    for relative, contents in files.items():
        path: Path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile"])

    output: str = "".join(capsys.readouterr())
    assert exit_code == test_case.expected_exit_code, output
    assert [fragment in output for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ], output
    assert [fragment in output for fragment in test_case.absent_fragments] == [
        False for _ in test_case.absent_fragments
    ], output
