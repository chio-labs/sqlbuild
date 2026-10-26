"""Compile checks the string literals that fill enum-typed columns against the enum's members."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sqlbuild._native import run_cli as main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    EnumLiteralCompileTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import write_enum_project

_UNION_MODEL: str = (
    "SELECT order_id, 'open' AS status FROM __source(\"web_orders\")\n"
    "UNION ALL\n"
    "SELECT order_id, 'held' FROM __source(\"partner_orders\")\n"
)


@pytest.mark.parametrize(
    "test_case",
    (
        EnumLiteralCompileTestCase(
            description="a union branch literal outside the enum fails at the literal",
            model_sql=_UNION_MODEL,
            expected_exit_code=1,
            expected_diagnostics=(
                (
                    "K013",
                    "value 'held' in column 'status' of model 'orders' is not a member of "
                    "enum order_status",
                    12,
                ),
            ),
        ),
        EnumLiteralCompileTestCase(
            description="a literal passed through a CTE fails",
            model_sql=(
                "WITH flagged AS (\n"
                "  SELECT order_id, 'pending' AS status FROM __source(\"web_orders\")\n"
                ")\n"
                "SELECT order_id, status FROM flagged\n"
            ),
            expected_exit_code=1,
            expected_diagnostics=(
                (
                    "K013",
                    "value 'pending' in column 'status' of model 'orders' is not a member of "
                    "enum order_status",
                    11,
                ),
            ),
        ),
        EnumLiteralCompileTestCase(
            description="a filter on the passed-through column leaves the check to the audit",
            model_sql=(
                "WITH unioned AS (\n"
                f"{_UNION_MODEL}"
                ")\n"
                "SELECT order_id, status FROM unioned WHERE status <> 'held'\n"
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        EnumLiteralCompileTestCase(
            description="an unfiltered passthrough of the union is still checked",
            model_sql=f"WITH unioned AS (\n{_UNION_MODEL})\nSELECT order_id, status FROM unioned\n",
            expected_exit_code=1,
            expected_diagnostics=(
                (
                    "K013",
                    "value 'held' in column 'status' of model 'orders' is not a member of "
                    "enum order_status",
                    13,
                ),
            ),
        ),
        EnumLiteralCompileTestCase(
            description="member literals compile",
            model_sql=_UNION_MODEL.replace("'held'", "'closed'"),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        EnumLiteralCompileTestCase(
            description="enum member references compile",
            model_sql=(
                'SELECT order_id, @enum("order_status").CLOSED AS status '
                'FROM __source("web_orders")\n'
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        EnumLiteralCompileTestCase(
            description="a computed value is left to the generated audit",
            model_sql=(
                "SELECT order_id, CASE WHEN order_id > 1 THEN 'held' ELSE 'open' END AS status "
                'FROM __source("web_orders")\n'
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        EnumLiteralCompileTestCase(
            description="without an enforced contract the enum domain is not checked",
            model_sql=_UNION_MODEL,
            contract="none",
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_enum_typed_column_when_compiling_then_non_member_literals_fail(
    test_case: EnumLiteralCompileTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_enum_project(root=tmp_path, model_sql=test_case.model_sql, contract=test_case.contract)

    exit_code: int = main(
        ["--project-dir", str(tmp_path), "--no-color", "compile", "--json", "--no-cache"]
    )

    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])
    assert exit_code == test_case.expected_exit_code
    errors: list[dict[str, object]] = list(
        filter(lambda item: item["severity"] == "error", diagnostics)
    )
    assert (
        tuple(
            (item["code"], item["message"], cast(dict[str, object], item["location"])["line"])
            for item in errors
        )
        == test_case.expected_diagnostics
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
