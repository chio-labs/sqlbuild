"""Integration coverage for compiler SQL dialect support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    SnowflakeCompileIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeCompileIntegrationTestCase(
            description="grouping sets include a nested variant dynamic key",
            query_sql="""WITH orders AS (
    SELECT
        'ready' AS category,
        OBJECT_CONSTRUCT('labels', OBJECT_CONSTRUCT('1', 'priority')) AS attributes,
        1 AS item_id,
        10 AS amount
)
SELECT
    category,
    attributes:labels[TO_VARCHAR(item_id)] AS attribute_value,
    SUM(amount) AS total_amount
FROM orders
GROUP BY GROUPING SETS (
    (category, attributes:labels[TO_VARCHAR(item_id)]),
    ()
)
""",
            expected_exit_code=0,
            expected_diagnostics=(),
            expected_query_fragment="attributes:labels[TO_VARCHAR(item_id)]",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_supported_snowflake_aggregation_when_compiling_then_project_succeeds(
    test_case: SnowflakeCompileIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "order_summary.sql"
    model.parent.mkdir()
    model.write_text(
        f"MODEL (database warehouse, schema analytics);\n\n{test_case.query_sql}",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])
    resources: dict[str, object] = cast(dict[str, object], result["resources"])
    models: list[dict[str, object]] = cast(list[dict[str, object]], resources["models"])

    assert exit_code == test_case.expected_exit_code
    assert tuple(item["code"] for item in diagnostics) == test_case.expected_diagnostics
    assert test_case.expected_query_fragment in cast(str, models[0]["query_sql"])
