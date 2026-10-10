"""Models whose analysis queries are equal in shape keep their own diagnostics and lineage.

Explicit expected outputs carried over from the deleted Python shared-binding tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    SharedQueryOutputTestCase,
)

_UPSTREAM_SQL: str = (
    "MODEL (description 'Test model.', materialized view); SELECT 1 AS id, 2.5 AS amount"
)
_HEADER: str = 'MODEL (description "Test model.", materialized view); '
_STUB_CTE: str = (
    "MODEL (description 'Test model.', materialized view); WITH {name} AS "
    '(SELECT CAST(2 AS VARCHAR) AS id) SELECT id FROM __ref("{upstream}")'
)
_MISSING: str = _HEADER + 'SELECT id FROM __ref("{upstream}") WHERE missing > 0'


def _write_project(*, project_dir: Path, models: dict[str, str]) -> None:
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n', encoding="utf-8"
    )
    model_dir: Path = project_dir / "models"
    model_dir.mkdir()
    for name, sql in {"orders": _UPSTREAM_SQL, "customers": _UPSTREAM_SQL, **models}.items():
        _ = (model_dir / f"{name}.sql").write_text(sql, encoding="utf-8")


def _upstream_sources(
    *, project_dir: Path, column: str, mode: str, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str]]:
    code: int = main(
        [
            "--project-dir",
            str(project_dir),
            "lineage",
            column,
            "--format",
            "json",
            "--direction",
            "upstream",
            "--depth",
            "1",
            "--mode",
            mode,
        ]
    )
    trace: list[dict[str, Any]] = json.loads(capsys.readouterr().out)["trace"]
    return code, [step["source"]["resource_name"] for step in trace]


@pytest.mark.parametrize(
    "test_case",
    [
        SharedQueryOutputTestCase(
            description="identical shapes over different inputs",
            models={
                "orders_summary": _HEADER + 'SELECT id, amount FROM __ref("orders")',
                "customers_summary": _HEADER + 'SELECT id, amount FROM __ref("customers")',
            },
            expected_lineage=(
                ("orders_summary.id", "orders", "rich"),
                ("customers_summary.id", "customers", "rich"),
                ("orders_summary.amount", "orders", "fast"),
                ("customers_summary.amount", "customers", "fast"),
            ),
        ),
        SharedQueryOutputTestCase(
            description="a relation name used as a qualifier",
            models={
                "orders_summary": _HEADER + 'SELECT orders.id FROM __ref("orders") AS orders',
                "customers_summary": (
                    _HEADER + 'SELECT customers.id FROM __ref("customers") AS customers'
                ),
            },
            expected_lineage=(
                ("orders_summary.id", "orders", "rich"),
                ("customers_summary.id", "customers", "rich"),
            ),
        ),
        SharedQueryOutputTestCase(
            description="an authored lowercase stub-named CTE",
            models={
                "orders_summary": _STUB_CTE.format(
                    name="__sqlbuild_project_input_0", upstream="orders"
                ),
                "customers_summary": _STUB_CTE.format(
                    name="__sqlbuild_project_input_0", upstream="customers"
                ),
                "next_orders": _HEADER + 'SELECT id + 1 AS next_id FROM __ref("orders_summary")',
            },
            expected_lineage=(
                ("orders_summary.id", "orders", "rich"),
                ("customers_summary.id", "customers", "rich"),
            ),
        ),
        SharedQueryOutputTestCase(
            description="an authored uppercase stub-named CTE",
            models={
                "orders_summary": _STUB_CTE.format(
                    name="__SQLBUILD_PROJECT_INPUT_0", upstream="orders"
                ),
                "customers_summary": _STUB_CTE.format(
                    name="__SQLBUILD_PROJECT_INPUT_0", upstream="customers"
                ),
                "next_orders": _HEADER + 'SELECT id + 1 AS next_id FROM __ref("orders_summary")',
            },
            expected_lineage=(
                ("orders_summary.id", "orders", "rich"),
                ("customers_summary.id", "customers", "rich"),
            ),
        ),
        SharedQueryOutputTestCase(
            description="later-wave members of equal shape",
            models={
                "orders_summary": _HEADER + 'SELECT id, amount FROM __ref("orders")',
                "customers_summary": _HEADER + 'SELECT id, amount FROM __ref("customers")',
                "orders_rollup": _HEADER + 'SELECT id, amount FROM __ref("orders_summary")',
                "customers_rollup": (_HEADER + 'SELECT id, amount FROM __ref("customers_summary")'),
            },
            expected_lineage=(
                ("orders_rollup.amount", "orders_summary", "rich"),
                ("customers_rollup.amount", "customers_summary", "rich"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_equal_shapes_when_compiling_then_each_model_keeps_its_own_lineage(
    test_case: SharedQueryOutputTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(project_dir=tmp_path, models=test_case.models)

    compiled: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    diagnostics: list[object] = json.loads(capsys.readouterr().out)["diagnostics"]
    traces: list[tuple[int, list[str]]] = [
        _upstream_sources(project_dir=tmp_path, column=column, mode=mode, capsys=capsys)
        for column, _, mode in test_case.expected_lineage
    ]

    assert (compiled, diagnostics) == (0, [])
    assert traces == [(0, [upstream]) for _, upstream, _ in test_case.expected_lineage]


@pytest.mark.parametrize(
    "test_case",
    [
        SharedQueryOutputTestCase(
            description="findings after the relation",
            models={
                "orders_summary": _MISSING.format(upstream="orders"),
                "customers_summary": _MISSING.format(upstream="customers"),
            },
            expected_findings=(("orders_summary", "orders"), ("customers_summary", "customers")),
        ),
        SharedQueryOutputTestCase(
            description="a later-wave member of a group with findings",
            models={
                "orders_summary": _MISSING.format(upstream="orders"),
                "customers_summary": _MISSING.format(upstream="customers"),
                "orders_mid": _HEADER + 'SELECT id, amount FROM __ref("orders")',
                "orders_late": _MISSING.format(upstream="orders_mid"),
            },
            expected_findings=(
                ("orders_summary", "orders"),
                ("customers_summary", "customers"),
                ("orders_late", "orders_mid"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_equal_shapes_with_findings_when_compiling_then_reports_each_model_exactly(
    test_case: SharedQueryOutputTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(project_dir=tmp_path, models=test_case.models)

    compiled: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    diagnostics: list[dict[str, Any]] = json.loads(capsys.readouterr().out)["diagnostics"]
    findings: list[tuple[str, str, str, int, int]] = sorted(
        (
            diagnostic["resource_name"],
            diagnostic["code"],
            diagnostic["message"],
            diagnostic["location"]["column"],
            diagnostic["location"]["end_column"],
        )
        for diagnostic in diagnostics
    )
    columns: dict[str, int] = {
        model: sql.index("missing") + 1
        for model, sql in test_case.models.items()
        if "missing" in sql
    }

    assert compiled == 1
    assert findings == sorted(
        (
            model,
            "B002",
            f"Unknown column 'missing' in {upstream}",
            columns[model],
            columns[model] + len("missing"),
        )
        for model, upstream in test_case.expected_findings
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
