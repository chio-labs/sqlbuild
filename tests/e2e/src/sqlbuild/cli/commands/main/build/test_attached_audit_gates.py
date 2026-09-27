"""Real-CLI coverage of attached audits that read other resources gating their target."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    AttachedAuditGateBuildE2ETestCase,
    AttachedAuditGateCycleE2ETestCase,
    AttachedAuditGateNoAuditsE2ETestCase,
    AttachedAuditGatePartialBuildE2ETestCase,
    NestedSourceGateE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    ATTACHED_AUDIT_GATE_DATABASE,
    build_asset_names,
    build_check_outcomes,
    prepare_attached_audit_gate_project,
    prepare_nested_source_gate_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    query_duckdb,
    run_sqb,
    table_exists,
)

_ORDERS_QUERY: str = "SELECT code FROM main.orders"
_RAW_ORDERS_QUERY: str = "SELECT code FROM main.raw_orders"
_ORDER_CODES_QUERY: str = "SELECT code FROM main.order_codes"


@pytest.mark.parametrize(
    "test_case",
    [
        AttachedAuditGateBuildE2ETestCase(
            description="passing model audit reading a sibling model publishes the model",
            target_kind="model",
            target_name="orders",
            audit_name="code_check",
            dependant_name="order_summary",
            order_code="A",
            expected_exit_code=0,
            expected_status="pass",
            expected_dependant_built=True,
            target_query=_ORDERS_QUERY,
            expected_target_rows=(("A",),),
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="failing model audit reading a sibling model keeps the model unpublished",
            target_kind="model",
            target_name="orders",
            audit_name="code_check",
            dependant_name="order_summary",
            order_code="Z",
            expected_exit_code=1,
            expected_status="error",
            expected_dependant_built=False,
            target_query=_ORDERS_QUERY,
            expected_target_rows=(("previous",),),
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="failing model audit keeps the model unpublished in a concurrent build",
            target_kind="model",
            target_name="orders",
            audit_name="code_check",
            dependant_name="order_summary",
            order_code="Z",
            expected_exit_code=1,
            expected_status="error",
            expected_dependant_built=False,
            target_query=_ORDERS_QUERY,
            expected_target_rows=(("previous",),),
            concurrency=4,
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="passing source audit reading a model lets dependants build",
            target_kind="source",
            target_name="raw_orders",
            audit_name="code_check",
            dependant_name="staged_orders",
            order_code="A",
            expected_exit_code=0,
            expected_status="pass",
            expected_dependant_built=True,
            target_query=_RAW_ORDERS_QUERY,
            expected_target_rows=(("A",),),
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="failing source audit reading a model blocks dependants",
            target_kind="source",
            target_name="raw_orders",
            audit_name="code_check",
            dependant_name="staged_orders",
            order_code="Z",
            expected_exit_code=1,
            expected_status="error",
            expected_dependant_built=False,
            target_query=_RAW_ORDERS_QUERY,
            expected_target_rows=(("Z",),),
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="passing seed audit reading a model lets dependants build",
            target_kind="seed",
            target_name="order_codes",
            audit_name="code_check",
            dependant_name="coded_orders",
            order_code="A",
            expected_exit_code=0,
            expected_status="pass",
            expected_dependant_built=True,
            target_query=_ORDER_CODES_QUERY,
            expected_target_rows=(("A",),),
        ),
        AttachedAuditGateBuildE2ETestCase(
            description="failing seed audit reading a model blocks dependants",
            target_kind="seed",
            target_name="order_codes",
            audit_name="code_check",
            dependant_name="coded_orders",
            order_code="Z",
            expected_exit_code=1,
            expected_status="error",
            expected_dependant_built=False,
            target_query=_ORDER_CODES_QUERY,
            expected_target_rows=(("Z",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attached_audit_reading_another_resource_when_building_then_it_gates_its_target(
    test_case: AttachedAuditGateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_attached_audit_gate_project(
        tmp_path=tmp_path, target_kind=test_case.target_kind, order_code=test_case.order_code
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json", "--concurrency", str(test_case.concurrency)),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    # valid_codes sorts after every target and the database starts without it, so the audit
    # resolving it proves the ordering edge; an error proves a real violation, not a missing table.
    assert build_check_outcomes(result.stdout).get(
        (test_case.audit_name, test_case.target_name)
    ) == (test_case.target_kind, test_case.expected_status)
    db_path: Path = project_dir / ATTACHED_AUDIT_GATE_DATABASE
    assert table_exists(db_path=db_path, table_name="valid_codes")
    assert (
        table_exists(db_path=db_path, table_name=test_case.dependant_name)
        is test_case.expected_dependant_built
    )
    assert query_duckdb(db_path=db_path, sql=test_case.target_query) == list(
        test_case.expected_target_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        AttachedAuditGateCycleE2ETestCase(
            description="model audit reading a model built from its target fails to compile",
            target_kind="model",
            read='__ref("order_summary")',
            expected_fragments=(
                "error[P005]",
                "reads model 'order_summary', which depends on 'orders'",
                "singular audit",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attached_audit_reading_its_targets_dependant_when_compiling_then_it_fails(
    test_case: AttachedAuditGateCycleE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_attached_audit_gate_project(
        tmp_path=tmp_path, target_kind=test_case.target_kind, order_code="A", read=test_case.read
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    output: str = result.stdout + result.stderr
    assert result.returncode != 0, output
    for fragment in test_case.expected_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        AttachedAuditGatePartialBuildE2ETestCase(
            description="seed audit reading an unselected model uses its existing table",
            target_kind="seed",
            select="order_codes",
            replaced_read_sql="CREATE OR REPLACE TABLE main.valid_codes AS SELECT 'C' AS code",
            expected_exit_code=1,
            expected_check=("seed", "error"),
            unselected_asset="valid_codes",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_partial_build_when_audit_reads_unselected_model_then_it_uses_existing_table(
    test_case: AttachedAuditGatePartialBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_attached_audit_gate_project(
        tmp_path=tmp_path, target_kind=test_case.target_kind, order_code="A"
    )
    first: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first.returncode == 0, first.stdout + first.stderr
    execute_duckdb(
        db_path=project_dir / ATTACHED_AUDIT_GATE_DATABASE, sql=test_case.replaced_read_sql
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json", "-s", test_case.select),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.unselected_asset not in build_asset_names(result.stdout)
    assert (
        build_check_outcomes(result.stdout).get(("code_check", test_case.select))
        == test_case.expected_check
    )


@pytest.mark.parametrize(
    "test_case",
    [
        AttachedAuditGateNoAuditsE2ETestCase(
            description="failing gate audit is skipped and the model publishes",
            target_kind="model",
            order_code="Z",
            target_query=_ORDERS_QUERY,
            expected_target_rows=(("Z",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_gate_audit_when_building_without_audits_then_target_publishes(
    test_case: AttachedAuditGateNoAuditsE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_attached_audit_gate_project(
        tmp_path=tmp_path, target_kind=test_case.target_kind, order_code=test_case.order_code
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--no-audits"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert query_duckdb(
        db_path=project_dir / ATTACHED_AUDIT_GATE_DATABASE, sql=test_case.target_query
    ) == list(test_case.expected_target_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        NestedSourceGateE2ETestCase(
            description="source audit reached through another audit's read waits for its reads",
            raw_code="B",
            expected_exit_code=0,
            expected_checks={
                ("source_check", "raw_codes"): ("source", "pass"),
                ("order_check", "orders"): ("model", "pass"),
            },
            expected_orders_built=True,
        ),
        NestedSourceGateE2ETestCase(
            description="failing source audit reached through another audit's read blocks it",
            raw_code="Z",
            expected_exit_code=1,
            expected_checks={("source_check", "raw_codes"): ("source", "error")},
            expected_orders_built=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_audit_triggered_by_audit_read_when_building_concurrently_then_reads_wait(
    test_case: NestedSourceGateE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_nested_source_gate_project(
        tmp_path=tmp_path, raw_code=test_case.raw_code
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json", "--concurrency", "4"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    outcomes: dict[tuple[object, object], tuple[object, object]] = build_check_outcomes(
        result.stdout
    )
    assert {key: outcomes.get(key) for key in test_case.expected_checks} == (
        test_case.expected_checks
    )
    assert (
        table_exists(db_path=project_dir / ATTACHED_AUDIT_GATE_DATABASE, table_name="orders")
        is test_case.expected_orders_built
    )
