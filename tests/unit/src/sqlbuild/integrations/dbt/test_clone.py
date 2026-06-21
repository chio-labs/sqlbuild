from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCloneOptions
from sqlbuild.integrations.dbt.pipeline.helpers.clone import (
    execute_dbt_clone,
    parse_dbt_clone_options,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtCloneExecuteTestCase,
    DbtCloneOptionsTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    assert_dbt_clone_execution_result,
    build_dbt_clone_manifest_index,
    build_dbt_clone_reuse_manifest_index,
    build_dbt_diff_ls_node,
    create_dbt_clone_relation_when_requested,
    read_dbt_clone_rows,
)

CLONE_OPTIONS_TEST_CASES: tuple[DbtCloneOptionsTestCase, ...] = (
    DbtCloneOptionsTestCase(
        description="parses select exclude and clone flags",
        args=(
            "--select",
            "dbt_orders",
            "dbt_customers",
            "--exclude",
            "tag:skip",
            "--hard-copy",
            "--no-sql-validation",
        ),
        expected_select=("dbt_orders", "dbt_customers"),
        expected_exclude=("tag:skip",),
        expected_hard_copy=True,
        expected_no_sql_validation=True,
        expected_dbt_args=("--select", "dbt_orders", "dbt_customers", "--exclude", "tag:skip"),
    ),
    DbtCloneOptionsTestCase(
        description="forwards dbt config flags",
        args=("--select", "dbt_orders", "--target", "dev", "--profiles-dir", "profiles"),
        expected_select=("dbt_orders",),
        expected_exclude=(),
        expected_hard_copy=False,
        expected_no_sql_validation=False,
        expected_dbt_args=(
            "--select",
            "dbt_orders",
            "--target",
            "dev",
            "--profiles-dir",
            "profiles",
        ),
    ),
)

CLONE_EXECUTE_TEST_CASES: tuple[DbtCloneExecuteTestCase, ...] = (
    DbtCloneExecuteTestCase(
        description="copies table from origin into current relation",
        current_materialized="table",
        reuse_materialized="table",
        create_destination_relation=True,
        create_origin_relation=True,
        include_reuse_manifest_model=True,
        expected_item_count=1,
        expected_action="copied",
        expected_status="success",
        expected_destination_rows=((1, "origin"),),
    ),
    DbtCloneExecuteTestCase(
        description="recreates current view sql when origin relation exists",
        current_materialized="view",
        reuse_materialized="view",
        create_destination_relation=False,
        create_origin_relation=True,
        include_reuse_manifest_model=True,
        expected_item_count=1,
        expected_action="recreated_view",
        expected_status="success",
        expected_destination_rows=((2, "current"),),
    ),
    DbtCloneExecuteTestCase(
        description="warns when origin relation is missing",
        current_materialized="table",
        reuse_materialized="table",
        create_destination_relation=True,
        create_origin_relation=False,
        include_reuse_manifest_model=True,
        expected_item_count=1,
        expected_action="warning_missing_source",
        expected_status="warning",
        expected_destination_rows=((9, "existing"),),
    ),
    DbtCloneExecuteTestCase(
        description="skips when origin manifest node is missing",
        current_materialized="table",
        reuse_materialized="table",
        create_destination_relation=True,
        create_origin_relation=True,
        include_reuse_manifest_model=False,
        expected_item_count=0,
        expected_action=None,
        expected_status=None,
        expected_destination_rows=((9, "existing"),),
    ),
    DbtCloneExecuteTestCase(
        description="skips ephemeral models",
        current_materialized="ephemeral",
        reuse_materialized="ephemeral",
        create_destination_relation=True,
        create_origin_relation=True,
        include_reuse_manifest_model=True,
        expected_item_count=0,
        expected_action=None,
        expected_status=None,
        expected_destination_rows=((9, "existing"),),
    ),
    DbtCloneExecuteTestCase(
        description="skips seed resources from model clone executor",
        current_materialized="table",
        reuse_materialized="table",
        create_destination_relation=True,
        create_origin_relation=True,
        include_reuse_manifest_model=True,
        expected_item_count=0,
        expected_action=None,
        expected_status=None,
        expected_destination_rows=((9, "existing"),),
        selected_resource_type="seed",
    ),
    DbtCloneExecuteTestCase(
        description="skips snapshot resources from model clone executor",
        current_materialized="table",
        reuse_materialized="table",
        create_destination_relation=True,
        create_origin_relation=True,
        include_reuse_manifest_model=True,
        expected_item_count=0,
        expected_action=None,
        expected_status=None,
        expected_destination_rows=((9, "existing"),),
        selected_resource_type="snapshot",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    CLONE_OPTIONS_TEST_CASES,
    ids=[case.description for case in CLONE_OPTIONS_TEST_CASES],
)
def test_given_clone_args_when_parsing_then_returns_expected_options(
    test_case: DbtCloneOptionsTestCase,
) -> None:
    options: DbtCloneOptions = parse_dbt_clone_options(test_case.args)

    assert options.select == test_case.expected_select
    assert options.exclude == test_case.expected_exclude
    assert options.hard_copy == test_case.expected_hard_copy
    assert options.no_sql_validation == test_case.expected_no_sql_validation
    assert options.dbt_args == test_case.expected_dbt_args


@pytest.mark.parametrize(
    "test_case",
    CLONE_EXECUTE_TEST_CASES,
    ids=[case.description for case in CLONE_EXECUTE_TEST_CASES],
)
def test_given_dbt_clone_selection_when_executing_then_clones_expected_relation(
    test_case: DbtCloneExecuteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "clone.duckdb")})
    try:
        create_dbt_clone_relation_when_requested(
            adapter=adapter,
            connection=connection,
            schema="main",
            create=test_case.create_destination_relation,
            rows=((9, "existing"),),
        )
        create_dbt_clone_relation_when_requested(
            adapter=adapter,
            connection=connection,
            schema="prod",
            create=test_case.create_origin_relation,
        )
        current_manifest: DbtManifestIndex = build_dbt_clone_manifest_index(
            schema="main",
            relation_name="main.dbt_orders",
            materialized=test_case.current_materialized,
            compiled_code="SELECT 2 AS order_id, 'current' AS status",
        )
        reuse_manifest: DbtManifestIndex = build_dbt_clone_reuse_manifest_index(
            include_model=test_case.include_reuse_manifest_model,
            materialized=test_case.reuse_materialized,
        )
        result: CloneExecutionResult = execute_dbt_clone(
            adapter=adapter,
            connection=connection,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            selected_nodes=(
                build_dbt_diff_ls_node(resource_type=test_case.selected_resource_type),
            ),
            hard_copy=True,
        )

        assert_dbt_clone_execution_result(
            result=result,
            expected_item_count=test_case.expected_item_count,
            expected_action=test_case.expected_action,
            expected_status=test_case.expected_status,
        )
        assert (
            read_dbt_clone_rows(adapter=adapter, connection=connection, schema="main")
            == test_case.expected_destination_rows
        )
    finally:
        adapter.close(connection)
