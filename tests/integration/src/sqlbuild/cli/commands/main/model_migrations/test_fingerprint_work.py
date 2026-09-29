"""Integration coverage for how much migration fingerprint work plan and build perform."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    MigrationFingerprintWorkTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    FingerprintComputation,
    build_each,
    load_raw_orders,
    models_with_stored_migration_fingerprints,
    original_order_models,
    plan_json,
    planned_migrations,
    record_fingerprint_computations,
    renamed_order_models,
    run_sqb,
    write_project,
)

_ORIGINAL_NAMES: tuple[str, ...] = ("daily_order_totals", "orders_enriched", "stg_orders")
_RENAMED_NAMES: tuple[str, ...] = (
    "customer_daily_order_totals",
    "customer_orders_enriched",
    "stg_customer_orders",
)


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationFingerprintWorkTestCase(
            description="plan without earlier state fingerprints nothing",
            prior_models=(),
            models=original_order_models,
            command=("plan", "--json"),
            expected_computations=0,
            expected_migrations=0,
        ),
        MigrationFingerprintWorkTestCase(
            description="plan with renamed models fingerprints each candidate once",
            prior_models=(original_order_models,),
            models=renamed_order_models,
            command=("plan", "--json"),
            expected_computations=3,
            expected_migrations=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_state_when_planning_then_fingerprints_only_migration_candidates_once(
    test_case: MigrationFingerprintWorkTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    build_each(project_dir=tmp_path, model_sets=test_case.prior_models, capsys=capsys)
    write_project(project_dir=tmp_path, models=test_case.models())
    computed: list[FingerprintComputation] = record_fingerprint_computations(monkeypatch)

    migrations: int = len(planned_migrations(plan_json(project_dir=tmp_path, capsys=capsys)))

    assert migrations == test_case.expected_migrations
    assert len(computed) == len(set(computed)) == test_case.expected_computations


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationFingerprintWorkTestCase(
            description="first build fingerprints each built model once",
            prior_models=(),
            models=original_order_models,
            command=("build",),
            expected_computations=3,
            expected_migrations=0,
            expected_stored_models=_ORIGINAL_NAMES,
        ),
        MigrationFingerprintWorkTestCase(
            description="rebuild with a warm compile cache computes no fingerprint",
            prior_models=(original_order_models,),
            models=original_order_models,
            command=("build",),
            expected_computations=0,
            expected_migrations=0,
            expected_stored_models=_ORIGINAL_NAMES,
        ),
        MigrationFingerprintWorkTestCase(
            description="rebuild without the compile cache computes each fingerprint once",
            prior_models=(original_order_models,),
            models=original_order_models,
            command=("build", "--no-cache"),
            expected_computations=3,
            expected_migrations=0,
            expected_stored_models=_ORIGINAL_NAMES,
        ),
        MigrationFingerprintWorkTestCase(
            description="renamed build after a plan computes only unplanned storage fingerprints",
            prior_models=(original_order_models,),
            models=renamed_order_models,
            command=("build",),
            expected_computations=2,
            expected_migrations=3,
            expected_stored_models=tuple(sorted((*_ORIGINAL_NAMES, *_RENAMED_NAMES))),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_state_when_building_then_stores_fingerprints_computed_once(
    test_case: MigrationFingerprintWorkTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    build_each(project_dir=tmp_path, model_sets=test_case.prior_models, capsys=capsys)
    write_project(project_dir=tmp_path, models=test_case.models())
    migrations: int = len(planned_migrations(plan_json(project_dir=tmp_path, capsys=capsys)))
    computed: list[FingerprintComputation] = record_fingerprint_computations(monkeypatch)

    result: CliRun = run_sqb(project_dir=tmp_path, args=test_case.command, capsys=capsys)

    assert result.exit_code == 0, result.output
    assert migrations == test_case.expected_migrations
    assert len(computed) == len(set(computed)) == test_case.expected_computations
    assert models_with_stored_migration_fingerprints(tmp_path) == (test_case.expected_stored_models)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
