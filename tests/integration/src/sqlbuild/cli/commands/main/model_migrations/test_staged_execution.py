"""Integration coverage for staged migration execution, archived displacement, and recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    MigrationArchiveExpiryTestCase,
    StagedPlanOutputTestCase,
    StagedReplaceTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    DESTINATION_MODEL,
    JANITOR_PROJECT_TOML,
    ORIGIN_MODEL,
    CliRun,
    archived_order_ids,
    archived_relations,
    build,
    build_ok,
    fail_non_transactional_promotion_rename,
    fail_partial_stage,
    fail_promotion_rename,
    live_relations,
    migration_decisions,
    migration_events,
    no_failure,
    order_ids,
    plan_json,
    prepare_forced_replace,
    run_sqb,
    state_tables,
)

_STAGE: str = "migration_stage"
_PREVIOUS: str = "migration_previous"
_FORCED_EVENT: tuple[str, str, str] = (ORIGIN_MODEL, DESTINATION_MODEL, "forced_replace")


@pytest.mark.parametrize(
    "test_case",
    [
        StagedReplaceTestCase(
            description="successful forced replace keeps the displaced destination archived",
            install_failure=no_failure,
            expected_first_exit_code=0,
            expected_relations_after_failure=("raw_orders", "stg_customer_orders", "stg_orders"),
            expected_previous_ids_after_failure=((1, 2),),
            expected_decision_after_failure="done",
            expected_final_previous_ids=((1, 2),),
            expected_final_abandoned_stages=0,
            expected_final_events=(_FORCED_EVENT,),
        ),
        StagedReplaceTestCase(
            description="transactional crash while promoting leaves the live destination intact",
            install_failure=fail_promotion_rename,
            expected_first_exit_code=1,
            expected_relations_after_failure=("raw_orders", "stg_customer_orders", "stg_orders"),
            expected_previous_ids_after_failure=(),
            expected_decision_after_failure="forced_replace",
            expected_final_previous_ids=((1, 2),),
            expected_final_abandoned_stages=1,
            expected_final_events=(_FORCED_EVENT,),
        ),
        StagedReplaceTestCase(
            description="non-transactional crash between renames keeps the old data archived",
            install_failure=fail_non_transactional_promotion_rename,
            expected_first_exit_code=1,
            expected_relations_after_failure=("raw_orders", "stg_orders"),
            expected_previous_ids_after_failure=((1, 2),),
            expected_decision_after_failure="migrate",
            expected_final_previous_ids=((1, 2),),
            expected_final_abandoned_stages=1,
            expected_final_events=((ORIGIN_MODEL, DESTINATION_MODEL, "migrate"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_forced_replace_when_interrupted_then_retry_converges_without_losing_data(
    test_case: StagedReplaceTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The destination is never dropped and a retry never promotes an old stage."""

    prepare_forced_replace(project_dir=tmp_path, capsys=capsys)

    with monkeypatch.context() as patch:
        test_case.install_failure(patch)
        first: CliRun = build(project_dir=tmp_path, capsys=capsys)
    relations_after_failure: tuple[str, ...] = live_relations(project_dir=tmp_path)
    previous_after_failure: tuple[tuple[int, ...], ...] = archived_order_ids(
        project_dir=tmp_path, kind=_PREVIOUS
    )
    after_failure: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert first.exit_code == test_case.expected_first_exit_code, first.output
    assert relations_after_failure == test_case.expected_relations_after_failure
    assert previous_after_failure == test_case.expected_previous_ids_after_failure
    assert migration_decisions(after_failure) == (test_case.expected_decision_after_failure,)
    assert order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}") == tuple(
        range(1, 6)
    )
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == tuple(range(1, 6))
    assert len(archived_relations(project_dir=tmp_path, kind=_STAGE)) == (
        test_case.expected_final_abandoned_stages
    )
    assert archived_order_ids(project_dir=tmp_path, kind=_PREVIOUS) == (
        test_case.expected_final_previous_ids
    )
    assert migration_events(project_dir=tmp_path) == test_case.expected_final_events


@pytest.mark.parametrize(
    "test_case",
    [
        StagedPlanOutputTestCase(
            description="duckdb plans a physical copy promoted in one transaction",
            expected_transfer="copy",
            expected_promotion="transactional_rename",
            expected_storage_transition=None,
            expected_text_fragment="└── transfer  physical copy, promote by transactional rename",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_forced_replace_when_planning_then_reports_transfer_and_promotion(
    test_case: StagedPlanOutputTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Plan text and JSON state how the migration is staged and promoted."""

    prepare_forced_replace(project_dir=tmp_path, capsys=capsys)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    text: CliRun = run_sqb(project_dir=tmp_path, args=("plan",), capsys=capsys)

    migration: dict[str, Any] = plan["migrations"][0]
    assert migration["transfer"] == test_case.expected_transfer
    assert migration["promotion"] == test_case.expected_promotion
    assert migration["storage_transition"] == test_case.expected_storage_transition
    assert "statement" not in migration
    assert test_case.expected_text_fragment in text.output


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationArchiveExpiryTestCase(
            description="janitor expires abandoned stages and displaced destinations only",
            janitor_retention_days="30",
            expected_archives_before=2,
            expected_relations_after=("stg_customer_orders", "stg_orders"),
            expected_migration_state_kept=True,
        ),
        MigrationArchiveExpiryTestCase(
            description="janitor removing stale relations still keeps the migration state table",
            janitor_retention_days="0",
            expected_archives_before=2,
            expected_relations_after=("stg_customer_orders",),
            expected_migration_state_kept=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_migration_archives_when_janitor_runs_then_expires_them_by_name(
    test_case: MigrationArchiveExpiryTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Archive names alone let janitor remove migration leftovers without touching live data."""

    prepare_forced_replace(project_dir=tmp_path, capsys=capsys, project_toml=JANITOR_PROJECT_TOML)
    with monkeypatch.context() as patch:
        fail_partial_stage(patch)
        _ = build(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    archives_before: int = len(
        archived_relations(project_dir=tmp_path, kind=_STAGE, schema="dev")
    ) + len(archived_relations(project_dir=tmp_path, kind=_PREVIOUS, schema="dev"))

    janitor: CliRun = run_sqb(
        project_dir=tmp_path,
        args=("janitor", "--auto-approve", "--retention-days", test_case.janitor_retention_days),
        capsys=capsys,
    )

    assert janitor.exit_code == 0, janitor.output
    assert archives_before == test_case.expected_archives_before
    assert archived_relations(project_dir=tmp_path, kind=_STAGE, schema="dev") == ()
    assert archived_relations(project_dir=tmp_path, kind=_PREVIOUS, schema="dev") == (), (
        janitor.output
    )
    assert live_relations(project_dir=tmp_path, schema="dev") == (
        test_case.expected_relations_after
    )
    assert order_ids(project_dir=tmp_path, relation=f"dev.{DESTINATION_MODEL}") == tuple(
        range(1, 6)
    )
    assert ("_sqlbuild_migrations" in state_tables(project_dir=tmp_path, schema="dev")) is (
        test_case.expected_migration_state_kept
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
