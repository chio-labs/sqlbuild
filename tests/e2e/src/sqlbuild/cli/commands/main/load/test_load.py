from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load._test_types import (
    SourceLoaderErrorE2ETestCase,
    SourceLoaderSchemaEvolutionE2ETestCase,
    SourceLoaderStrategiesE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    build_schema_behavior_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
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


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="non-contract source adds late columns to existing append target",
            command=("--no-color", "load"),
            expected_rows=((1, None), (2, "late-note")),
        )
    ],
    ids=["non-contract source adds late columns to existing append target"],
)
def test_given_non_contract_loader_when_late_column_appears_then_existing_target_evolves(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    write_strategy: append\n"
                "    cursor_column: load_seq\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: load_seq\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    if ctx.current_cursor_value is None:\n"
                "        return [{'event_id': 1, 'load_seq': 1}]\n"
                "    return [{'event_id': 2, 'load_seq': 2, 'note': 'late-note'}]\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

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
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, note FROM raw_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows


SOURCE_LOADER_ERROR_TEST_CASES: list[SourceLoaderErrorE2ETestCase] = [
    SourceLoaderErrorE2ETestCase(
        description="contract rejects extra returned columns",
        command=("--no-color", "load"),
        expected_error_fragment="contract has extra columns: extra_note",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_contract_events\n"
                "    loader: raw_contract_events\n"
                "    write_strategy: table\n"
                "    contract: enforced\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_contract_events(ctx):\n"
                "    return [{'event_id': 1, 'extra_note': 'not declared'}]\n"
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="contract rejects missing declared columns",
        command=("--no-color", "load"),
        expected_error_fragment="contract missing columns: event_name",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_contract_events\n"
                "    loader: raw_contract_events\n"
                "    write_strategy: table\n"
                "    contract: enforced\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: event_name\n"
                "        type: VARCHAR\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_contract_events(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="existing target rejects returned type changes",
        command=("--no-color", "load"),
        expected_error_fragment="column 'amount' changed type",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    write_strategy: append\n"
                "    cursor_column: load_seq\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: load_seq\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    if ctx.current_cursor_value is None:\n"
                "        return [{'event_id': 1, 'load_seq': 1, 'amount': 100}]\n"
                "    return [{'event_id': 2, 'load_seq': 2, 'amount': 'one hundred'}]\n"
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SOURCE_LOADER_ERROR_TEST_CASES,
    ids=[case.description for case in SOURCE_LOADER_ERROR_TEST_CASES],
)
def test_given_loader_schema_error_when_loading_then_reports_expected_failure(
    tmp_path: Path,
    test_case: SourceLoaderErrorE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=test_case.repo_files,
    )

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode in {0, test_case.expected_return_code}, (
        first_result.stdout + first_result.stderr
    )
    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in result.stdout
