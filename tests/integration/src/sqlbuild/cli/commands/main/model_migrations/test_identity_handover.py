"""Integration coverage for identity handover of renamed views and tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    IdentityHandoverTestCase,
    RenamedPlanTextTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    build,
    build_ok,
    execute,
    fail_model_build,
    fail_nothing_in_build,
    load_raw_orders,
    migration_events,
    model_entry,
    original_replay_order_models,
    plan_json,
    query,
    renamed_replay_order_models,
    row_count,
    run_sqb,
    write_project,
)

_MARK_HISTORY: str = (
    "UPDATE main.daily_order_totals SET total_cents = -1 WHERE order_date = TIMESTAMP '2026-01-01'"
)
_READ_MARK: str = (
    "SELECT total_cents FROM main.customer_daily_order_totals "
    "WHERE order_date = TIMESTAMP '2026-01-01'"
)
_EVENTS: tuple[tuple[str, str, str], ...] = (
    ("daily_order_totals", "customer_daily_order_totals", "migrate"),
    ("orders_enriched", "customer_orders_enriched", "renamed"),
    ("stg_orders", "stg_customer_orders", "migrate"),
)


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityHandoverTestCase(
            middle_materialization="view",
            description="renamed view between incrementals does not replay downstream history",
            install_failure=fail_nothing_in_build,
            failing_model="",
            expected_first_exit_code=0,
            expected_first_view_reason="renamed",
            expected_retry_totals_reason="normal_incremental",
            expected_totals_rows=8,
            expected_marked_total=-1,
            expected_events=_EVENTS,
        ),
        IdentityHandoverTestCase(
            middle_materialization="view",
            description="retry after the renamed view was built keeps downstream history",
            install_failure=fail_model_build,
            failing_model="customer_daily_order_totals",
            expected_first_exit_code=1,
            expected_first_view_reason="renamed",
            expected_retry_totals_reason="normal_incremental",
            expected_totals_rows=8,
            expected_marked_total=-1,
            expected_events=_EVENTS,
        ),
        IdentityHandoverTestCase(
            middle_materialization="view",
            description="retry before the renamed view was built keeps downstream history",
            install_failure=fail_model_build,
            failing_model="stg_customer_orders",
            expected_first_exit_code=1,
            expected_first_view_reason="renamed",
            expected_retry_totals_reason="normal_incremental",
            expected_totals_rows=8,
            expected_marked_total=-1,
            expected_events=_EVENTS,
        ),
        IdentityHandoverTestCase(
            middle_materialization="table",
            description="renamed table between incrementals is rebuilt without replaying history",
            install_failure=fail_model_build,
            failing_model="customer_daily_order_totals",
            expected_first_exit_code=1,
            expected_first_view_reason="renamed",
            expected_retry_totals_reason="normal_incremental",
            expected_totals_rows=8,
            expected_marked_total=-1,
            expected_events=_EVENTS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_chain_with_full_replay_when_building_then_migrated_history_survives(
    test_case: IdentityHandoverTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renamed view hands its identity downstream so replay_on_change keeps marked history."""

    write_project(
        project_dir=tmp_path,
        models=original_replay_order_models(middle=test_case.middle_materialization),
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    execute(project_dir=tmp_path, sql=_MARK_HISTORY)
    load_raw_orders(project_dir=tmp_path, first_day=3, last_day=8)
    write_project(
        project_dir=tmp_path,
        models=renamed_replay_order_models(middle=test_case.middle_materialization),
    )

    first_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    with monkeypatch.context() as patch:
        test_case.install_failure(monkeypatch=patch, model_name=test_case.failing_model)
        first: CliRun = build(project_dir=tmp_path, capsys=capsys)
    retry_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert first.exit_code == test_case.expected_first_exit_code, first.output
    assert model_entry(plan=first_plan, name="customer_orders_enriched")["reason"] == (
        test_case.expected_first_view_reason
    )
    assert model_entry(plan=first_plan, name="customer_daily_order_totals")["reason"] != (
        "upstream_changed"
    )
    assert model_entry(plan=retry_plan, name="customer_daily_order_totals")["reason"] == (
        test_case.expected_retry_totals_reason
    )
    assert (
        row_count(project_dir=tmp_path, relation="main.customer_daily_order_totals")
        == test_case.expected_totals_rows
    )
    assert query(project_dir=tmp_path, sql=_READ_MARK) == [(test_case.expected_marked_total,)]
    assert tuple(sorted(migration_events(project_dir=tmp_path))) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    [
        RenamedPlanTextTestCase(
            description="plan lists renamed views separately from data migrations",
            expected_fragment=(
                "Renamed (1)\n└── customer_orders_enriched  main.orders_enriched -> "
                "main.customer_orders_enriched  (identity handed over)"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_view_when_planning_then_text_lists_it_under_renamed(
    test_case: RenamedPlanTextTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Renamed tables and views move no data and appear in their own plan section."""

    write_project(project_dir=tmp_path, models=original_replay_order_models(middle="view"))
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(project_dir=tmp_path, models=renamed_replay_order_models(middle="view"))

    text: CliRun = run_sqb(project_dir=tmp_path, args=("plan",), capsys=capsys)

    assert text.exit_code == 0, text.output
    assert test_case.expected_fragment in text.output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
