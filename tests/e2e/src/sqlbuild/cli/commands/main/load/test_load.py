from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load._test_types import (
    SourceLoaderStrategiesE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_source_loader_strategies,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderStrategiesE2ETestCase(
            description="source loader strategies apply expected rows across two loads",
            command=("--no-color", "load", "--concurrency", "4"),
            expected_countries=((1, "US", "United States"), (2, "CA", "Canada")),
            expected_webhook_event_counts=((101, "signup", 2), (102, "checkout", 2)),
            expected_order_events=((201, 1000), (202, 2500), (203, 3000)),
            expected_customers=((1, "pro"), (2, "trial"), (3, "enterprise")),
            expected_loader_status=((1, "loaded", "self_managed"),),
            expected_stdout_fragments=(
                "raw_countries",
                "raw_webhook_events",
                "raw_order_events",
                "raw_customers",
                "raw_loader_status",
            ),
        )
    ],
    ids=["source loader strategies apply expected rows across two loads"],
)
def test_given_source_loader_strategy_project_when_loading_twice_then_all_write_modes_apply(
    tmp_path: Path,
    test_case: SourceLoaderStrategiesE2ETestCase,
) -> None:
    project_dir: Path = prepare_source_loader_strategies(tmp_path=tmp_path)
    db_path: Path = project_dir / "source_loader_strategies.duckdb"

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    second_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode == test_case.expected_return_code, (
        first_result.stdout + first_result.stderr
    )
    assert second_result.returncode == test_case.expected_return_code, (
        second_result.stdout + second_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in second_result.stdout

    countries: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT country_id, country_code, country_name FROM raw_countries ORDER BY country_id"
        ),
    )
    webhook_event_counts: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT event_id, event_name, COUNT(*) FROM raw_webhook_events "
            "GROUP BY event_id, event_name ORDER BY event_id"
        ),
    )
    order_events: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, amount_cents FROM raw_order_events ORDER BY event_id",
    )
    customers: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT customer_id, plan_name FROM raw_customers ORDER BY customer_id",
    )
    loader_status: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=("SELECT status_id, status_name, loaded_by FROM raw_loader_status ORDER BY status_id"),
    )

    assert tuple(countries) == test_case.expected_countries
    assert tuple(webhook_event_counts) == test_case.expected_webhook_event_counts
    assert tuple(order_events) == test_case.expected_order_events
    assert tuple(customers) == test_case.expected_customers
    assert tuple(loader_status) == test_case.expected_loader_status
