"""Real CLI coverage for the compiled SQL a compile writes when Rules fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import run_cli as main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RuleFailureArtifactsTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import open_orders_model

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
_ORDERS: str = (
    'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
    "SELECT 1 AS order_id, 'open' AS status\n"
)
_HEADER: str = "-- sqb: compile failed for this model; not buildable\n"


@pytest.mark.parametrize(
    "test_case",
    [
        RuleFailureArtifactsTestCase(
            description="a model failing a Rule is written with a header listing its findings",
            open_orders_sql='SELECT o.order_id, status FROM __ref("orders") AS o',
            expected_exit_code=1,
            expected_open_orders=(
                _HEADER + "-- SQBRSQL028 at models/open_orders.sql:6:20: "
                "Single-relation query mixes qualified and unqualified columns\n"
                'SELECT o.order_id, status FROM __ref("orders") AS o\n'
            ),
            expected_manifest=False,
        ),
        RuleFailureArtifactsTestCase(
            description="a passing compile writes the same model without the header",
            open_orders_sql='SELECT o.order_id, o.status FROM __ref("orders") AS o',
            expected_exit_code=0,
            expected_open_orders='SELECT o.order_id, o.status FROM __ref("orders") AS o\n',
            expected_manifest=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rule_findings_when_compiling_then_models_are_written_with_a_failure_header(
    test_case: RuleFailureArtifactsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT,
        "models/orders.sql": _ORDERS,
        "models/open_orders.sql": open_orders_model(
            'SELECT o.order_id, o.status FROM __ref("orders") AS o'
        ),
    }
    for relative, contents in files.items():
        path: Path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    compile_args: list[str] = [
        "--no-color",
        "--project-dir",
        str(tmp_path),
        "compile",
        "--manifest",
    ]
    _ = main(compile_args)
    _ = (tmp_path / "models" / "open_orders.sql").write_text(
        open_orders_model(test_case.open_orders_sql), encoding="utf-8"
    )
    assert (tmp_path / "target" / "manifest.json").exists()

    exit_code: int = main(compile_args)

    output: str = "".join(capsys.readouterr())
    compiled: Path = tmp_path / "target" / "compiled" / "models"
    assert exit_code == test_case.expected_exit_code, output
    assert (compiled / "open_orders.sql").read_text(encoding="utf-8") == (
        test_case.expected_open_orders
    )
    assert (compiled / "orders.sql").read_text(encoding="utf-8") == (
        "SELECT 1 AS order_id, 'open' AS status\n"
    )
    assert (tmp_path / "target" / "manifest.json").exists() is test_case.expected_manifest
