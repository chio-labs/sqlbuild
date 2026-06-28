from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCloneOptions
from sqlbuild.integrations.dbt.pipeline.helpers.clone import (
    execute_dbt_clone,
    parse_dbt_clone_options,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtCloneExecuteTestCase,
    DbtCloneExecutionOrderTestCase,
    DbtCloneOptionsErrorTestCase,
    DbtCloneOptionsTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    assert_dbt_clone_execution_result,
    build_dbt_clone_manifest_index,
    build_dbt_clone_reuse_manifest_index,
    build_dbt_diff_ls_node,
    build_manifest_data,
    build_manifest_model_node,
    create_dbt_clone_relation,
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

CLONE_OPTIONS_ERROR_TEST_CASES: tuple[DbtCloneOptionsErrorTestCase, ...] = (
    DbtCloneOptionsErrorTestCase(
        description="rejects clone without explicit select",
        args=(),
        expected_error_fragment="requires an explicit --select",
        expected_help_fragment="Refusing to clone the entire dbt project",
    ),
    DbtCloneOptionsErrorTestCase(
        description="rejects bare positional selector with select hint",
        args=("tag:unicron",),
        expected_error_fragment="unexpected positional argument 'tag:unicron'",
        expected_help_fragment="Use --select tag:unicron",
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
    CLONE_OPTIONS_ERROR_TEST_CASES,
    ids=[case.description for case in CLONE_OPTIONS_ERROR_TEST_CASES],
)
def test_given_unsafe_clone_args_when_parsing_then_raises_argument_error(
    test_case: DbtCloneOptionsErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropArgumentError) as exc_info:
        parse_dbt_clone_options(test_case.args)

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.help is not None
    assert test_case.expected_help_fragment in exc_info.value.help


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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneExecutionOrderTestCase(
            description="orders selected dependencies before dependent views",
            expected_item_names=("base_orders", "child_orders"),
            expected_child_rows=((1, "origin"),),
        )
    ],
    ids=["orders selected dependencies before dependent views"],
)
def test_given_view_selected_before_dependency_when_executing_clone_then_clones_dependency_first(
    test_case: DbtCloneExecutionOrderTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "ordered_clone.duckdb")})
    try:
        create_dbt_clone_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            name="base_orders",
            rows=test_case.expected_child_rows,
        )
        create_dbt_clone_relation(
            adapter=adapter,
            connection=connection,
            schema="prod",
            name="child_orders",
            rows=((99, "origin_view_placeholder"),),
        )
        current_manifest: DbtManifestIndex = build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.base_orders",
                        package_name="analytics",
                        name="base_orders",
                        relation_name="main.base_orders",
                        schema="main",
                        alias="base_orders",
                        materialized="table",
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.child_orders",
                        package_name="analytics",
                        name="child_orders",
                        relation_name="main.child_orders",
                        schema="main",
                        alias="child_orders",
                        materialized="view",
                        compiled_code="SELECT order_id, status FROM main.base_orders",
                        depends_on_nodes=("model.analytics.base_orders",),
                    ),
                )
            )
        )
        reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.base_orders",
                        package_name="analytics",
                        name="base_orders",
                        relation_name="prod.base_orders",
                        schema="prod",
                        alias="base_orders",
                        materialized="table",
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.child_orders",
                        package_name="analytics",
                        name="child_orders",
                        relation_name="prod.child_orders",
                        schema="prod",
                        alias="child_orders",
                        materialized="view",
                    ),
                )
            )
        )
        streamed_item_names: list[str] = []

        result: CloneExecutionResult = execute_dbt_clone(
            adapter=adapter,
            connection=connection,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            selected_nodes=(
                build_dbt_diff_ls_node(
                    unique_id="model.analytics.child_orders", name="child_orders"
                ),
                build_dbt_diff_ls_node(unique_id="model.analytics.base_orders", name="base_orders"),
            ),
            hard_copy=True,
            on_item=lambda _index, _total, item: streamed_item_names.append(item.name),
        )

        assert tuple(item.name for item in result.item_results) == test_case.expected_item_names
        assert tuple(streamed_item_names) == test_case.expected_item_names
        assert (
            read_dbt_clone_rows(
                adapter=adapter, connection=connection, schema="main", name="child_orders"
            )
            == test_case.expected_child_rows
        )
    finally:
        adapter.close(connection)
