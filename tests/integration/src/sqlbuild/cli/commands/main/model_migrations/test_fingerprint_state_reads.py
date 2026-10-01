"""Integration coverage for how often planning reads the fingerprint state table."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    FingerprintStateReadTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    build_each,
    declared_rename_models,
    edited_original_order_models,
    fingerprint_history,
    load_raw_orders,
    original_order_models,
    plan_json,
    planned_migrations,
    record_fingerprint_state_reads,
    renamed_order_models,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintStateReadTestCase(
            description="full plan discovering renames reads latest state once",
            prior_models=(original_order_models, edited_original_order_models),
            models=renamed_order_models,
            plan_args=(),
            expected_reads=1,
            expected_rows_read=lambda identities: identities,
            expected_migrations=(
                ("daily_order_totals", "customer_daily_order_totals", "automatic", "migrate"),
                ("orders_enriched", "customer_orders_enriched", "automatic", "renamed"),
                ("stg_orders", "stg_customer_orders", "automatic", "migrate"),
            ),
        ),
        FingerprintStateReadTestCase(
            description="selected plan of a project declaring migrations reads latest state once",
            prior_models=(original_order_models, edited_original_order_models),
            models=declared_rename_models,
            plan_args=("-s", "stg_customer_orders"),
            expected_reads=1,
            expected_rows_read=lambda identities: identities,
            expected_migrations=(("stg_orders", "stg_customer_orders", "manual", "migrate"),),
        ),
        FingerprintStateReadTestCase(
            description="selected plan without migration work reads only the selected state",
            prior_models=(original_order_models, edited_original_order_models),
            models=original_order_models,
            plan_args=("-s", "stg_orders"),
            expected_reads=1,
            expected_rows_read=lambda identities: 1,
            expected_migrations=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_history_when_planning_then_reads_latest_state_once(
    test_case: FingerprintStateReadTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    build_each(project_dir=tmp_path, model_sets=test_case.prior_models, capsys=capsys)
    stored_rows: int
    identities: int
    stored_rows, identities = fingerprint_history(project_dir=tmp_path)
    write_project(project_dir=tmp_path, models=test_case.models())
    rows_read: list[int] = record_fingerprint_state_reads(monkeypatch)

    migrations: tuple[tuple[str | None, str, str, str], ...] = planned_migrations(
        plan_json(project_dir=tmp_path, capsys=capsys, args=test_case.plan_args)
    )

    assert stored_rows > identities
    assert migrations == test_case.expected_migrations
    assert rows_read == [test_case.expected_rows_read(identities)] * test_case.expected_reads


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
