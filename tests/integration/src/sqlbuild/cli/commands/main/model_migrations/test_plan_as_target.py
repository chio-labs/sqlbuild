"""Integration coverage for inspection-only plan --as previews of migrations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    PlanAsTargetTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    DESTINATION_MODEL,
    CliRun,
    migration_decisions,
    plan_json,
    prepare_prod_rename,
    run_sqb,
    warehouse_state,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanAsTargetTestCase(
            description="pending prod migration previews as migrate",
            preview_target="prod",
            expected_exit_code=0,
            expected_decisions=("migrate",),
            expected_fragment="migrate  prod.stg_orders -> prod.stg_customer_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pending_prod_migration_when_planning_as_prod_then_previews_without_mutation(
    test_case: PlanAsTargetTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_prod_rename(project_dir=tmp_path, capsys=capsys)
    before: tuple[tuple[Any, ...], ...] = warehouse_state(project_dir=tmp_path)

    preview: dict[str, Any] = plan_json(
        project_dir=tmp_path, capsys=capsys, args=("--as", test_case.preview_target)
    )
    active: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    text: CliRun = run_sqb(
        project_dir=tmp_path, args=("plan", "--as", test_case.preview_target), capsys=capsys
    )
    after: tuple[tuple[Any, ...], ...] = warehouse_state(project_dir=tmp_path)

    assert migration_decisions(preview) == test_case.expected_decisions
    assert preview["migrations"][0]["destination"] == "prod.stg_customer_orders"
    assert migration_decisions(active) == ("origin_missing",)
    assert text.exit_code == test_case.expected_exit_code, text.output
    assert "Previewing plan as target 'prod'" in text.output
    assert test_case.expected_fragment in text.output
    assert after == before
    assert ("prod", "_sqlbuild_migrations", 0) not in after
    assert all(name != DESTINATION_MODEL for _, name, _ in after)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanAsTargetTestCase(
            description="executed prod migration previews as done",
            preview_target="prod",
            expected_exit_code=0,
            expected_decisions=("done",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_executed_prod_migration_when_planning_as_prod_then_reports_done(
    test_case: PlanAsTargetTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_prod_rename(project_dir=tmp_path, capsys=capsys)
    migrated: CliRun = run_sqb(
        project_dir=tmp_path, args=("build", "--target", "prod"), capsys=capsys
    )
    before: tuple[tuple[Any, ...], ...] = warehouse_state(project_dir=tmp_path)

    preview: dict[str, Any] = plan_json(
        project_dir=tmp_path, capsys=capsys, args=("--as", test_case.preview_target)
    )

    assert migrated.exit_code == test_case.expected_exit_code, migrated.output
    assert migration_decisions(preview) == test_case.expected_decisions
    assert preview["migrations"][0]["target"] == test_case.preview_target
    assert warehouse_state(project_dir=tmp_path) == before


@pytest.mark.parametrize(
    "test_case",
    [
        PlanAsTargetTestCase(
            description="unknown target fails clearly",
            preview_target="staging",
            expected_exit_code=1,
            expected_fragment="unknown target 'staging' for plan --as",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_target_when_planning_as_it_then_fails_clearly(
    test_case: PlanAsTargetTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_prod_rename(project_dir=tmp_path, capsys=capsys)

    result: CliRun = run_sqb(
        project_dir=tmp_path, args=("plan", "--as", test_case.preview_target), capsys=capsys
    )

    assert result.exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
