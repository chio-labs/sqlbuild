"""Deferred migrate_from lookups skip selected models and survive unlistable origins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild._native import CompilePipelineResult
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    UnlistedMigrationOriginTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    UnlistedDatabaseDuckDbAdapter,
    plan_deferred_project,
)

_UNLISTED_DATABASE: str = "archive_db"
_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[targets.dev]\nschema = "dev"\n\n'
        '[targets.prod]\nschema = "prod"\n'
    ),
    "models/order_ledger.sql": (
        'MODEL (description "Test model order_ledger.", materialized table, '
        f"migrate_from {_UNLISTED_DATABASE}.prod.order_history);\n\nSELECT 1 AS order_id\n"
    ),
    "models/order_report.sql": (
        'MODEL (description "Test model order_report.", materialized table);\n\n'
        'SELECT order_id FROM __ref("order_ledger")\n'
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        UnlistedMigrationOriginTestCase(
            description="unlistable origin of an unselected upstream falls back with a warning",
            select=("order_report",),
            expected_warnings=(
                "could not list archive_db.prod.order_history in the deferred target to look "
                "for a pre-migration relation, so model 'order_ledger' is deferred under its "
                "current name: cannot list database archive_db",
            ),
            expected_unlisted_reads=1,
        ),
        UnlistedMigrationOriginTestCase(
            description="selected models are never looked up in the deferred target",
            select=("order_ledger", "order_report"),
            expected_warnings=(),
            expected_unlisted_reads=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unlistable_migration_origin_when_planning_with_defer_then_planning_continues(
    test_case: UnlistedMigrationOriginTestCase,
    tmp_path: Path,
    connection: Any,
) -> None:
    connection.execute("CREATE SCHEMA dev")
    connection.execute("CREATE SCHEMA prod")
    connection.execute("CREATE TABLE dev.order_ledger AS SELECT 1 AS order_id")
    adapter: UnlistedDatabaseDuckDbAdapter = UnlistedDatabaseDuckDbAdapter(
        connection=connection, unlisted_database=_UNLISTED_DATABASE
    )

    result: CompilePipelineResult = plan_deferred_project(
        project_dir=tmp_path,
        adapter=adapter,
        project_files=_PROJECT_FILES,
        select=test_case.select,
    )

    assert (
        tuple(
            filter(
                lambda message: "deferred target" in message,
                (warning.message for warning in result.plan_output.warnings),
            )
        )
        == test_case.expected_warnings
    ), test_case.description
    assert (
        adapter.listed_databases.count(_UNLISTED_DATABASE) == test_case.expected_unlisted_reads
    ), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
